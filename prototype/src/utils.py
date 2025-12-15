"""Utility functions for the prototype evaluation framework."""

from pathlib import Path


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
