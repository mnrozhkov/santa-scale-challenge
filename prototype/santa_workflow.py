#!/usr/bin/env python3
"""Main entrypoint for Santa Agent Pipeline prototype.

Sequential pipeline that processes kid profiles from CSV and generates personalized gift cards.
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from src.card_formatter import create_complete_gift_card
from src.csv_reader import read_kid_profiles_from_csv
from src.data_scheme import GiftCard, KidProfile
from src.drive_uploader import upload_to_google_drive
from src.generators import generate_card_image, generate_gift_recommendation, generate_wish
from src.image_model_config import get_available_image_models
from src.model_config import get_available_models
from src.utils import load_env_from_repo_root

# Load .env file from repository root
load_env_from_repo_root()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def save_intermediate_result(
    output_dir: Path,
    kid_id: str,
    step_name: str,
    data: dict,
) -> None:
    """
    Save intermediate result to JSON file.

    Args:
        output_dir: Directory to save intermediate results
        kid_id: ID of the kid
        step_name: Name of the step (e.g., "gift_recommendation", "wish", "image")
        data: Data to save (should be JSON-serializable)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"{kid_id}_{step_name}.json"

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)

    logger.debug(f"Saved intermediate result: {file_path}")


def process_kid(
    kid_profile: KidProfile,
    llm_client,
    image_client,
    output_dir: Path,
    intermediate_dir: Path,
    upload_to_drive: bool = True,
) -> GiftCard | None:
    """
    Process a single kid through the entire pipeline.

    Args:
        kid_profile: Profile of the kid
        llm_client: Initialized LLM client
        image_client: Initialized image client
        output_dir: Directory to save final PNG cards
        intermediate_dir: Directory to save intermediate results
        upload_to_drive: Whether to upload final card to Google Drive

    Returns:
        GiftCard object if successful, None if failed

    Raises:
        Exception: If any step fails (will be caught by caller)
    """
    logger.info(f"Processing {kid_profile.name} (ID: {kid_profile.id})...")

    # Step 1: Generate gift recommendation
    logger.info(f"  Generating gift recommendation for {kid_profile.name}...")
    gift_recommendation, gift_metrics = generate_gift_recommendation(
        llm_client=llm_client,
        kid_profile=kid_profile,
    )
    save_intermediate_result(
        intermediate_dir,
        kid_profile.id,
        "gift_recommendation",
        {
            "recommendation": gift_recommendation.model_dump(),
            "metrics": gift_metrics,
            "timestamp": datetime.now().isoformat(),
        },
    )
    logger.info(f"  ✅ Generated {len(gift_recommendation.gifts)} gift recommendations")

    # Step 2: Generate wish
    logger.info(f"  Generating wish for {kid_profile.name}...")
    wish, wish_metrics = generate_wish(
        llm_client=llm_client,
        kid_profile=kid_profile,
        gift_recommendation=gift_recommendation,
    )
    save_intermediate_result(
        intermediate_dir,
        kid_profile.id,
        "wish",
        {
            "wish": wish.model_dump(),
            "metrics": wish_metrics,
            "timestamp": datetime.now().isoformat(),
        },
    )
    logger.info("  ✅ Generated wish")

    # Step 3: Generate card image
    logger.info(f"  Generating card image for {kid_profile.name}...")
    card_image, image_metrics = generate_card_image(
        image_client=image_client,
        kid_profile=kid_profile,
        gift_recommendation=gift_recommendation,
    )
    save_intermediate_result(
        intermediate_dir,
        kid_profile.id,
        "image",
        {
            "image": card_image.model_dump(),
            "metrics": image_metrics,
            "timestamp": datetime.now().isoformat(),
        },
    )
    logger.info(f"  ✅ Generated card image: {card_image.image_url}")

    # Step 4: Format and save PNG card
    logger.info(f"  Creating PNG card for {kid_profile.name}...")
    gift_card = create_complete_gift_card(
        kid_profile=kid_profile,
        gift_recommendation=gift_recommendation,
        wish=wish,
        card_image=card_image,
        output_dir=str(output_dir),
    )
    save_intermediate_result(
        intermediate_dir,
        kid_profile.id,
        "gift_card",
        {
            "gift_card": gift_card.model_dump(),
            "timestamp": datetime.now().isoformat(),
        },
    )
    logger.info(f"  ✅ Created PNG card: {gift_card.rendered_url}")

    # Step 5: Upload to Google Drive (if enabled)
    if upload_to_drive and gift_card.rendered_url:
        logger.info(f"  Uploading card to Google Drive for {kid_profile.name}...")
        try:
            drive_result = upload_to_google_drive(
                file_path=gift_card.rendered_url,
            )
            logger.info(
                f"  ✅ Uploaded to Google Drive: {drive_result.get('web_view_link', 'N/A')}"
            )
        except Exception as e:
            logger.warning(f"  ⚠️  Failed to upload to Google Drive: {e}")
            # Don't fail the entire pipeline if upload fails

    logger.info(f"✅ Completed processing {kid_profile.name}")
    return gift_card


def main() -> int:
    """Main entrypoint for the Santa workflow."""
    parser = argparse.ArgumentParser(
        description="Santa Agent Pipeline - Generate personalized gift cards from CSV"
    )
    parser.add_argument(
        "csv_path",
        type=str,
        help="Path to CSV file with kid profiles",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="prototype/data/santa_workflow/cards",
        help="Directory to save final PNG cards (default: prototype/data/santa_workflow/cards)",
    )
    parser.add_argument(
        "--intermediate-dir",
        type=str,
        default="prototype/data/santa_workflow/intermediate",
        help="Directory to save intermediate results (default: prototype/data/santa_workflow/intermediate)",
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default="gpt-4o-mini",
        help="LLM model name to use (default: first available from config)",
    )
    parser.add_argument(
        "--image-model",
        type=str,
        default="recraftv3",
        help="Image model name to use (default: first available from config)",
    )
    parser.add_argument(
        "--no-drive-upload",
        action="store_true",
        help="Skip Google Drive upload",
    )
    parser.add_argument(
        "--default-age",
        type=int,
        default=10,
        help="Default age for kids (default: 10)",
    )

    args = parser.parse_args()

    # Validate CSV path
    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        logger.error(f"CSV file not found: {csv_path}")
        return 1

    # Create output directories
    output_dir = Path(args.output_dir)
    intermediate_dir = Path(args.intermediate_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    intermediate_dir.mkdir(parents=True, exist_ok=True)

    # Initialize LLM client
    logger.info("Initializing LLM client...")
    llm_models = get_available_models(
        include_openai=True,
        include_token_factory=True,
        include_self_hosted=True,
    )
    if not llm_models:
        logger.error(
            "No LLM models available. Set OPENAI_API_KEY / TOKEN_FACTORY_API_KEY / self-hosted env vars."
        )
        return 1

    if args.llm_model:
        llm_model = next((m for m in llm_models if m.name == args.llm_model), None)
        if not llm_model:
            logger.error(
                f"LLM model '{args.llm_model}' not found. Available: {[m.name for m in llm_models]}"
            )
            return 1
    else:
        llm_model = llm_models[0]

    llm_client = llm_model.client
    logger.info(f"✅ Using LLM model: {llm_model.name}")

    # Initialize image client
    logger.info("Initializing image client...")
    image_models = get_available_image_models()
    if not image_models:
        logger.error(
            "No image models available. Set RECRAFT_API_KEY or other required environment variables."
        )
        return 1

    if args.image_model:
        image_model = next((m for m in image_models if m.name == args.image_model), None)
        if not image_model:
            logger.error(
                f"Image model '{args.image_model}' not found. Available: {[m.name for m in image_models]}"
            )
            return 1
    else:
        image_model = image_models[0]

    image_client = image_model.client
    logger.info(f"✅ Using image model: {image_model.name}")

    # Read kid profiles from CSV
    logger.info(f"Reading kid profiles from {csv_path}...")
    try:
        kid_profiles = read_kid_profiles_from_csv(csv_path, default_age=args.default_age)
        logger.info(f"✅ Loaded {len(kid_profiles)} kid profiles")
    except Exception as e:
        logger.error(f"Failed to read CSV: {e}")
        return 1

    # Process each kid
    logger.info("Starting pipeline processing...")
    successful = 0
    failed = 0

    for kid_profile in kid_profiles:
        try:
            gift_card = process_kid(
                kid_profile=kid_profile,
                llm_client=llm_client,
                image_client=image_client,
                output_dir=output_dir,
                intermediate_dir=intermediate_dir,
                upload_to_drive=not args.no_drive_upload,
            )
            if gift_card:
                successful += 1
        except Exception as e:
            failed += 1
            logger.error(f"❌ Failed to process {kid_profile.name}: {e}", exc_info=True)
            # Continue with next kid (error recovery)

    # Summary
    logger.info("=" * 80)
    logger.info("Pipeline Summary:")
    logger.info(f"  Total kids: {len(kid_profiles)}")
    logger.info(f"  Successful: {successful}")
    logger.info(f"  Failed: {failed}")
    logger.info("=" * 80)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
