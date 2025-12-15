"""Content generation functions that combine prompts, LLM calls, and parsing."""

from typing import Any

from src.clients.image_client import ImageClient
from src.clients.llm_client import LLMClient
from src.data_scheme import CardImage, GiftRecommendation, KidProfile, Wish
from src.prompts import generate_gift_recommendation_prompt, generate_wish_prompt


def generate_gift_recommendation(
    llm_client: LLMClient,
    kid_profile: KidProfile,
    temperature: float = 0.8,
    max_tokens: int = 300,
) -> tuple[GiftRecommendation, dict[str, Any]]:
    """
    Generate gift recommendations for a kid using LLM with structured JSON output.

    Args:
        llm_client: Initialized LLM client
        kid_profile: Profile of the kid
        temperature: Sampling temperature (default: 0.8)
        max_tokens: Maximum tokens to generate (default: 300)

    Returns:
        Tuple of (GiftRecommendation, metrics_dict) where metrics includes:
        - latency_ms: Time taken in milliseconds
        - tokens_in: Input tokens
        - tokens_out: Output tokens
        - model: Model name used

    Raises:
        ValueError: If JSON parsing fails or required fields are missing
    """
    prompt = generate_gift_recommendation_prompt(kid_profile)

    try:
        # Try structured JSON output first
        response_json, metrics = llm_client.generate_json(
            prompt, temperature=temperature, max_tokens=max_tokens
        )

        # Validate and extract fields
        gifts = response_json.get("gifts", [])
        rationale = response_json.get("rationale", "")

        if not gifts:
            raise ValueError("No gifts found in JSON response")
        if not rationale:
            raise ValueError("No rationale found in JSON response")

        gift_recommendation = GiftRecommendation(
            kid_id=kid_profile.id,
            gifts=gifts[:5],  # Limit to 5 gifts
            rationale=rationale.strip(),
            model_version=llm_client.model_version,
        )

        return gift_recommendation, metrics

    except ValueError:
        # If JSON mode fails, fall back to text parsing (for models that don't support JSON)
        response, metrics = llm_client.generate(
            prompt, temperature=temperature, max_tokens=max_tokens
        )

        # Fallback parsing (existing logic)
        lines = response.split("\n")
        gifts = []
        rationale = ""
        in_gifts_section = False
        in_rationale_section = False

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.upper().startswith("GIFTS"):
                in_gifts_section = True
                in_rationale_section = False
                continue
            elif line.upper().startswith("RATIONALE"):
                in_rationale_section = True
                in_gifts_section = False
                continue

            if in_gifts_section and line.startswith("-"):
                gift = line[1:].strip()
                if gift:
                    gifts.append(gift)
            elif in_rationale_section:
                rationale += line + " "

        # Fallback: if parsing failed, try to extract gifts from lines starting with "-"
        if not gifts:
            for line in lines:
                if line.strip().startswith("-"):
                    gift = line.strip()[1:].strip()
                    if gift:
                        gifts.append(gift)

        # If still no gifts, use the first few sentences as gifts
        if not gifts:
            sentences = response.split(".")
            gifts = [s.strip() for s in sentences[:3] if s.strip()]

        # Use remaining text as rationale if not found
        if not rationale.strip():
            rationale = response

        gift_recommendation = GiftRecommendation(
            kid_id=kid_profile.id,
            gifts=gifts[:5] if gifts else ["Unknown gift"],
            rationale=rationale.strip() or "No rationale provided",
            model_version=llm_client.model_version,
        )

        return gift_recommendation, metrics


def generate_wish(
    llm_client: LLMClient,
    kid_profile: KidProfile,
    gift_recommendation: GiftRecommendation,
    temperature: float = 0.9,
    max_tokens: int = 200,
) -> tuple[Wish, dict[str, Any]]:
    """
    Generate a personalized holiday wish for a kid using LLM with structured JSON output.

    Args:
        llm_client: Initialized LLM client
        kid_profile: Profile of the kid
        gift_recommendation: Previously generated gift recommendation
        temperature: Sampling temperature (default: 0.9)
        max_tokens: Maximum tokens to generate (default: 200)

    Returns:
        Tuple of (Wish, metrics_dict) where metrics includes:
        - latency_ms: Time taken in milliseconds
        - tokens_in: Input tokens
        - tokens_out: Output tokens
        - model: Model name used

    Raises:
        ValueError: If JSON parsing fails or required fields are missing
    """
    prompt = generate_wish_prompt(kid_profile, gift_recommendation)

    try:
        # Try structured JSON output first
        response_json, metrics = llm_client.generate_json(
            prompt, temperature=temperature, max_tokens=max_tokens
        )

        # Validate and extract fields
        wish_text = response_json.get("wish", "")

        if not wish_text:
            raise ValueError("No wish text found in JSON response")

        wish = Wish(
            kid_id=kid_profile.id,
            text=wish_text.strip(),
            model_version=llm_client.model_version,
        )

        return wish, metrics

    except ValueError:
        # If JSON mode fails, fall back to text parsing (for models that don't support JSON)
        response, metrics = llm_client.generate(
            prompt, temperature=temperature, max_tokens=max_tokens
        )

        # For wish generation, the response should be plain text
        # Clean up any potential formatting artifacts
        wish_text = response.strip()

        # Remove any JSON-like formatting if present
        if wish_text.startswith("{") and "wish" in wish_text:
            # Try to extract wish from JSON-like string
            try:
                import json

                # Try to parse as JSON
                if wish_text.startswith("{"):
                    parsed = json.loads(wish_text)
                    wish_text = parsed.get("wish", wish_text)
            except (json.JSONDecodeError, ValueError):
                # If parsing fails, use the text as-is
                pass

        # Remove any prefixes or labels that might have been added
        prefixes_to_remove = [
            "Wish:",
            "Here is the wish:",
            "The wish is:",
            "Santa's wish:",
        ]
        for prefix in prefixes_to_remove:
            if wish_text.lower().startswith(prefix.lower()):
                wish_text = wish_text[len(prefix) :].strip()

        wish = Wish(
            kid_id=kid_profile.id,
            text=wish_text or "No wish generated",
            model_version=llm_client.model_version,
        )

        return wish, metrics


def generate_card_image(
    image_client: ImageClient, kid_profile: KidProfile, gift_recommendation: GiftRecommendation
) -> tuple[CardImage, dict[str, Any]]:
    """
    Generate a card image based on kid profile and gift recommendations.

    Args:
        image_client: Initialized image generation client
        kid_profile: Profile of the kid
        gift_recommendation: Previously generated gift recommendation

    Returns:
        Tuple of (CardImage, metrics_dict) where metrics includes:
        - latency_ms: Time taken in milliseconds
        - model: Model name used
    """
    # Create a prompt for image generation
    main_gift = gift_recommendation.gifts[0] if gift_recommendation.gifts else "birthday gift"

    #     prompt = f"""A magical, festive holiday card illustration featuring:
    # - A cheerful, age-appropriate scene for a {kid_profile.age}-year-old child
    # - A {main_gift} in the center of the image
    # - Holiday decorations: Christmas tree, snow, presents, stars
    # - Warm, colorful, and joyful atmosphere
    # - Suitable for a holiday gift card
    # - Style: whimsical, child-friendly, magical
    # - No text in the image"""

    prompt = f"""
    A magical, festive Christmas postcard illustration featuring:
- A joyful, whimsical holiday scene suitable for a child
- The central item: a {main_gift} (shown as a magical, beautifully illustrated object)
- A cheerful, fictional child character (no resemblance to real people) admiring or interacting with the gift
- Bright Christmas decorations: trees, ornaments, presents, snow, twinkling lights, stars
- Warm, vibrant, colorful atmosphere with a magical glow
- Whimsical, storybook-style art appropriate for a children’s holiday card
- Soft lighting, sparkles, and a sense of wonder
- No text, signatures, or writing anywhere in the image
- No copyrighted characters

Style:
- Child-friendly, illustrated, magical
- Clean, centered composition suitable for a printed holiday card
    """

    # Unified API: all services use the same simple call
    # Defaults are handled automatically by ImageClient (1024x1024, PNG format, service-appropriate settings)
    image_url, metrics = image_client.generate(prompt=prompt)

    image = CardImage(
        kid_id=kid_profile.id,
        image_url=image_url,
        model_version=image_client.model_version,
        prompt=prompt,
    )

    return image, metrics
