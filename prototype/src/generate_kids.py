#!/usr/bin/env python3
"""Generate CSV file with kid profiles for Santa workflow.

Creates a CSV file with the expected format:
- Column 0: Timestamp
- Column 1: Your Name (Optional)
- Column 2: What did you want for Christmas as a child?
"""

import argparse
import csv
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


def get_first_names() -> list[str]:
    """Return list of common first names for kids."""
    return [
        "Alice",
        "Bob",
        "Charlie",
        "Diana",
        "Emma",
        "Frank",
        "Grace",
        "Henry",
        "Iris",
        "Jack",
        "Kate",
        "Leo",
        "Mia",
        "Noah",
        "Olivia",
        "Paul",
        "Quinn",
        "Ruby",
        "Sam",
        "Tina",
        "Alex",
        "Bella",
        "Carter",
        "Daisy",
        "Ethan",
        "Fiona",
        "George",
        "Hannah",
        "Ian",
        "Julia",
        "Kevin",
        "Lily",
        "Max",
        "Nora",
        "Owen",
        "Penny",
        "Rose",
        "Seth",
        "Tara",
        "Victor",
        "Wendy",
        "Xander",
        "Yara",
        "Zoe",
        "Adam",
        "Brooke",
        "Caleb",
        "Eva",
        "Felix",
        "Gina",
        "Hugo",
        "Isla",
        "Jake",
        "Kara",
        "Liam",
        "Maya",
        "Nate",
        "Opal",
        "Peter",
        "Riley",
        "Sara",
        "Tom",
        "Uma",
        "Vera",
        "Will",
        "Xara",
        "Yuki",
        "Zara",
    ]


def get_wishlist_items() -> list[str]:
    """Return list of realistic wishlist items for kids."""
    return [
        "Lego set",
        "space toys",
        "astronaut costume",
        "Dinosaurs",
        "puzzles",
        "science kit",
        "Unicorns",
        "drawing supplies",
        "art set",
        "Superhero action figures",
        "comic books",
        "Princess dress",
        "tiara",
        "fairy wand",
        "Remote control car",
        "racing track",
        "Musical instruments",
        "piano",
        "guitar",
        "Building blocks",
        "construction toys",
        "tools",
        "Dolls",
        "dollhouse",
        "tea set",
        "Video games",
        "gaming console",
        "headphones",
        "Horse toys",
        "stable playset",
        "riding boots",
        "Robots",
        "coding kit",
        "tech gadgets",
        "Art supplies",
        "paint set",
        "easel",
        "Sports equipment",
        "basketball",
        "soccer ball",
        "Books",
        "reading lamp",
        "bookcase",
        "Train set",
        "model cars",
        "tracks",
        "Magic kit",
        "science experiments",
        "microscope",
        "Jewelry making kit",
        "beads",
        "crafts",
        "Board games",
        "chess set",
        "Dance shoes",
        "ballet outfit",
        "music player",
        "Bike",
        "skateboard",
        "roller skates",
        "Telescope",
        "binoculars",
        "nature guide",
        "Cooking set",
        "baking supplies",
        "recipe book",
        "Camera",
        "photo album",
        "scrapbook",
        "star chart",
        "planetarium",
        "Sewing kit",
        "fabric",
        "patterns",
        "Karaoke machine",
        "microphone",
        "speakers",
        "Trampoline",
        "jump rope",
        "hula hoop",
        "Fishing rod",
        "tackle box",
        "fishing guide",
        "Camping gear",
        "tent",
        "sleeping bag",
        "Drone",
        "RC helicopter",
        "flying toys",
        "3D printer",
        "filament",
        "design software",
    ]


def generate_timestamp(index: int, base_date: datetime) -> str:
    """Generate a timestamp string for a given index.

    Args:
        index: Index of the kid (0-based)
        base_date: Base date to start from

    Returns:
        Formatted timestamp string
    """
    days_offset = index % 25
    hours_offset = (index // 25) % 24
    minutes_offset = index % 60
    timestamp = base_date + timedelta(days=days_offset, hours=hours_offset, minutes=minutes_offset)
    return timestamp.strftime("%Y/%m/%d %I:%M:%S %p CET")


def generate_name(index: int, first_names: list[str]) -> str:
    """Generate a name for a kid.

    Args:
        index: Index of the kid (0-based)
        first_names: List of available first names

    Returns:
        Generated name
    """
    if index < len(first_names):
        return first_names[index]
    base_name = random.choice(first_names)
    return f"{base_name} {index + 1}"


def generate_wishlist(wishlist_items: list[str], min_items: int = 1, max_items: int = 4) -> str:
    """Generate a wishlist string with random items.

    Args:
        wishlist_items: List of available wishlist items
        min_items: Minimum number of items
        max_items: Maximum number of items

    Returns:
        Comma-separated wishlist string
    """
    num_items = random.randint(min_items, max_items)
    selected_items = random.sample(wishlist_items, min(num_items, len(wishlist_items)))
    return ", ".join(selected_items)


def generate_kids_csv(
    output_path: Path,
    num_kids: int,
    base_date: Optional[datetime] = None,
) -> None:
    """Generate a CSV file with kid profiles.

    Args:
        output_path: Path to output CSV file
        num_kids: Number of kids to generate
        base_date: Base date for timestamps (defaults to Dec 1, 2024)

    Raises:
        ValueError: If num_kids is less than 1
    """
    if num_kids < 1:
        raise ValueError("Number of kids must be at least 1")

    if base_date is None:
        base_date = datetime(2024, 12, 1, 10, 0, 0)

    first_names = get_first_names()
    wishlist_items = get_wishlist_items()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "Timestamp",
                "Your Name (Optional)",
                "What did you want for Christmas as a child?",
            ]
        )

        for i in range(num_kids):
            timestamp = generate_timestamp(i, base_date)
            name = generate_name(i, first_names)
            wishlist = generate_wishlist(wishlist_items)

            writer.writerow([timestamp, name, wishlist])


def main() -> int:
    """Main entrypoint for kid profile generator."""
    parser = argparse.ArgumentParser(
        description="Generate CSV file with kid profiles for Santa workflow"
    )
    parser.add_argument(
        "num_kids",
        type=int,
        help="Number of kids to generate",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="prototype/data/santa_workflow/kids.csv",
        help="Output CSV file path (default: prototype/data/santa_workflow/kids.csv)",
    )
    parser.add_argument(
        "--base-date",
        type=str,
        default=None,
        help="Base date for timestamps in format YYYY-MM-DD (default: 2024-12-01)",
    )

    args = parser.parse_args()

    if args.num_kids < 1:
        print(f"Error: Number of kids must be at least 1, got {args.num_kids}", file=sys.stderr)
        return 1

    base_date = None
    if args.base_date:
        try:
            base_date = datetime.strptime(args.base_date, "%Y-%m-%d")
            base_date = base_date.replace(hour=10, minute=0, second=0)
        except ValueError as e:
            print(f"Error: Invalid date format: {e}", file=sys.stderr)
            return 1

    output_path = Path(args.output)

    try:
        generate_kids_csv(output_path, args.num_kids, base_date)
        print(f"✅ Generated {args.num_kids} kid profiles in {output_path}")
        return 0
    except Exception as e:
        print(f"Error: Failed to generate CSV: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

