"""Generate ``data/kids.csv``: ``id,name,age,wishlist`` profiles for ``santa batch``."""

from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

from santa.config import REPO_ROOT
from santa.schemas import KidProfile

DEFAULT_KIDS_CSV = REPO_ROOT / "data" / "kids.csv"

# Workshop copy names Emma + telescope; keep these 24 as k01–k24.
_CANNED: tuple[tuple[str, str, int, str], ...] = (
    ("k01", "Emma", 7, "a telescope"),
    ("k02", "Lucas", 5, "a wooden train set"),
    ("k03", "Noah", 9, "a robot kit"),
    ("k04", "Sofia", 6, "a paint set"),
    ("k05", "Mika", 8, "a microscope"),
    ("k06", "Aino", 4, "a plush reindeer"),
    ("k07", "Oliver", 10, "a soccer ball"),
    ("k08", "Freya", 7, "ice skates"),
    ("k09", "Leo", 6, "building blocks"),
    ("k10", "Isla", 8, "a storybook"),
    ("k11", "Hugo", 5, "a sled"),
    ("k12", "Vera", 11, "a camera"),
    ("k13", "Nils", 9, "a chess set"),
    ("k14", "Astrid", 6, "a dollhouse"),
    ("k15", "Erik", 12, "a bicycle"),
    ("k16", "Linnea", 7, "art supplies"),
    ("k17", "Oscar", 8, "a drum"),
    ("k18", "Saga", 5, "a puzzle"),
    ("k19", "Viktor", 10, "a science kit"),
    ("k20", "Elsa", 6, "a toy kitchen"),
    ("k21", "Bjorn", 9, "a kite"),
    ("k22", "Maja", 7, "a diary"),
    ("k23", "Arvid", 8, "a flashlight"),
    ("k24", "Alma", 4, "a stuffed fox"),
)

# Lifted from prototype/src/generate_kids.py
FIRST_NAMES: tuple[str, ...] = (
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
)

WISHLIST_ITEMS: tuple[str, ...] = (
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
)


def _canned_profiles() -> list[KidProfile]:
    return [
        KidProfile(id=kid_id, name=name, age=age, wishlist=[wish])
        for kid_id, name, age, wish in _CANNED
    ]


def _random_kid(index: int, rng: random.Random) -> KidProfile:
    n_items = rng.randint(1, min(4, len(WISHLIST_ITEMS)))
    wish = ", ".join(rng.sample(WISHLIST_ITEMS, n_items))
    return KidProfile(
        id=f"k{index:02d}",
        name=rng.choice(FIRST_NAMES),
        age=rng.randint(1, 18),
        wishlist=[wish],
    )


def generate_kids(n: int, *, rng: random.Random) -> list[KidProfile]:
    """Return ``n`` profiles: canned k01–k24 first, then rng-filled k25+."""
    if n < 1:
        raise ValueError("n must be at least 1")
    canned = _canned_profiles()
    kids = canned[:n]
    for i in range(len(kids) + 1, n + 1):
        kids.append(_random_kid(i, rng))
    return kids


def generate_kids_csv(path: Path | str, n: int, *, rng: random.Random) -> None:
    """Write ``n`` profiles to ``path`` (columns: id, name, age, wishlist)."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["id", "name", "age", "wishlist"], lineterminator="\n"
        )
        writer.writeheader()
        for kid in generate_kids(n, rng=rng):
            writer.writerow(
                {
                    "id": kid.id,
                    "name": kid.name,
                    "age": kid.age,
                    "wishlist": ", ".join(kid.wishlist),
                }
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate CSV file with kid profiles for Santa workflow"
    )
    parser.add_argument(
        "num_kids",
        nargs="?",
        type=int,
        default=200,
        help="Number of kids to generate (default: 200)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_KIDS_CSV,
        help="Output CSV file path (default: data/kids.csv)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="RNG seed for reproducible generated rows",
    )
    args = parser.parse_args(argv)
    if args.num_kids < 1:
        print(f"Error: Number of kids must be at least 1, got {args.num_kids}", file=sys.stderr)
        return 1
    generate_kids_csv(args.output, args.num_kids, rng=random.Random(args.seed))
    print(f"Generated {args.num_kids} kid profiles in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
