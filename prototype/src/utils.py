"""Utility functions for the prototype evaluation framework."""

import base64
from pathlib import Path
from tempfile import NamedTemporaryFile

import requests


def find_repo_root(start_path: Path | None = None) -> Path:
    """
    Find the repository root directory by looking for .git directory or pyproject.toml.

    Args:
        start_path: Starting directory to search from (defaults to current working directory)

    Returns:
        Path to repository root

    Raises:
        ValueError: If repository root cannot be found
    """
    if start_path is None:
        start_path = Path.cwd()
    else:
        start_path = Path(start_path)

    current = start_path.resolve()

    # Look for markers that indicate repo root
    markers = [".git", "pyproject.toml", ".gitignore"]

    while current != current.parent:
        # Check if any marker exists
        for marker in markers:
            if (current / marker).exists():
                return current
        current = current.parent

    # If we reach here, we couldn't find the repo root
    raise ValueError(
        f"Could not find repository root. "
        f"Started searching from: {start_path}. "
        f"Looking for one of: {markers}"
    )


def load_env_from_repo_root(env_file: str = ".env", override: bool = False) -> None:
    """
    Load environment variables from .env file in repository root.

    Args:
        env_file: Name of the environment file (default: ".env")
    """
    from dotenv import load_dotenv

    repo_root = find_repo_root()
    env_path = repo_root / env_file

    if not env_path.exists():
        raise FileNotFoundError(
            f"Environment file not found: {env_path}. " f"Expected location: {repo_root / env_file}"
        )

    load_dotenv(env_path, override)


def download_image_for_mlflow(image_data: str) -> str:
    """
    Download image from URL or decode base64 and save to temporary file for MLflow logging.

    Args:
        image_data: Image URL, base64 encoded string, or local file path

    Returns:
        Path to temporary file or local file path

    Raises:
        requests.RequestException: If downloading from URL fails
        ValueError: If image data cannot be processed
    """
    # Handle base64 encoded images (from Flux/SDXL)
    if image_data.startswith("data:image") or (
        len(image_data) > 100 and not image_data.startswith("http")
    ):
        # Try to decode as base64
        try:
            # Remove data URL prefix if present
            if "," in image_data:
                image_data = image_data.split(",")[1]
            image_bytes = base64.b64decode(image_data)
            ext = ".png"  # default for base64
            with NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
                tmp_file.write(image_bytes)
                return tmp_file.name
        except Exception:
            # If base64 decode fails, treat as URL or local path
            pass

    # Handle HTTP URLs
    if image_data.startswith("http"):
        response = requests.get(image_data, timeout=30)
        response.raise_for_status()
        # Determine file extension from content type or URL
        ext = ".png"  # default
        content_type = response.headers.get("content-type", "").lower()
        if "jpeg" in content_type or ".jpg" in image_data.lower():
            ext = ".jpg"
        elif ".png" in image_data.lower():
            ext = ".png"

        with NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
            tmp_file.write(response.content)
            return tmp_file.name
    else:
        # Local file path
        return image_data
