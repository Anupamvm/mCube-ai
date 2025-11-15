"""
LLM Model Manager

This service manages downloading, storing, and loading LLM models.

Features:
- Download GGUF models from Hugging Face
- Manage local model storage
- Import models into Ollama
- List and verify models
- Model metadata tracking
"""

import logging
import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests
from tqdm import tqdm

logger = logging.getLogger(__name__)


class ModelManager:
    """
    Manages LLM models for the trading system

    Directory Structure:
        models/
        ├── gguf/          # Raw GGUF files downloaded from HuggingFace
        ├── ollama/        # Ollama model files
        └── metadata.json  # Model metadata and tracking
    """

    def __init__(self, models_dir: Optional[str] = None):
        """
        Initialize Model Manager

        Args:
            models_dir: Base directory for models (default: ./models)
        """
        if models_dir is None:
            models_dir = os.path.join(os.getcwd(), 'models')

        self.models_dir = Path(models_dir)
        self.gguf_dir = self.models_dir / 'gguf'
        self.ollama_dir = self.models_dir / 'ollama'
        self.metadata_file = self.models_dir / 'metadata.json'

        # Create directories if they don't exist
        self.gguf_dir.mkdir(parents=True, exist_ok=True)
        self.ollama_dir.mkdir(parents=True, exist_ok=True)

        # Load metadata
        self.metadata = self._load_metadata()

        logger.info(f"Model Manager initialized at {self.models_dir}")

    def _load_metadata(self) -> Dict:
        """Load model metadata from JSON file"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading metadata: {str(e)}")
                return {"models": {}}
        return {"models": {}}

    def _save_metadata(self):
        """Save model metadata to JSON file"""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(self.metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving metadata: {str(e)}")

    def download_from_huggingface(
        self,
        repo_id: str,
        filename: str,
        model_name: Optional[str] = None,
        branch: str = "main"
    ) -> Tuple[bool, str]:
        """
        Download GGUF model from Hugging Face

        Args:
            repo_id: HuggingFace repo ID (e.g., "TheBloke/Llama-2-7B-GGUF")
            filename: Model filename (e.g., "llama-2-7b.Q4_K_M.gguf")
            model_name: Local name for model (default: filename without extension)
            branch: Repository branch (default: "main")

        Returns:
            Tuple[bool, str]: (success, file_path or error_message)

        Example:
            >>> manager = ModelManager()
            >>> success, path = manager.download_from_huggingface(
            ...     "TheBloke/deepseek-coder-6.7B-instruct-GGUF",
            ...     "deepseek-coder-6.7b-instruct.Q4_K_M.gguf"
            ... )
        """
        if model_name is None:
            model_name = Path(filename).stem

        # Build download URL
        url = f"https://huggingface.co/{repo_id}/resolve/{branch}/{filename}"

        # Destination path
        dest_path = self.gguf_dir / filename

        # Check if already downloaded
        if dest_path.exists():
            logger.info(f"Model already exists: {dest_path}")
            self._update_metadata(model_name, str(dest_path), repo_id, filename)
            return True, str(dest_path)

        logger.info(f"Downloading {filename} from {repo_id}...")

        try:
            # Stream download with progress bar
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))

            with open(dest_path, 'wb') as f, tqdm(
                desc=filename,
                total=total_size,
                unit='B',
                unit_scale=True,
                unit_divisor=1024,
            ) as pbar:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))

            logger.info(f"Downloaded successfully: {dest_path}")

            # Update metadata
            self._update_metadata(model_name, str(dest_path), repo_id, filename)

            return True, str(dest_path)

        except Exception as e:
            error_msg = f"Download failed: {str(e)}"
            logger.error(error_msg, exc_info=True)

            # Clean up partial download
            if dest_path.exists():
                dest_path.unlink()

            return False, error_msg

    def _update_metadata(self, model_name: str, file_path: str, repo_id: str, filename: str):
        """Update model metadata"""
        if "models" not in self.metadata:
            self.metadata["models"] = {}

        self.metadata["models"][model_name] = {
            "file_path": file_path,
            "repo_id": repo_id,
            "filename": filename,
            "file_size": os.path.getsize(file_path),
            "downloaded_at": str(Path(file_path).stat().st_mtime)
        }

        self._save_metadata()

    def list_local_models(self) -> List[Dict]:
        """
        List all locally downloaded models

        Returns:
            List[Dict]: List of model information
        """
        models = []

        # From metadata
        for name, info in self.metadata.get("models", {}).items():
            file_path = Path(info["file_path"])
            if file_path.exists():
                models.append({
                    "name": name,
                    "file_path": str(file_path),
                    "file_size_mb": round(info["file_size"] / (1024 * 1024), 2),
                    "repo_id": info.get("repo_id", "Unknown"),
                    "exists": True
                })

        # Check for files not in metadata
        for gguf_file in self.gguf_dir.glob("*.gguf"):
            name = gguf_file.stem
            if name not in self.metadata.get("models", {}):
                models.append({
                    "name": name,
                    "file_path": str(gguf_file),
                    "file_size_mb": round(gguf_file.stat().st_size / (1024 * 1024), 2),
                    "repo_id": "Unknown",
                    "exists": True
                })

        return models

    def import_to_ollama(
        self,
        gguf_filename: str,
        ollama_model_name: str,
        base_model: str = "llama2"
    ) -> Tuple[bool, str]:
        """
        Import GGUF model into Ollama

        Args:
            gguf_filename: GGUF file name in models/gguf/
            ollama_model_name: Name for the model in Ollama
            base_model: Base model template (llama2, mistral, etc.)

        Returns:
            Tuple[bool, str]: (success, message)

        Note:
            This creates a Modelfile and imports it into Ollama.
            Requires Ollama to be running.
        """
        gguf_path = self.gguf_dir / gguf_filename

        if not gguf_path.exists():
            return False, f"GGUF file not found: {gguf_path}"

        # Create Modelfile
        modelfile_content = f"""FROM {gguf_path}

# Temperature
PARAMETER temperature 0.7

# Context window
PARAMETER num_ctx 4096

# System prompt
SYSTEM You are a helpful AI assistant specialized in stock market analysis and trading."""

        modelfile_path = self.ollama_dir / f"{ollama_model_name}.Modelfile"

        try:
            with open(modelfile_path, 'w') as f:
                f.write(modelfile_content)

            logger.info(f"Created Modelfile: {modelfile_path}")

            # Import into Ollama (requires ollama CLI)
            import subprocess

            result = subprocess.run(
                ['ollama', 'create', ollama_model_name, '-f', str(modelfile_path)],
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode == 0:
                logger.info(f"Model imported to Ollama as '{ollama_model_name}'")
                return True, f"Model '{ollama_model_name}' created successfully"
            else:
                error_msg = f"Ollama import failed: {result.stderr}"
                logger.error(error_msg)
                return False, error_msg

        except FileNotFoundError:
            return False, "Ollama CLI not found. Please install Ollama first."
        except Exception as e:
            error_msg = f"Error importing to Ollama: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    def delete_model(self, model_name: str) -> Tuple[bool, str]:
        """
        Delete a local model

        Args:
            model_name: Model name to delete

        Returns:
            Tuple[bool, str]: (success, message)
        """
        if model_name not in self.metadata.get("models", {}):
            return False, f"Model '{model_name}' not found in metadata"

        try:
            file_path = Path(self.metadata["models"][model_name]["file_path"])

            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted model file: {file_path}")

            # Remove from metadata
            del self.metadata["models"][model_name]
            self._save_metadata()

            return True, f"Model '{model_name}' deleted successfully"

        except Exception as e:
            error_msg = f"Error deleting model: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    def get_recommended_models(self) -> List[Dict]:
        """
        Get list of recommended models for trading

        Returns:
            List[Dict]: Recommended models with download info
        """
        return [
            {
                "name": "DeepSeek Coder 6.7B Instruct (Q4_K_M)",
                "repo_id": "TheBloke/deepseek-coder-6.7B-instruct-GGUF",
                "filename": "deepseek-coder-6.7b-instruct.Q4_K_M.gguf",
                "size": "~3.8GB",
                "description": "Excellent for code and analysis. Good balance of size and performance.",
                "use_case": "General analysis, trade validation, code generation"
            },
            {
                "name": "DeepSeek Coder 33B Instruct (Q4_K_M)",
                "repo_id": "TheBloke/deepseek-coder-33b-instruct-GGUF",
                "filename": "deepseek-coder-33b-instruct.Q4_K_M.gguf",
                "size": "~19GB",
                "description": "Larger model with better reasoning. Requires more RAM.",
                "use_case": "Complex analysis, multi-step reasoning"
            },
            {
                "name": "Mistral 7B Instruct (Q4_K_M)",
                "repo_id": "TheBloke/Mistral-7B-Instruct-v0.2-GGUF",
                "filename": "mistral-7b-instruct-v0.2.Q4_K_M.gguf",
                "size": "~4.1GB",
                "description": "Fast and efficient. Good for quick queries.",
                "use_case": "Fast responses, sentiment analysis"
            },
            {
                "name": "Llama 2 13B Chat (Q4_K_M)",
                "repo_id": "TheBloke/Llama-2-13B-chat-GGUF",
                "filename": "llama-2-13b-chat.Q4_K_M.gguf",
                "size": "~7.4GB",
                "description": "Well-balanced model for conversational tasks.",
                "use_case": "Trade discussions, explanations"
            },
            {
                "name": "OpenHermes 2.5 Mistral 7B (Q4_K_M)",
                "repo_id": "TheBloke/OpenHermes-2.5-Mistral-7B-GGUF",
                "filename": "openhermes-2.5-mistral-7b.Q4_K_M.gguf",
                "size": "~4.1GB",
                "description": "Fine-tuned for following instructions accurately.",
                "use_case": "Structured analysis, JSON extraction"
            }
        ]


# Global instance
_model_manager = None


def get_model_manager() -> ModelManager:
    """Get or create global ModelManager instance"""
    global _model_manager

    if _model_manager is None:
        _model_manager = ModelManager()

    return _model_manager
