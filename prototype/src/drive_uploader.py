"""Google Drive uploader for final card images."""

import os
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


def upload_to_google_drive(
    file_path: str | Path,
    folder_id: str | None = None,
    credentials_path: str | None = None,
) -> dict[str, str]:
    """
    Upload a file to Google Drive using service account authentication.

    Args:
        file_path: Path to the file to upload
        folder_id: Optional folder ID to upload to (from GOOGLE_DRIVE_FOLDER_ID env var)
        credentials_path: Path to service account JSON file (from GOOGLE_DRIVE_CREDENTIALS env var)

    Returns:
        Dictionary with 'file_id' and 'web_view_link' keys

    Raises:
        ValueError: If credentials are not found or upload fails
        FileNotFoundError: If file_path doesn't exist
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Get credentials path from env var if not provided
    if credentials_path is None:
        credentials_path = os.getenv("GOOGLE_DRIVE_CREDENTIALS")
        if not credentials_path:
            raise ValueError(
                "Google Drive credentials not found. "
                "Set GOOGLE_DRIVE_CREDENTIALS environment variable with path to service account JSON file."
            )

    credentials_path = Path(credentials_path)
    if not credentials_path.exists():
        raise FileNotFoundError(f"Credentials file not found: {credentials_path}")

    # Get folder ID from env var if not provided
    if folder_id is None:
        folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

    # Authenticate using service account
    try:
        credentials = service_account.Credentials.from_service_account_file(
            str(credentials_path),
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )
    except Exception as e:
        raise ValueError(f"Failed to load service account credentials: {e}") from e

    # Build Drive API service
    try:
        service = build("drive", "v3", credentials=credentials)
    except Exception as e:
        raise ValueError(f"Failed to build Drive API service: {e}") from e

    # Prepare file metadata
    file_metadata: dict[str, str | list[str]] = {
        "name": file_path.name,
    }

    # Add folder parent if provided
    if folder_id:
        file_metadata["parents"] = [folder_id]

    # Upload file
    try:
        media = MediaFileUpload(str(file_path), resumable=True)

        file = (
            service.files()
            .create(body=file_metadata, media_body=media, fields="id,webViewLink")
            .execute()
        )

        file_id = file.get("id")
        web_view_link = file.get("webViewLink")

        if not file_id:
            raise ValueError("Upload succeeded but no file ID returned")

        return {
            "file_id": file_id,
            "web_view_link": web_view_link or "",
        }

    except Exception as e:
        raise ValueError(f"Failed to upload file to Google Drive: {e}") from e
