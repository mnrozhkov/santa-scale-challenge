"""Google Drive uploader for final card images."""

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload


def _build_drive_service(credentials_path: str | Path) -> Any:
    """
    Internal helper to build the Google Drive service client.
    """
    credentials = service_account.Credentials.from_service_account_file(
        str(credentials_path),
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )
    # Optional: Domain-wide delegation (Google Workspace) to upload into a user's Drive.
    # Requires the service account to be configured for delegation in Admin Console.
    impersonate_user = os.getenv("GOOGLE_DRIVE_IMPERSONATE_USER")
    if impersonate_user:
        credentials = credentials.with_subject(impersonate_user)
    return build("drive", "v3", credentials=credentials)


def upload_to_google_drive(
    file_path: str | Path,
    folder_id: str | None = None,
    credentials_path: str | None = None,
    service: Any | None = None,
) -> dict[str, str]:
    """
    Upload a file to Google Drive using service account authentication.
    Reuses existing service instance if provided.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # NOTE: `credentials_path` kept for backward compatibility, but env var is authoritative.
    credentials_path_from_env = os.getenv("GOOGLE_DRIVE_CREDENTIALS")
    if not credentials_path_from_env:
        raise ValueError(
            "Missing GOOGLE_DRIVE_CREDENTIALS. Set it to the path of a service account JSON file."
        )
    credentials_path_final = Path(credentials_path_from_env)
    if not credentials_path_final.exists():
        raise FileNotFoundError(
            f"Credentials file not found at GOOGLE_DRIVE_CREDENTIALS: {credentials_path_final}"
        )

    # Get folder ID from env var if not provided
    if folder_id is None:
        folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    if not folder_id:
        raise ValueError("Missing GOOGLE_DRIVE_FOLDER_ID.")

    # Build Drive API service
    if service is None:
        service = _build_drive_service(credentials_path_final)

    # Prepare file metadata
    metadata: dict[str, str | list[str]] = {"name": file_path.name}
    metadata["parents"] = [folder_id]

    media = MediaFileUpload(str(file_path), resumable=True)

    try:
        uploaded = (
            service.files()
            # supportsAllDrives=True is required when uploading into Shared Drives folders
            .create(
                body=metadata,
                media_body=media,
                fields="id,webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )

        file_id = uploaded.get("id")
        web_view_link = uploaded.get("webViewLink")

        if not file_id:
            raise ValueError("Upload succeeded but no file ID returned")

        return {"file_id": file_id, "web_view_link": web_view_link or ""}

    except HttpError as err:
        if err.resp is not None and err.resp.status == 404:
            raise ValueError(
                "Google Drive upload failed with 404 Not Found. "
                "This usually means GOOGLE_DRIVE_FOLDER_ID is invalid OR the folder is not shared "
                "with the service account (share the folder with the service account client_email)."
            ) from err
        if err.resp is not None and err.resp.status == 403:
            raise ValueError(
                "Google Drive upload failed with 403. If the error mentions "
                "'Service Accounts do not have storage quota', you're trying to upload into a "
                "user's 'My Drive'. Fix by either:\n"
                "- Using a Shared Drive folder and adding the service account as a member, or\n"
                "- Enabling Domain-Wide Delegation and setting GOOGLE_DRIVE_IMPERSONATE_USER "
                "to a Workspace user email.\n"
                "Also verify the folder is shared with the target identity."
            ) from err
        raise ValueError(f"Failed to upload file to Google Drive: {err}") from err
    except Exception as err:
        raise ValueError(f"Failed to upload file to Google Drive: {err}") from err


def upload_directory_to_google_drive(
    directory: str | Path,
    folder_id: str | None = None,
    credentials_path: str | None = None,
    recursive: bool = False,
    extensions: Iterable[str] | None = None,
) -> list[dict[str, str]]:
    """
    Upload ALL files in a local directory to Google Drive.

    Args:
        directory: Local directory containing files.
        folder_id: Optional Google Drive folder ID.
        credentials_path: Path to service account credentials JSON.
        recursive: If True, walks through subdirectories.
        extensions: Optional iterable of file extensions to include
                    e.g. {".png", ".jpg", ".json"}

    Returns:
        A list of dicts with Google Drive upload metadata for each file.
    """
    directory = Path(directory)
    if not directory.exists() or not directory.is_dir():
        raise NotADirectoryError(f"Directory not found: {directory}")

    # Build service ONCE for performance
    credentials_path_from_env = os.getenv("GOOGLE_DRIVE_CREDENTIALS")
    if not credentials_path_from_env:
        raise ValueError(
            "Missing GOOGLE_DRIVE_CREDENTIALS. Set it to the path of a service account JSON file."
        )
    credentials_path_final = Path(credentials_path_from_env)
    if not credentials_path_final.exists():
        raise FileNotFoundError(
            f"Credentials file not found at GOOGLE_DRIVE_CREDENTIALS: {credentials_path_final}"
        )

    service = _build_drive_service(credentials_path_final)

    # Collect files
    if recursive:
        file_paths = [p for p in directory.rglob("*") if p.is_file()]
    else:
        file_paths = [p for p in directory.iterdir() if p.is_file()]

    # Filter by extensions if provided
    if extensions:
        extensions = {ext.lower() for ext in extensions}
        file_paths = [p for p in file_paths if p.suffix.lower() in extensions]

    if not file_paths:
        return []

    uploaded_results = []

    for file in file_paths:
        try:
            info = upload_to_google_drive(
                file_path=file,
                folder_id=folder_id,
                credentials_path=credentials_path,
                service=service,  # reusing same session
            )
            uploaded_results.append(
                {
                    "local_path": str(file),
                    "file_id": info["file_id"],
                    "web_view_link": info["web_view_link"],
                }
            )
            print(f"Uploaded: {file} → {info['file_id']}")
        except Exception as e:
            print(f"❌ Failed to upload {file}: {e}")

    return uploaded_results
