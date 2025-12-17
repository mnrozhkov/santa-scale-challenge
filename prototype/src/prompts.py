"""Prompt generation functions for evaluation tasks."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import BaseModel


def generate_gift_recommendation_prompt(kid_profile: "BaseModel") -> str:
    """
    Generate prompt for gift recommendation with JSON output format.

    Args:
        kid_profile: KidProfile instance with name, age, and wishlist

    Returns:
        Formatted prompt string requesting JSON output
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
1. Recommend 1-5 gifts (one short phrase each) that are:
- Highly relevant to the child's wishlist
2. Each gift must be age-appropriate, safe, and appealing for a child of this age.
3. Take inspiration from the child's wishlist, but avoid repeating it unless it is genuinely relevant.
4. Ensure the gifts are fun, creative, and suitable for Santa to give.
5. Provide a warm, concise rationale (2–3 sentences) explaining why these gifts match the child's interests and age.

Respond with a JSON object in this exact format:
{{
  "gifts": ["Gift 1", "Gift 2", "Gift 3"],
  "rationale": "2–3 sentence explanation"
}}
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

Respond with a JSON object in this exact format:
{{
  "wish": "The personalized wish text here"
}}
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


def generate_gift_quality_judge_prompt(
    kid_profile: "BaseModel",
    response: str,
) -> str:
    """
    Generate LLM-as-a-judge prompt to evaluate gift recommendation quality with JSON output.

    Args:
        kid_profile: KidProfile instance
        response: Generated gift recommendation string

    Returns:
        A deterministic judge prompt string requesting JSON output
    """
    wishlist_str = ", ".join(kid_profile.wishlist) if kid_profile.wishlist else "None"

    return f"""You are an evaluator. Score the quality of a gift recommendation between 0.0 and 1.0.

CRITICAL FAILURES (result in score of 0.0):
- If gifts contain meta-instructions, formatting instructions, or system prompts (e.g., "We need to output JSON", "Gifts: 3-5 items", "Avoid repeating wishlist")
- If gifts are not actual gift items but instructions, placeholders, or explanations
- If the rationale contains meta-instructions or formatting instructions instead of explaining why gifts match the child
- If the output is clearly malformed or contains no valid gift recommendations
- If gifts are dangerous, unsafe, or inappropriate for the child's age

SCORING REFERENCE EXAMPLES:

Score 0.0 - Critical Failures:
- Meta-instructions: {{"gifts": ["You must provide JSON with a gifts array", "Ensure 3-5 items"], "rationale": "This is how the assistant should respond."}}
- Wrong structure: Plain text instead of JSON format
- Unsafe content: {{"gifts": ["High-powered chemical kit", "Real fireworks set"], "rationale": "These are exciting."}}

Score 0.1-0.3 - Low Quality:
- Generic, uncreative: {{"gifts": ["Gift card", "Chocolate box", "Generic toy"], "rationale": "These are common gifts that most kids like."}}
- Repeats wishlist with no insight: {{"gifts": ["doll", "art supplies", "books"], "rationale": "She said she likes these things so I repeated them."}}

Score 0.4-0.6 - Mediocre:
- Reasonable but generic: {{"gifts": ["Painting set", "Puzzle", "Storybook"], "rationale": "These are fun items many kids enjoy."}}
- Slight personalization but lacks creativity: {{"gifts": ["Basketball poster", "Basic headphones", "Intro science book"], "rationale": "These relate somewhat to his wishlist but are not very imaginative."}}

Score 0.7-1.0 - High Quality:
- Highly relevant to the child's wishlist (highest weight)
- Excellent personalization + creativity (second highest weight)
- Excellent STEM + activity alignment (third highest weight)
- Excellent quality and correctness of the output (fourth highest weight)
- Excellent personalization (fifth highest weight)

Your evaluation must consider ALL the following criteria equally:

1. Alignment to the child's interests
   - Gifts should reflect the wishlist AND extend it thoughtfully.
   - Penalize generic or boilerplate gifts that could apply to any child.

2. Creativity and originality
   - Gifts should show imagination, not just repeat obvious wishlist items.
   - Penalize recommendations that are too common, predictable, or unoriginal.

3. Appropriateness for age and safety
   - Gifts must be suitable for the child's developmental stage.
   - Penalize items that are too advanced, too childish, or potentially unsafe.

4. Quality and correctness of the output
   - Gifts list should be 3–5 items, non-repetitive, and domain-appropriate.
   - Rationale should be coherent and tied specifically to the child's interests.
   - Penalize formatting errors, meta-instructions, or invalid content.

5. Personalization
   - Recommendation must clearly connect to the child's *specific* profile.
   - Penalize outputs that could be reused for any other child.

Kid Profile:
Name: {kid_profile.name}
Age: {kid_profile.age}
Wishlist: {wishlist_str}

Recommendation to evaluate:
---
{response}
---

First, check for CRITICAL FAILURES. If any are present, score MUST be 0.0.
If no critical failures, evaluate based on the 5 criteria above, using the reference examples to calibrate your scoring.

Respond with a JSON object in this exact format:
{{
  "quality_score": 0.85,
  "rationale": "Brief explanation of the score based on the criteria above. If critical failure detected, explain which one."
}}
"""


def generate_wish_quality_judge_prompt(
    kid_profile: "BaseModel",
    response: str,
) -> str:
    """
    Generate a deterministic LLM-as-a-judge prompt for evaluating holiday wish quality.
    Produces JSON output with a score and rationale.
    """
    return f"""
You are an evaluator. Score the quality of a holiday wish between 0.0 and 1.0.

CRITICAL FAILURES (result in score of 0.0):
- If the wish contains meta-instructions, formatting instructions, or system prompts
- If the output is not a wish text but JSON, instructions, or placeholders
- If the wish contains dangerous, inappropriate, or harmful content
- If the wish is clearly malformed or contains no valid wish content

SCORING REFERENCE EXAMPLES:

Score 0.0 - Critical Failures:
- Meta-instructions: "Write a 2-sentence Christmas wish here that mentions the child's hobbies."
- Wrong structure: {{"wish": "You should generate a warm holiday message."}}
- Unsafe content: "Noah, I hope this Christmas you pull dangerous pranks and try daring experiments with real chemicals. It will be so exciting!"

Score 0.1-0.3 - Low Quality:
- Generic, impersonal: "Hope you have a good holiday season. Best wishes from Santa."
- Unrelated, bland: "Have a great winter and make sure to stay warm. Bye."

Score 0.4-0.6 - Mediocre:
- Some warmth but generic: "Wishing you a fun and cheerful holiday! I hope you enjoy your gifts and have a happy Christmas."
- Mild personalization but low creativity: "Dear Noah, I hope you have a great Christmas filled with sports, music, and learning. Enjoy the season!"

Score 0.7-1.0 - High Quality:
- Excellent personalization: "Dear Emma, I've seen how brightly your imagination shines! I hope this holiday brings you new colors to paint with, new stories to explore, and magical moments to share. Keep creating your beautiful world—Santa is so proud of you! 🎨✨"
- Excellent for STEM + adventure kid: "Noah, your curiosity and energy light up the North Pole! May this holiday spark bold experiments, exciting games, and joyful moments with friends. Keep exploring and dreaming big—Santa knows amazing discoveries await you! 🔬🏀🌟"
- Heartwarming + personalized: "Lucas, I've loved watching you build new worlds piece by piece and race toward every adventure. This Christmas, may your imagination soar higher than ever and your journeys—indoors or outdoors—be filled with joy. Keep creating and exploring! 🎁🚴✨"

Your evaluation must consider all criteria equally:

1. Personalization
   - The wish must clearly relate to the child's specific name, age, and interests.
   - Penalize generic or reusable wishes that could apply to any child.

2. Warmth and Tone
   - Should feel kind, uplifting, and authentically Santa-like.
   - Penalize overly formal, robotic, or emotionally flat text.

3. Age-appropriateness
   - Language should match the developmental stage of a {kid_profile.age}-year-old.
   - Penalize advanced vocabulary, confusing metaphors, or babyish phrasing.

4. Magic and Imagination
   - Wish should evoke holiday magic or charm.
   - Penalize dull, literal, or purely informational content.

5. Safety and Content Correctness
   - Must contain no harmful, scary, or inappropriate content.
   - Must not mention gifts the kid should NOT get or guarantee outcomes.

Wish to evaluate:
---
{response}
---

Kid Profile:
Name: {kid_profile.name}
Age: {kid_profile.age}

First, check for CRITICAL FAILURES. If any are present, score MUST be 0.0.
If no critical failures, evaluate based on the 5 criteria above, using the reference examples to calibrate your scoring.

Return ONLY a JSON object in this format:
{{
  "quality_score": 0.0,
  "rationale": "Brief justification for the score. If critical failure detected, explain which one."
}}
"""


def generate_image_quality_judge_prompt(
    prompt: str,
    image_url: str,
    kid_profile: "BaseModel",
) -> str:
    """
    Improved LLM-as-a-judge prompt for evaluating image quality with weighted criteria.
    """
    return f"""
You are an expert evaluator for children's holiday illustrations. Evaluate the quality of the generated image using the criteria below.

YOUR TASK:
Review the following:
- The *intended image prompt*
- The *actual generated image* at the provided URL
- The *kid profile* (age-appropriateness matters)

Then provide a JSON response containing:
1. "quality_score": A float between 0.0 and 1.0
2. "rationale": A short explanation referencing the scoring criteria

-------------------------
IMAGE GENERATION PROMPT
-------------------------
{prompt}

-------------------------
GENERATED IMAGE
-------------------------
Image URL: {image_url}

-------------------------
KID PROFILE
-------------------------
Name: {kid_profile.name}
Age: {kid_profile.age}

-------------------------
EVALUATION CRITERIA
(Weighted Scoring)
-------------------------

1. **Visual Quality & Aesthetic Appeal** (0.3)
   - Is the illustration visually appealing?
   - Is the composition clear?
   - Are artifacts, distortions, or strange body features avoided?

2. **Faithfulness to the Prompt** (0.3)
   - Image does not contain any text, signatures, or writing anywhere in the image
   - Does the image depict the intended main gift?
   - Does it match the holiday / magical / festive style?
   - Does it reflect key elements listed in the prompt (e.g., sparkles, warm lighting, decorations)?

3. **Age-Appropriateness & Child-Friendliness** (0.2)
   - Is the content suitable for a child of this age?
   - Avoids scary, dark, violent, or unsafe elements.

4. **Holiday Theme, Magic, Warmth** (0.2)
   - Does the image convey a joyful Christmas atmosphere?
   - Does it feel magical, whimsical, or storybook-like?
   - Contains cheerful, positive, friendly visual themes.

-------------------------
OUTPUT FORMAT (STRICT)
-------------------------
Respond **only** with a valid JSON object in this exact structure:

{{
  "quality_score": 0.0,
  "rationale": "Explain why you assigned this score based on the criteria."
}}

Your score must reflect the weighted criteria above.
    """
