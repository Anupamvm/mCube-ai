"""
PDF Text Extraction Utility

Extracts text content from PDF files using pdfplumber.
Used for processing analyst research reports.
"""

import logging
import os
from typing import Tuple

from django.conf import settings

logger = logging.getLogger(__name__)


def _resolve_pdf_path(pdf_path: str) -> str:
    """
    Resolve PDF path to handle absolute paths from different machines.

    If the exact path doesn't exist, tries to find the file relative to BASE_DIR
    by extracting the relative portion from the path.

    Args:
        pdf_path: Original path (may be from another machine)

    Returns:
        Resolved path that exists, or original path if not found
    """
    if not pdf_path:
        return pdf_path

    # If path exists as-is, return it
    if os.path.exists(pdf_path):
        return pdf_path

    # Try to extract relative path and resolve from BASE_DIR
    # Look for common markers in the path
    markers = ['apps/data/tldata/', 'mCube-ai/apps/data/tldata/']

    for marker in markers:
        if marker in pdf_path:
            # Extract the relative part starting from apps/data/tldata/
            idx = pdf_path.find(marker)
            if marker.startswith('mCube-ai/'):
                relative_path = pdf_path[idx + len('mCube-ai/'):]
            else:
                relative_path = pdf_path[idx:]

            resolved = os.path.join(settings.BASE_DIR, relative_path)
            if os.path.exists(resolved):
                logger.debug(f"Resolved PDF path: {pdf_path} -> {resolved}")
                return resolved

    # Return original path if resolution failed
    return pdf_path


def extract_pdf_text(pdf_path: str, max_pages: int = 50) -> Tuple[bool, str, dict]:
    """
    Extract text content from a PDF file.

    Args:
        pdf_path: Path to the PDF file
        max_pages: Maximum number of pages to process (default: 50)

    Returns:
        Tuple of (success, extracted_text, metadata)
        - success: bool indicating if extraction succeeded
        - extracted_text: The extracted text content
        - metadata: dict with page_count, char_count, etc.
    """
    # Resolve path to handle different machines
    resolved_path = _resolve_pdf_path(pdf_path)

    if not resolved_path or not os.path.exists(resolved_path):
        logger.error(f"PDF file not found: {pdf_path}")
        return False, "", {"error": "File not found"}

    try:
        import pdfplumber
    except (ImportError, Exception) as e:
        logger.error(f"pdfplumber not available: {e}. Run: pip install --force-reinstall pdfplumber")
        return False, "", {"error": f"pdfplumber not available: {str(e)}"}

    try:
        text_parts = []
        metadata = {
            "page_count": 0,
            "char_count": 0,
            "file_size": os.path.getsize(resolved_path),
            "file_path": resolved_path,
        }

        with pdfplumber.open(resolved_path) as pdf:
            metadata["page_count"] = len(pdf.pages)
            pages_to_process = min(len(pdf.pages), max_pages)

            for i, page in enumerate(pdf.pages[:pages_to_process]):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(f"--- Page {i + 1} ---\n{page_text}")
                except Exception as page_error:
                    logger.warning(f"Error extracting page {i + 1}: {page_error}")
                    continue

        extracted_text = "\n\n".join(text_parts)
        metadata["char_count"] = len(extracted_text)
        metadata["pages_processed"] = pages_to_process

        if not extracted_text:
            logger.warning(f"No text extracted from PDF: {resolved_path}")
            return False, "", {**metadata, "error": "No text content found"}

        logger.info(f"Extracted {metadata['char_count']} chars from {pages_to_process} pages: {resolved_path}")
        return True, extracted_text, metadata

    except Exception as e:
        logger.error(f"Error extracting text from PDF {resolved_path}: {e}", exc_info=True)
        return False, "", {"error": str(e)}


def extract_pdf_text_truncated(
    pdf_path: str,
    max_chars: int = 15000,
    max_pages: int = 20
) -> Tuple[bool, str, dict]:
    """
    Extract text from PDF with truncation for LLM processing.

    Extracts text and truncates to fit within token limits.
    Useful for analyst reports where we need summary, not full text.

    Args:
        pdf_path: Path to the PDF file
        max_chars: Maximum characters to return (default: 15000 ~= 3750 tokens)
        max_pages: Maximum pages to process

    Returns:
        Tuple of (success, truncated_text, metadata)
    """
    success, full_text, metadata = extract_pdf_text(pdf_path, max_pages)

    if not success:
        return success, full_text, metadata

    if len(full_text) > max_chars:
        # Truncate but try to end at a sentence
        truncated = full_text[:max_chars]
        last_period = truncated.rfind('.')
        if last_period > max_chars * 0.8:
            truncated = truncated[:last_period + 1]
        truncated += "\n\n[... content truncated ...]"
        metadata["truncated"] = True
        metadata["original_char_count"] = len(full_text)
        return True, truncated, metadata

    return True, full_text, metadata


def get_pdf_info(pdf_path: str) -> dict:
    """
    Get basic information about a PDF without extracting text.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        dict with page_count, file_size, etc.
    """
    # Resolve path to handle different machines
    resolved_path = _resolve_pdf_path(pdf_path)

    if not resolved_path or not os.path.exists(resolved_path):
        return {"error": "File not found"}

    try:
        import pdfplumber
    except (ImportError, Exception) as e:
        return {"error": f"pdfplumber not available: {str(e)}"}

    try:
        info = {
            "file_path": resolved_path,
            "file_size": os.path.getsize(resolved_path),
            "file_name": os.path.basename(resolved_path),
        }

        with pdfplumber.open(resolved_path) as pdf:
            info["page_count"] = len(pdf.pages)
            if pdf.metadata:
                info["title"] = pdf.metadata.get("Title", "")
                info["author"] = pdf.metadata.get("Author", "")
                info["creation_date"] = pdf.metadata.get("CreationDate", "")

        return info

    except Exception as e:
        logger.error(f"Error getting PDF info: {e}")
        return {"error": str(e)}
