"""Simple S3 upload utility for files and directories."""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

from src.utils import load_env_from_repo_root

# Load .env file from repository root
load_env_from_repo_root()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_s3_client(endpoint_url: str | None = None) -> Any:
    """Create S3 client with optional custom endpoint URL.

    Args:
        endpoint_url: Custom S3 endpoint URL (e.g., for Nebius S3)

    Returns:
        Initialized boto3 S3 client
    """
    config = {}
    if endpoint_url:
        config["endpoint_url"] = endpoint_url

    return boto3.client("s3", **config)


def parse_bucket_name(bucket: str) -> str:
    """Parse bucket name from Nebius format or return as-is.

    Args:
        bucket: Bucket name, possibly in format "nebius://bucket-name"

    Returns:
        Clean bucket name
    """
    if bucket.startswith("nebius://"):
        return bucket.replace("nebius://", "")
    return bucket


def upload_file_to_s3(
    s3_client: Any,
    local_path: Path,
    bucket: str,
    s3_key: str,
) -> bool:
    """Upload a single file to S3.

    Args:
        s3_client: Initialized boto3 S3 client
        local_path: Local file path to upload
        bucket: S3 bucket name
        s3_key: S3 object key (path in bucket)

    Returns:
        True if file was uploaded successfully, False otherwise
    """
    if not local_path.exists():
        logger.error(f"File not found: {local_path}")
        return False

    if not local_path.is_file():
        logger.error(f"Path is not a file: {local_path}")
        return False

    try:
        s3_client.upload_file(str(local_path), bucket, s3_key)
        logger.info(f"✅ Uploaded {local_path.name} to s3://{bucket}/{s3_key}")
        return True
    except ClientError as e:
        logger.error(f"❌ Failed to upload {local_path.name}: {e}")
        return False


def upload_directory_to_s3(
    s3_client: Any,
    local_dir: Path,
    bucket: str,
    s3_prefix: str,
) -> tuple[int, int]:
    """Upload all files from a directory to S3, preserving directory structure.

    Args:
        s3_client: Initialized boto3 S3 client
        local_dir: Local directory to upload
        bucket: S3 bucket name
        s3_prefix: S3 prefix (base path in bucket)

    Returns:
        Tuple of (successful_uploads, failed_uploads)
    """
    if not local_dir.exists():
        logger.error(f"Directory not found: {local_dir}")
        return (0, 0)

    if not local_dir.is_dir():
        logger.error(f"Path is not a directory: {local_dir}")
        return (0, 0)

    successful = 0
    failed = 0

    # Walk through all files in directory
    for file_path in local_dir.rglob("*"):
        if file_path.is_file():
            # Preserve relative path structure
            relative_path = file_path.relative_to(local_dir)
            s3_key = f"{s3_prefix}/{relative_path}".replace("\\", "/")

            if upload_file_to_s3(s3_client, file_path, bucket, s3_key):
                successful += 1
            else:
                failed += 1

    return (successful, failed)


def upload_to_s3(
    source_path: Path,
    bucket: str,
    s3_prefix: str,
    endpoint_url: str | None = None,
) -> tuple[int, int]:
    """Upload a file or directory to S3.

    Args:
        source_path: Local file or directory path to upload
        bucket: S3 bucket name (can be in "nebius://bucket-name" format)
        s3_prefix: S3 prefix (base path in bucket)
        endpoint_url: Optional S3 endpoint URL

    Returns:
        Tuple of (successful_uploads, failed_uploads)
    """
    bucket = parse_bucket_name(bucket)

    # Create S3 client
    logger.info(f"Connecting to S3 bucket: {bucket}")
    if endpoint_url:
        logger.info(f"Using endpoint URL: {endpoint_url}")

    try:
        s3_client = create_s3_client(endpoint_url)
    except Exception as e:
        logger.error(f"Failed to create S3 client: {e}")
        return (0, 0)

    # Upload file or directory
    if source_path.is_file():
        logger.info(f"Uploading file: {source_path}")
        s3_key = f"{s3_prefix}/{source_path.name}"
        success = upload_file_to_s3(s3_client, source_path, bucket, s3_key)
        return (1, 0) if success else (0, 1)
    elif source_path.is_dir():
        logger.info(f"Uploading directory: {source_path}")
        return upload_directory_to_s3(s3_client, source_path, bucket, s3_prefix)
    else:
        logger.error(f"Path does not exist: {source_path}")
        return (0, 0)


def main() -> int:
    """Main entrypoint for S3 upload script."""
    parser = argparse.ArgumentParser(description="Upload file or directory to S3")
    parser.add_argument(
        "--source-file",
        type=str,
        default=None,
        help="Path to file to upload",
    )
    parser.add_argument(
        "--source-dir",
        type=str,
        default=None,
        help="Path to directory to upload",
    )
    parser.add_argument(
        "--destination-bucket",
        type=str,
        default=None,
        help="S3 bucket name (default: from NEBIUS_S3_BUCKET or AWS_S3_BUCKET env var)",
    )
    parser.add_argument(
        "--s3-prefix",
        type=str,
        default="",
        help="S3 prefix/directory path (default: empty)",
    )
    parser.add_argument(
        "--endpoint-url",
        type=str,
        default=None,
        help="S3 endpoint URL (default: from NEBIUS_S3_ENDPOINT_URL or AWS_ENDPOINT_URL env var)",
    )

    args = parser.parse_args()

    # Validate that exactly one source is provided
    if not args.source_file and not args.source_dir:
        logger.error("Either --source-file or --source-dir must be provided")
        return 1

    if args.source_file and args.source_dir:
        logger.error("Cannot specify both --source-file and --source-dir")
        return 1

    # Determine source path
    source_path = Path(args.source_file) if args.source_file else Path(args.source_dir)

    # Get bucket name from args or environment
    bucket = args.destination_bucket
    if not bucket:
        bucket = os.getenv("NEBIUS_S3_BUCKET") or os.getenv("AWS_S3_BUCKET")
        if not bucket:
            logger.error(
                "Bucket name not provided. Use --destination-bucket or set NEBIUS_S3_BUCKET/AWS_S3_BUCKET env var"
            )
            return 1

    # Get endpoint URL from args or environment
    endpoint_url = args.endpoint_url
    if not endpoint_url:
        endpoint_url = os.getenv("NEBIUS_S3_ENDPOINT_URL") or os.getenv("AWS_ENDPOINT_URL")

    # Upload
    logger.info("=" * 80)
    logger.info("Starting S3 upload...")
    logger.info("=" * 80)

    successful, failed = upload_to_s3(source_path, bucket, args.s3_prefix, endpoint_url)

    # Summary
    logger.info("=" * 80)
    logger.info("Upload Summary:")
    logger.info(f"  Successful uploads: {successful}")
    logger.info(f"  Failed uploads: {failed}")
    logger.info("=" * 80)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
