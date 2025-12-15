"""Content generation functions that combine prompts, LLM calls, and parsing."""

from typing import Any

from src.clients.llm_client import LLMClient
from src.prompts import generate_gift_recommendation_prompt
from src.test_samples import GiftRecommendation, KidProfile


def generate_gift_recommendation(
    llm_client: LLMClient,
    kid_profile: KidProfile,
    temperature: float = 0.8,
    max_tokens: int = 300,
) -> tuple[GiftRecommendation, dict[str, Any]]:
    """
    Generate gift recommendations for a kid using LLM.

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
    """
    prompt = generate_gift_recommendation_prompt(kid_profile)
    response, metrics = llm_client.generate(prompt, temperature=temperature, max_tokens=max_tokens)

    # Parse response to extract gifts and rationale
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
        gifts=gifts[:5],  # Limit to 5 gifts
        rationale=rationale.strip(),
        model_version=llm_client.model_version,
    )

    return gift_recommendation, metrics
