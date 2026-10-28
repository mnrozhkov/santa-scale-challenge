"""JSONL + optional callback tracer for Experiment B."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Tracer:
    """Append-only events.jsonl; optional ``on_event`` for Rich / SSE."""

    def __init__(
        self,
        path: Path | str | None = None,
        *,
        run_id: str,
        mode: str = "agent",
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.run_id = run_id
        self.mode = mode
        self.path = Path(path) if path else None
        self.on_event = on_event
        self._lock = threading.Lock()
        self.events: list[dict[str, Any]] = []
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("", encoding="utf-8")

    def emit(self, event: str, *, kid_id: str | None = None, **fields: Any) -> dict[str, Any]:
        row: dict[str, Any] = {
            "ts": _now(),
            "run_id": self.run_id,
            "mode": self.mode,
            "event": event,
            **fields,
        }
        if kid_id is not None:
            row["kid_id"] = kid_id
        with self._lock:
            self.events.append(row)
            if self.path is not None:
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, default=str) + "\n")
        if self.on_event is not None:
            self.on_event(row)
        return row
