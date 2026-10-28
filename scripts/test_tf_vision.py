#!/usr/bin/env python3
"""Smoke-test Token Factory vision models used by the agent image judge.

Hits each TF VLM with the real ``evaluate_image`` prompt + a bundled card PNG.
No OpenAI fallback — a failure here means the TF model cannot judge images.

Usage:
  uv run python scripts/test_tf_vision.py
  uv run python scripts/test_tf_vision.py --model moonshotai/Kimi-K3
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

from santa.agent.judge import _parse_image_eval, image_judge_prompt
from santa.config import REPO_ROOT, Settings
from santa.models import AdapterError, ChatAdapter
from santa.schemas import GiftRecommendation, KidProfile

ALT_TF_VLM = "zai-org/GLM-5.3-Flash"
DEFAULT_IMAGE = REPO_ROOT / "data" / "fallback" / "cards" / "card-01.png"
KID = KidProfile(id="probe", name="Mia", age=6, wishlist=["a wooden train set"])
REC = GiftRecommendation(
    kid_id=KID.id,
    gifts=["a wooden train set"],
    rationale="smoke test",
    model_version="probe",
)


def _models(settings: Settings, extra: list[str]) -> list[str]:
    primary = (settings.models.roles["vlm"].model or "").strip()
    seen: list[str] = []
    for name in (primary, ALT_TF_VLM, *extra):
        if name and name not in seen:
            seen.append(name)
    return seen


def _probe(vlm: ChatAdapter, png: bytes) -> dict[str, Any]:
    """Cheap vision check: must name something that is actually in the card."""
    return vlm.generate_json_vision(
        'Look at this Christmas card. Return JSON: {"objects":[up to 5 short nouns]}',
        [png],
    )


def _run_one(model: str, png: bytes, settings: Settings) -> dict[str, Any]:
    row: dict[str, Any] = {"model": model, "ok": False, "error": None, "ms": 0}
    t0 = time.perf_counter()
    try:
        cfg = settings.role("vlm").model_copy(update={"model": model})
        vlm = ChatAdapter(cfg)
        seen = _probe(vlm, png)
        objects = seen.get("objects") if isinstance(seen, dict) else None
        row["objects"] = objects if isinstance(objects, list) else []
        data = vlm.generate_json_vision(image_judge_prompt(KID, REC), [png])
        ev = _parse_image_eval(data, judge_model=model)
        row["decision"] = ev.decision
        row["score"] = ev.score
        row["reasons"] = ev.reasons
        row["fix"] = ev.fix
        row["ms"] = round((time.perf_counter() - t0) * 1000)
        row["tokens_in"] = vlm.last_metrics.get("tokens_in")
        row["tokens_out"] = vlm.last_metrics.get("tokens_out")
        row["ok"] = ev.decision in ("PASS", "RETRY")
    except AdapterError as exc:
        row["ms"] = round((time.perf_counter() - t0) * 1000)
        row["error"] = str(exc)
    except Exception as exc:  # noqa: BLE001 — live smoke test, print anything
        row["ms"] = round((time.perf_counter() - t0) * 1000)
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def _line(row: dict[str, Any]) -> str:
    if not row["ok"]:
        return f"FAIL  {row['model']}  {row['ms']}ms  {row['error']}"
    objects = ", ".join(str(o) for o in row.get("objects") or []) or "—"
    reasons = "; ".join(row["reasons"]) or "—"
    return (
        f"OK    {row['model']}  {row['ms']}ms  "
        f"{row['decision']} {row['score']}  objects=[{objects}]  {reasons}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=str, default=str(DEFAULT_IMAGE))
    parser.add_argument("--model", action="append", default=[], help="Extra TF model id")
    args = parser.parse_args(argv)

    settings = Settings.load()
    if not (os.environ.get("TOKEN_FACTORY_API_KEY") or "").strip():
        print("TOKEN_FACTORY_API_KEY is not set — cannot hit Token Factory.", file=sys.stderr)
        return 1

    png_path = Path(args.image)
    if not png_path.is_file():
        print(f"image not found: {png_path}", file=sys.stderr)
        return 1
    png = png_path.read_bytes()
    models = _models(settings, args.model)
    print(f"image: {png_path} ({len(png)} bytes)")
    print(f"models: {', '.join(models)}")
    print(f"kid: {KID.name}, {KID.age} · gift: {REC.gifts[0]}")
    print()

    rows = [_run_one(model, png, settings) for model in models]
    for row in rows:
        print(_line(row))
    failed = [r["model"] for r in rows if not r["ok"]]
    print()
    if failed:
        print(f"{len(failed)}/{len(rows)} failed: {', '.join(failed)}")
        return 1
    print(f"{len(rows)}/{len(rows)} Token Factory vision models answered with judge JSON.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
