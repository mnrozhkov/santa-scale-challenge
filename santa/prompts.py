"""Prompt builders. Lifted from prototype/src/prompts.py; wish prompt now also asks for a mood tag."""

from __future__ import annotations

from santa.schemas import GiftRecommendation, KidProfile

MOODS = ("warm", "playful", "dreamy", "adventurous", "cozy", "magical", "joyful", "calm")


def gift_recommendation_prompt(kid: KidProfile) -> str:
    wishlist = ", ".join(kid.wishlist) if kid.wishlist else "No specific items listed"
    return f"""You are Santa's magical gift recommendation assistant. Based on the child's profile, recommend 3–5 thoughtful, age-appropriate gifts that feel personal, imaginative, and exciting.

Kid Profile:
- Name: {kid.name}
- Age: {kid.age}
- Wishlist: {wishlist}

Your task:
1. Recommend 1-5 gifts (one short phrase each) that are highly relevant to the child's wishlist.
2. Each gift must be age-appropriate, safe, and appealing for a child of this age.
3. Take inspiration from the wishlist, but avoid repeating it unless it is genuinely relevant.
4. Ensure the gifts are fun, creative, and suitable for Santa to give.
5. Provide a warm, concise rationale (2–3 sentences).

Respond with a JSON object in this exact format:
{{
  "gifts": ["Gift 1", "Gift 2", "Gift 3"],
  "rationale": "2–3 sentence explanation"
}}
"""


def wish_prompt(kid: KidProfile, rec: GiftRecommendation) -> str:
    gifts = "\n".join(f"- {g}" for g in rec.gifts)
    moods = ", ".join(MOODS)
    return f"""You are Santa Claus writing a warm, magical, and age-appropriate holiday message to a child.

Kid Profile:
- Name: {kid.name}
- Age: {kid.age}

Recommended Gifts:
{gifts}

Write a personalized holiday wish that:
1. Addresses the child by name.
2. Mentions their age in a natural, encouraging way.
3. References the recommended gifts subtly and magically (no listing).
4. Uses a warm, gentle Santa tone.
5. Contains 2–4 sentences.
6. Does NOT include Santa's last name.
7. Ends with "Merry Christmas!" as the final sentence.

Also pick ONE mood tag for the background music from: {moods}.

Respond with a JSON object in this exact format:
{{
  "wish": "The personalized wish text here",
  "mood": "one of the mood tags"
}}
"""


def image_prompt(kid: KidProfile, rec: GiftRecommendation) -> str:
    """Illustration prompt. Object-centric, no faces or text — the card is animated later."""
    main_gift = rec.gifts[0] if rec.gifts else "a wrapped present"
    return f"""A magical Christmas storybook illustration, centered composition:
- The hero object: {main_gift}, beautifully illustrated, glowing softly, placed on snow under a starry night sky
- Around it: a small decorated Christmas tree, wrapped presents, twinkling lights, gentle falling snow
- Warm, vibrant colors, soft lighting, sparkles, a sense of wonder
- Whimsical children's-book art style, clean shapes, cinematic depth
- No people, no faces, no animals with faces, no text, no letters, no signatures, no copyrighted characters
"""
