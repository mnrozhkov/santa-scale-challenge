#!/usr/bin/env python3
"""Script to export all environment variables to a .env file."""

import os
from pathlib import Path


def escape_env_value(value: str) -> str:
    """Escape special characters in environment variable values for .env format."""
    # If value contains spaces, quotes, or special chars, wrap in quotes
    if any(char in value for char in [" ", '"', "'", "$", "\\", "\n", "\r"]):
        # Escape backslashes and quotes
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def export_env_to_file(output_path: Path, filter_prefix: str | None = None) -> None:
    """
    Export all environment variables to a .env file.

    Args:
        output_path: Path to the output .env file
        filter_prefix: Optional prefix to filter environment variables (e.g., 'SANTA_')
    """
    env_vars = dict(os.environ)

    # Filter by prefix if provided
    if filter_prefix:
        env_vars = {k: v for k, v in env_vars.items() if k.startswith(filter_prefix)}

    # Sort by key for consistent output
    sorted_vars = sorted(env_vars.items())

    if not sorted_vars:
        print(
            f"No environment variables found{f' with prefix {filter_prefix}' if filter_prefix else ''}"
        )
        return

    # Write to file
    with open(output_path, "w", encoding="utf-8") as f:
        for key, value in sorted_vars:
            escaped_value = escape_env_value(value)
            f.write(f"{key}={escaped_value}\n")

    print(f"Exported {len(sorted_vars)} environment variable(s) to {output_path}")


def main() -> None:
    """Main entry point."""
    import sys

    # Default output file
    output_file = Path(".env")

    # Check for command line arguments
    filter_prefix: str | None = None
    if len(sys.argv) > 1:
        if sys.argv[1] == "--help" or sys.argv[1] == "-h":
            print("Usage: save_env.py [output_file] [--prefix PREFIX]")
            print("  output_file: Path to output .env file (default: .env)")
            print("  --prefix PREFIX: Only export variables starting with PREFIX")
            sys.exit(0)
        elif sys.argv[1] == "--prefix" and len(sys.argv) > 2:
            filter_prefix = sys.argv[2]
            if len(sys.argv) > 3:
                output_file = Path(sys.argv[3])
        else:
            output_file = Path(sys.argv[1])
            if len(sys.argv) > 2 and sys.argv[2] == "--prefix" and len(sys.argv) > 3:
                filter_prefix = sys.argv[3]

    export_env_to_file(output_file, filter_prefix)


if __name__ == "__main__":
    main()
