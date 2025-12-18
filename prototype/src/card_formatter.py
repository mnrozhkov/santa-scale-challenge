"""Card formatting functions for generating HTML and PNG postcards."""

import os
import re
import shutil
import tempfile
from pathlib import Path

from src.data_scheme import CardImage, GiftCard, GiftRecommendation, KidProfile, Wish


def format_gift_card(
    kid_profile: KidProfile,
    gift_recommendation: GiftRecommendation,
    wish: Wish,
    card_image: CardImage,
) -> str:
    """
    Generates a clean, centered postcard suitable for html2image PNG export.

    - The card fills the entire viewport → border is always visible
    - No wrapper that makes the card float smaller than the frame
    - Warm non-white background with consistent rounded corners
    - Perfect for A4 landscape rendering (ratio handled by screenshot size)

    Args:
        kid_profile: Profile of the child
        gift_recommendation: Gift recommendation data
        wish: Personalized wish text
        card_image: Generated card image

    Returns:
        HTML template string for the postcard
    """
    # Sanitize wish text
    wish_text = wish.text.strip()
    wish_text = re.sub(r"Santa\s+\w+", "Santa", wish_text, flags=re.IGNORECASE)

    html_template = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<link href="https://fonts.googleapis.com/css2?family=Mountains+of+Christmas:wght@400;700&family=Caveat:wght@400;600;700&family=Dancing+Script:wght@400;600;700&display=swap" rel="stylesheet">

<style>
    html, body {{
        margin: 0;
        padding: 0;
        width: 100%;
        height: 100%;
    }}

    /* The postcard itself will fill the screenshot area */
    .card {{
        width: 100%;
        height: 100%;
        box-sizing: border-box;

        background: #fffaf2; /* warm ivory */
        border: 14px solid #b30000;
        border-radius: 28px;

        display: flex;
        overflow: hidden;
        position: relative;

        box-shadow: 0 0 28px rgba(0, 0, 0, 0.16);
    }}

    /* Snowflake animation */
    @keyframes twinkle {{
        0%, 100% {{ opacity: 0.9; transform: translateY(0px); }}
        50% {{ opacity: 0.4; transform: translateY(-6px); }}
    }}

    .snowflake {{
        position: absolute;
        color: #cfe6ff;
        opacity: 0.7;
        font-size: 40px;
        pointer-events: none;
        animation: twinkle 3s ease-in-out infinite;
    }}

    /* Text area */
    .right {{
        width: 50%;
        padding: 60px 50px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        text-align: center;
        font-family: 'Caveat', cursive;
        color: #2c3e50;
    }}

    .right h1 {{
        font-family: 'Mountains of Christmas', cursive;
        color: #b00000;
        font-size: 58px;
        margin-bottom: 30px;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
    }}

    .right p {{
        font-size: 58px;
        line-height: 1.6;
        max-width: 90%;
    }}

    .signature {{
        margin-top: 50px;
        font-size: 48px;
        font-family: 'Dancing Script', cursive;
        color: #b00000;
        font-weight: 700;
    }}

</style>
</head>

<body>

<div class="card">

    <!-- Snowflakes -->
    <div class="snowflake" style="top:20px; left:20px;">❄️</div>
    <div class="snowflake" style="top:40px; right:40px; animation-delay:1s;">❄️</div>
    <div class="snowflake" style="bottom:300px; left:1500px; animation-delay:1s;">❄️</div>
    <div class="snowflake" style="bottom:40px; right:60px; animation-delay:2s;">✦</div>

    <!-- Image column -->
    <div style="width:50%; padding:40px; display:flex; justify-content:center; align-items:center;">
        <img src="{card_image.image_url}"
             style="width:100%; border-radius:18px; box-shadow:0 4px 10px rgba(0,0,0,0.15);" />
    </div>

    <!-- Text column -->
    <div class="right">
        <h1>To: {kid_profile.name}</h1>

        <p>{wish_text}</p>

        <div class="signature">— Santa 🎅</div>
    </div>

</div>

</body>
</html>
"""
    return html_template


def find_chrome_executable() -> str | None:
    """
    Find Chrome/Chromium executable on the system.
    
    Returns:
        Path to Chrome/Chromium executable, or None if not found
    """
    # Common Chrome/Chromium executable paths
    possible_paths = [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/snap/bin/chromium",
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        shutil.which("chromium-browser"),
        shutil.which("chromium"),
    ]
    
    for path in possible_paths:
        if path and Path(path).exists() and os.access(path, os.X_OK):
            return path
    
    return None


def create_complete_gift_card(
    kid_profile: KidProfile,
    gift_recommendation: GiftRecommendation,
    wish: Wish,
    card_image: CardImage,
    output_dir: str | None = "prototype/cards",
    width: int = 2400,
    height: int = 1697,
) -> GiftCard:
    """
    Create a complete gift card and save as PNG image.

    Ensures full card including borders is captured.

    Args:
        kid_profile: Profile of the child
        gift_recommendation: Gift recommendation data
        wish: Personalized wish text
        card_image: Generated card image
        output_dir: Directory to save PNG file (None to skip saving)
        width: Card width in pixels
        height: Card height in pixels

    Returns:
        GiftCard object with rendered_url pointing to PNG file

    Raises:
        ValueError: If html2image is not installed or PNG creation fails
    """
    # Generate HTML
    html_content = format_gift_card(
        kid_profile=kid_profile,
        gift_recommendation=gift_recommendation,
        wish=wish,
        card_image=card_image,
    )

    # Save PNG file with format: "kid_name-card_id.png"
    png_path = None
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

        # Sanitize kid name for filename
        safe_kid_name = re.sub(r"[^\w\s-]", "", kid_profile.name).strip()
        safe_kid_name = re.sub(r"[-\s]+", "-", safe_kid_name)

        # Create filename: "kid_name-card_id.png"
        png_filename = f"{safe_kid_name}-{card_image.id}.png"
        png_path = os.path.join(output_dir, png_filename)

        # Export HTML to PNG using html2image
        try:
            from html2image import Html2Image

            screenshot_width = width
            screenshot_height = height

            # Find Chrome/Chromium executable
            chrome_path = find_chrome_executable()
            if chrome_path:
                # Create Html2Image instance with explicit Chrome path
                hti = Html2Image(
                    size=(screenshot_width, screenshot_height),
                    browser_executable=chrome_path,
                )
            else:
                # Try without explicit path (html2image will try to find it)
                hti = Html2Image(size=(screenshot_width, screenshot_height))

            # Save HTML to temp file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".html", delete=False, encoding="utf-8"
            ) as tmp_file:
                tmp_file.write(html_content)
                tmp_html = tmp_file.name

            # Convert to PNG - use exact size
            hti.screenshot(
                html_file=tmp_html,
                save_as=png_filename,
                size=(screenshot_width, screenshot_height),
            )

            # Move file to output directory
            temp_png = png_filename
            if os.path.exists(temp_png):
                shutil.move(temp_png, png_path)

            # Clean up temp HTML file
            os.unlink(tmp_html)

        except ImportError as e:
            raise ValueError(
                "html2image is required for PNG export. Install with: pip install html2image"
            ) from e
        except Exception as e:
            raise ValueError(f"Failed to create PNG: {str(e)}") from e

    # Create GiftCard object
    gift_card = GiftCard(
        kid_id=kid_profile.id,
        recommendation_id=gift_recommendation.id,
        wish_id=wish.id,
        image_id=card_image.id,
        rendered_url=png_path,
        status="completed",
    )

    return gift_card
