"""CSV reader for parsing kid profiles from CSV files."""

import csv
from pathlib import Path

from src.data_scheme import KidProfile


def read_kid_profiles_from_csv(csv_path: str | Path, default_age: int = 10) -> list[KidProfile]:
    """
    Read kid profiles from CSV file and create KidProfile objects.

    CSV structure expected:
    - Column 0: Timestamp
    - Column 1: Your Name (Optional)
    - Column 2: What did you want for Christmas as a child?

    Args:
        csv_path: Path to CSV file
        default_age: Default age to use for all kids (CSV doesn't have age column)

    Returns:
        List of KidProfile objects

    Raises:
        FileNotFoundError: If CSV file doesn't exist
        ValueError: If CSV file is malformed or empty
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    kid_profiles: list[KidProfile] = []

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.reader(f)

        # Skip header row
        header = next(reader, None)
        if header is None:
            raise ValueError("CSV file is empty")

        # Process each row
        for row_num, row in enumerate(reader, start=2):  # Start at 2 (header + 1-based)
            if not row:
                continue

            # Extract fields
            # Column 0: Timestamp (ignored)
            # Column 1: Name (optional)
            # Column 2: Wishlist (what they wanted for Christmas)
            name = row[1].strip() if len(row) > 1 and row[1].strip() else f"Child {row_num}"
            wishlist_text = row[2].strip() if len(row) > 2 and row[2].strip() else ""

            # Parse wishlist - split by common delimiters (comma, semicolon, newline)
            wishlist: list[str] = []
            if wishlist_text:
                # Try splitting by various delimiters
                for delimiter in [",", ";", "\n", "|"]:
                    if delimiter in wishlist_text:
                        wishlist = [
                            item.strip() for item in wishlist_text.split(delimiter) if item.strip()
                        ]
                        break

                # If no delimiter found, treat entire text as single wish
                if not wishlist:
                    wishlist = [wishlist_text]

            # Create KidProfile with default age
            kid_profile = KidProfile(
                name=name,
                age=default_age,
                wishlist=wishlist,
            )

            kid_profiles.append(kid_profile)

    if not kid_profiles:
        raise ValueError("No kid profiles found in CSV file")

    return kid_profiles
