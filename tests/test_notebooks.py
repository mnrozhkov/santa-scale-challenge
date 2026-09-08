"""Research + workshop notebooks live under notebooks/; no prototype/src imports."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ROOT / "notebooks"

BANNED = ("from src.", "import src", "prototype/src", "santa_demo.proto")
RESEARCH = (
    "10_prototype.ipynb",
    "11_gift_rec_eval.ipynb",
    "12_wish_model_eval.ipynb",
    "13_image_generation_eval.ipynb",
    "14_benchmark_llm.ipynb",
)


def _cells(path: Path) -> str:
    nb = json.loads(path.read_text(encoding="utf-8"))
    parts = []
    for cell in nb.get("cells", []):
        src = cell.get("source", [])
        parts.append("".join(src) if isinstance(src, list) else str(src))
    return "\n".join(parts)


def test_prototype_tree_is_gone() -> None:
    assert not (ROOT / "prototype").exists()
    assert not (ROOT / "santa_demo" / "proto.py").exists()


def test_notebooks_do_not_import_prototype_src() -> None:
    ipynbs = sorted(NOTEBOOKS.glob("*.ipynb"))
    assert ipynbs
    offenders = []
    for path in ipynbs:
        text = _cells(path)
        for needle in BANNED:
            if needle in text:
                offenders.append(f"{path.name}: {needle}")
    assert offenders == [], offenders


def test_research_notebooks_import_santa() -> None:
    for name in RESEARCH:
        text = _cells(NOTEBOOKS / name)
        assert "santa." in text, name


def test_notebook_code_cells_compile() -> None:
    for path in sorted(NOTEBOOKS.glob("*.ipynb")):
        nb = json.loads(path.read_text(encoding="utf-8"))
        for i, cell in enumerate(nb.get("cells", [])):
            if cell.get("cell_type") != "code":
                continue
            src = "".join(cell.get("source") or [])
            # magics / shell
            lines = [
                ln for ln in src.splitlines() if not ln.startswith("%") and not ln.startswith("!")
            ]
            body = "\n".join(lines).strip()
            if not body:
                continue
            compile(body, f"{path.name}:{i}", "exec")
