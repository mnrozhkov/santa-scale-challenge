"""Prompt generation functions for evaluation tasks."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import BaseModel


def generate_gift_recommendation_prompt(kid_profile: "BaseModel") -> str:
    """
    Generate prompt for gift recommendation.

    Args:
        kid_profile: KidProfile instance with name, age, and wishlist

    Returns:
        Formatted prompt string
    """
    wishlist_str = (
        ", ".join(kid_profile.wishlist) if kid_profile.wishlist else "No specific items listed"
    )

    return f"""You are Santa's magical gift recommendation assistant. Based on the child's profile, recommend 3–5 thoughtful, age-appropriate gifts that feel personal, imaginative, and exciting.

Kid Profile:
- Name: {kid_profile.name}
- Age: {kid_profile.age}
- Wishlist: {wishlist_str}

Your task:
1. Recommend 1-3 gifts (one short phrase each).
2. Each gift must be age-appropriate, safe, and appealing for a child of this age.
3. Take inspiration from the child's wishlist, but avoid repeating it unless it is genuinely relevant.
4. Ensure the gifts are fun, creative, and suitable for Santa to give.
5. After the list, provide a warm, concise rationale (2–3 sentences) explaining why these gifts match the child's interests and age.

Format your answer EXACTLY like this:

GIFTS:
- Gift 1
- Gift 2
- Gift 3

RATIONALE:
[2–3 sentence explanation]
"""


def generate_wish_prompt(kid_profile: "BaseModel", gift_recommendation: "BaseModel") -> str:
    """
    Generate prompt for wish generation.

    Args:
        kid_profile: KidProfile instance
        gift_recommendation: GiftRecommendation instance with gifts list

    Returns:
        Formatted prompt string
    """
    gifts_list = "\n".join(f"- {gift}" for gift in gift_recommendation.gifts)

    return f"""You are Santa Claus writing a warm, magical, and age-appropriate holiday message to a child.

Kid Profile:
- Name: {kid_profile.name}
- Age: {kid_profile.age}

Recommended Gifts:
{gifts_list}

Write a personalized holiday wish that:
1. Addresses the child by name.
2. Mentions their age in a natural, encouraging way.
3. References the recommended gifts subtly and magically (no listing, no forced enumeration).
4. Uses a warm, gentle Santa tone that feels joyful and kind.
5. Contains 2–4 sentences.
6. Does NOT include Santa's last name.
7. Ends with "Merry Christmas!" as the final sentence.

Write only the wish text. No prefixes, no labels, no formatting.
"""


def generate_image_prompt(kid_profile: "BaseModel", gift_recommendation: "BaseModel") -> str:
    """
    Generate prompt for image generation.

    Args:
        kid_profile: KidProfile instance
        gift_recommendation: GiftRecommendation instance with gifts list

    Returns:
        Formatted prompt string
    """
    main_gift = gift_recommendation.gifts[0] if gift_recommendation.gifts else "birthday gift"

    return f"""A magical, festive Christmas postcard illustration featuring:
- A joyful, whimsical holiday scene suitable for a child
- The central item: a {main_gift} (shown as a magical, beautifully illustrated object)
- A cheerful, fictional child character (no resemblance to real people) admiring or interacting with the gift
- Bright Christmas decorations: trees, ornaments, presents, snow, twinkling lights, stars
- Warm, vibrant, colorful atmosphere with a magical glow
- Whimsical, storybook-style art appropriate for a children's holiday card
- Soft lighting, sparkles, and a sense of wonder
- No text, signatures, or writing anywhere in the image
- No copyrighted characters

Style:
- Child-friendly, illustrated, magical
- Clean, centered composition suitable for a printed holiday card
"""


# def generate_gift_quality_judge_prompt(
#     kid_profile: "BaseModel",
#     response: str,
# ) -> str:
#     """
#     Generate LLM-as-a-judge prompt for evaluating gift recommendation quality.

#     Args:
#         kid_profile: KidProfile instance
#         response: Generated gift recommendation response

#     Returns:
#         Formatted judge prompt string
#     """
#     wishlist_str = ", ".join(kid_profile.wishlist) if kid_profile.wishlist else "None"

#     return f"""Evaluate the following gift recommendation for quality on a scale of 0.0 to 1.0.

# Kid Profile:
# - Name: {kid_profile.name}
# - Age: {kid_profile.age}
# - Wishlist: {wishlist_str}

# Recommendation:
# {response}

# Consider:
# 1. Age-appropriateness (0.25 weight)
# 2. Relevance to child's interests (0.25 weight)
# 3. Safety and appropriateness (0.25 weight)
# 4. Creativity and thoughtfulness (0.25 weight)

# Respond with ONLY a number between 0.0 and 1.0, nothing else.
# """


def generate_gift_quality_judge_prompt(
    kid_profile: "BaseModel",
    response: str,
) -> str:
    """
    Generate a stable LLM-as-a-judge prompt to evaluate gift recommendation quality.

    Args:
        kid_profile: KidProfile instance
        response: Generated gift recommendation string

    Returns:
        A deterministic judge prompt string
    """

    wishlist_str = ", ".join(kid_profile.wishlist) if kid_profile.wishlist else "None"

    return f"""
You are an evaluator. Score the quality of a gift recommendation from 0.0 to 1.0.

Kid Profile:
Name: {kid_profile.name}
Age: {kid_profile.age}
Wishlist: {wishlist_str}

Recommendation to evaluate:
---
{response}
---

Scoring criteria (each weight = 0.25):
1. Age-appropriateness
2. Relevance to the child's interests
3. Safety and appropriateness
4. Creativity and thoughtfulness

Return ONLY a floating point number between 0.0 and 1.0 with no explanation.
"""


def generate_wish_quality_judge_prompt(
    kid_profile: "BaseModel",
    response: str,
) -> str:
    """
    Generate LLM-as-a-judge prompt for evaluating wish quality.

    Args:
        kid_profile: KidProfile instance
        response: Generated wish response

    Returns:
        Formatted judge prompt string
    """
    return f"""Evaluate the following holiday wish for quality on a scale of 0.0 to 1.0.

Kid Profile:
- Name: {kid_profile.name}
- Age: {kid_profile.age}

Wish:
{response}

Consider:
1. Warmth and personalization (0.3 weight) - Does it feel personal and warm?
2. Age-appropriateness (0.3 weight) - Is the language and content suitable for this age?
3. Safety (0.2 weight) - No dangerous, offensive, or inappropriate content
4. Natural flow and magic (0.2 weight) - Does it read naturally and feel magical?

Respond with ONLY a number between 0.0 and 1.0, nothing else.
"""


def generate_image_quality_judge_prompt(
    prompt: str,
    image_url: str,
    kid_profile: "BaseModel",
) -> str:
    """
    Generate LLM-as-a-judge prompt for evaluating image quality.

    Args:
        prompt: Original image generation prompt
        image_url: URL or path to generated image
        kid_profile: KidProfile instance

    Returns:
        Formatted judge prompt string
    """
    return f"""Evaluate the following image generation for quality on a scale of 0.0 to 1.0.

Image Prompt:
{prompt}

Image URL: {image_url}

Kid Profile:
- Name: {kid_profile.name}
- Age: {kid_profile.age}

Consider:
1. Visual quality and aesthetic appeal (0.3 weight)
2. Relevance to prompt (0.3 weight)
3. Age-appropriateness and child-friendliness (0.2 weight)
4. Holiday theme and magic (0.2 weight)

Respond with ONLY a number between 0.0 and 1.0, nothing else.
"""
