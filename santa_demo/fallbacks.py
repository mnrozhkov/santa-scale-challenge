"""Committed fallback GiftCard rasters for animate and batch video."""

from __future__ import annotations

from pathlib import Path

FALLBACK_DIR = Path(__file__).resolve().parent / "data" / "fallback"


def list_fallback_pngs() -> list[Path]:
    pngs = sorted(FALLBACK_DIR.glob("card-*.png"))
    return pngs


def require_four_fallbacks() -> list[Path]:
    pngs = list_fallback_pngs()
    if len(pngs) < 4:
        raise FileNotFoundError(f"Need four fallback rasters in {FALLBACK_DIR}. Found {len(pngs)}.")
    return pngs[:4]
