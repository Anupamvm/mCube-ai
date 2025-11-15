"""
ChromaDB Vector Store Service

This service handles vector storage and semantic search using ChromaDB.

Features:
- Store text embeddings
- Semantic search
- Hybrid search (vector + metadata filtering)
- Collection management
- Persistence
"""

import logging
import os
from typing import Dict, List, Optional, Tuple
import chromadb
from chromadb.config import Settings
import uuid

logger = logging.getLogger(__name__)


class VectorStore:
    """
    ChromaDB-based vector store for semantic search

    Stores embeddings with metadata for efficient retrieval
    """

    def __init__(self, persist_directory: Optional[str] = None):
        """
        Initialize ChromaDB client

        Args:
            persist_directory: Directory to persist data (default: ./chroma_db)
        """
        if persist_directory is None:
            persist_directory = os.path.join(
                os.getcwd(),
                'chroma_db'
            )

        try:
            # Initialize ChromaDB client with persistence
            self.client = chromadb.Client(Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=persist_directory
            ))

            self.persist_directory = persist_directory
            self.enabled = True

            logger.info(f"ChromaDB initialized at {persist_directory}")

        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {str(e)}")
            self.enabled = False
            self.client = None

    def is_enabled(self) -> bool:
        """Check if vector store is enabled"""
        return self.enabled

    def get_or_create_collection(
        self,
        name: str,
        metadata: Optional[Dict] = None
    ):
        """
        Get or create a collection

        Args:
            name: Collection name
            metadata: Collection metadata

        Returns:
            Collection object or None
        """
        if not self.enabled:
            return None

        try:
            collection = self.client.get_or_create_collection(
                name=name,
                metadata=metadata or {}
            )
            logger.debug(f"Collection '{name}' ready (count: {collection.count()})")
            return collection

        except Exception as e:
            logger.error(f"Error getting collection: {str(e)}")
            return None

    def add_documents(
        self,
        collection_name: str,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict]] = None,
        ids: Optional[List[str]] = None
    ) -> Tuple[bool, List[str]]:
        """
        Add documents with embeddings to collection

        Args:
            collection_name: Collection to add to
            documents: List of document texts
            embeddings: List of embedding vectors
            metadatas: List of metadata dicts
            ids: List of document IDs (auto-generated if None)

        Returns:
            Tuple[bool, List[str]]: (success, list of document IDs)
        """
        if not self.enabled:
            return False, []

        try:
            collection = self.get_or_create_collection(collection_name)

            if collection is None:
                return False, []

            # Generate IDs if not provided
            if ids is None:
                ids = [str(uuid.uuid4()) for _ in documents]

            # Add to collection
            collection.add(
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas or [{} for _ in documents],
                ids=ids
            )

            logger.info(f"Added {len(documents)} documents to '{collection_name}'")
            return True, ids

        except Exception as e:
            logger.error(f"Error adding documents: {str(e)}", exc_info=True)
            return False, []

    def query(
        self,
        collection_name: str,
        query_embeddings: List[List[float]],
        n_results: int = 10,
        where: Optional[Dict] = None,
        include: Optional[List[str]] = None
    ) -> Dict:
        """
        Query collection for similar documents

        Args:
            collection_name: Collection to query
            query_embeddings: Query embedding vectors
            n_results: Number of results to return
            where: Metadata filter conditions
            include: Fields to include in results

        Returns:
            Dict: Query results with documents, distances, metadatas
        """
        if not self.enabled:
            return {}

        try:
            collection = self.client.get_collection(collection_name)

            if collection is None:
                logger.warning(f"Collection '{collection_name}' not found")
                return {}

            # Default includes
            if include is None:
                include = ["documents", "metadatas", "distances"]

            results = collection.query(
                query_embeddings=query_embeddings,
                n_results=n_results,
                where=where,
                include=include
            )

            logger.debug(f"Query returned {len(results.get('ids', [[]])[0])} results")
            return results

        except Exception as e:
            logger.error(f"Error querying collection: {str(e)}", exc_info=True)
            return {}

    def query_by_text(
        self,
        collection_name: str,
        query_text: str,
        embedding_function,
        n_results: int = 10,
        where: Optional[Dict] = None
    ) -> Dict:
        """
        Query collection using text (with embedding function)

        Args:
            collection_name: Collection to query
            query_text: Query text
            embedding_function: Function to generate embedding
            n_results: Number of results
            where: Metadata filter

        Returns:
            Dict: Query results
        """
        if not self.enabled:
            return {}

        try:
            # Generate embedding for query text
            success, embedding = embedding_function(query_text)

            if not success or not embedding:
                logger.error("Failed to generate query embedding")
                return {}

            # Query with embedding
            return self.query(
                collection_name,
                query_embeddings=[embedding],
                n_results=n_results,
                where=where
            )

        except Exception as e:
            logger.error(f"Error in text query: {str(e)}", exc_info=True)
            return {}

    def update_document(
        self,
        collection_name: str,
        document_id: str,
        document: Optional[str] = None,
        embedding: Optional[List[float]] = None,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Update a document in collection

        Args:
            collection_name: Collection name
            document_id: Document ID to update
            document: New document text
            embedding: New embedding vector
            metadata: New metadata

        Returns:
            bool: Success status
        """
        if not self.enabled:
            return False

        try:
            collection = self.client.get_collection(collection_name)

            if collection is None:
                return False

            collection.update(
                ids=[document_id],
                documents=[document] if document else None,
                embeddings=[embedding] if embedding else None,
                metadatas=[metadata] if metadata else None
            )

            logger.debug(f"Updated document {document_id} in '{collection_name}'")
            return True

        except Exception as e:
            logger.error(f"Error updating document: {str(e)}")
            return False

    def delete_document(
        self,
        collection_name: str,
        document_id: str
    ) -> bool:
        """
        Delete a document from collection

        Args:
            collection_name: Collection name
            document_id: Document ID to delete

        Returns:
            bool: Success status
        """
        if not self.enabled:
            return False

        try:
            collection = self.client.get_collection(collection_name)

            if collection is None:
                return False

            collection.delete(ids=[document_id])

            logger.debug(f"Deleted document {document_id} from '{collection_name}'")
            return True

        except Exception as e:
            logger.error(f"Error deleting document: {str(e)}")
            return False

    def get_collection_stats(self, collection_name: str) -> Dict:
        """
        Get collection statistics

        Args:
            collection_name: Collection name

        Returns:
            Dict: Collection stats (count, metadata, etc.)
        """
        if not self.enabled:
            return {}

        try:
            collection = self.client.get_collection(collection_name)

            if collection is None:
                return {}

            return {
                "name": collection_name,
                "count": collection.count(),
                "metadata": collection.metadata
            }

        except Exception as e:
            logger.error(f"Error getting stats: {str(e)}")
            return {}

    def list_collections(self) -> List[str]:
        """
        List all collections

        Returns:
            List[str]: List of collection names
        """
        if not self.enabled:
            return []

        try:
            collections = self.client.list_collections()
            return [c.name for c in collections]

        except Exception as e:
            logger.error(f"Error listing collections: {str(e)}")
            return []

    def delete_collection(self, collection_name: str) -> bool:
        """
        Delete a collection

        Args:
            collection_name: Collection to delete

        Returns:
            bool: Success status
        """
        if not self.enabled:
            return False

        try:
            self.client.delete_collection(collection_name)
            logger.info(f"Deleted collection '{collection_name}'")
            return True

        except Exception as e:
            logger.error(f"Error deleting collection: {str(e)}")
            return False

    def persist(self) -> bool:
        """
        Persist the database to disk

        Returns:
            bool: Success status
        """
        if not self.enabled:
            return False

        try:
            self.client.persist()
            logger.info("ChromaDB persisted to disk")
            return True

        except Exception as e:
            logger.error(f"Error persisting: {str(e)}")
            return False


# Global instance
_vector_store = None


def get_vector_store() -> VectorStore:
    """Get or create global VectorStore instance"""
    global _vector_store

    if _vector_store is None:
        _vector_store = VectorStore()

    return _vector_store


# Collection name constants
COLLECTION_NEWS = "news_articles"
COLLECTION_CALLS = "investor_calls"
COLLECTION_KNOWLEDGE = "knowledge_base"
COLLECTION_REPORTS = "research_reports"
