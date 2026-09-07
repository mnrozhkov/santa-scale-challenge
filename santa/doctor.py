"""``santa doctor`` — one screen: what works, what to fix.

Each check returns a ``Check``; the CLI renders a table and exits non-zero if any
*required* check failed. A role whose primary fails but whose fallback answers is a
warning, not a failure. Probes are short (5 s) so the command finishes fast in a tent.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import requests  # type: ignore[import-untyped]

from santa.config import REPO_ROOT, ConfigError, RoleConfig, Settings, fallback_policy

PROBE_TIMEOUT_S = 5
PROBED_ROLES = ("llm", "image", "video", "audio")
REQUIRED_ROLES = ("llm", "image")  # video/audio are Step 7; missing them is a SKIP


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    fix: str = ""
    required: bool = True
    warn: bool = False  # ok=False but a fallback covers it

    @property
    def status(self) -> str:
        if self.ok:
            return "OK"
        if self.warn:
            return "WARN"
        return "FAIL" if self.required else "SKIP"


Probe = Callable[[str, dict[str, str]], tuple[int, str]]


def _http_get(url: str, headers: dict[str, str]) -> tuple[int, str]:
    resp = requests.get(url, headers=headers, timeout=PROBE_TIMEOUT_S)
    return resp.status_code, resp.text[:200]


def _probe_models(cfg: RoleConfig, probe: Probe) -> tuple[bool, str, str]:
    if cfg.adapter == "local_tracks":
        raw = cfg.options.get("dir", "data/fallback/moods")
        path = Path(raw) if Path(raw).is_absolute() else REPO_ROOT / raw
        exists = path.is_dir() and any(p.suffix == ".mp3" for p in path.iterdir())
        return (
            exists,
            f"{path} {'has tracks' if exists else 'is empty'}",
            "Run scripts/make_mood_bank.py",
        )
    headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
    start = time.time()
    try:
        code, body = probe(f"{cfg.v1}/models", headers)
    except requests.exceptions.SSLError:
        return (
            False,
            "TLS handshake failed (SSLError)",
            (
                "Corporate proxy / custom CA? The CLI trusts the OS cert store (truststore); "
                "if it persists: export SSL_CERT_FILE=/path/to/corp-ca.pem"
            ),
        )
    except requests.RequestException as exc:
        return (
            False,
            f"unreachable: {exc.__class__.__name__}",
            "Check the URL; is the endpoint RUNNING?",
        )
    ms = round((time.time() - start) * 1000)
    if code == 200:
        return True, f"/v1/models 200 in {ms} ms", ""
    if code in (401, 403):
        return False, f"/v1/models {code}", "Key/token rejected — copy it again into .env"
    if code == 502:
        return (
            False,
            "/v1/models 502 — RUNNING but weights still loading",
            "Wait 1–5 min and re-run doctor",
        )
    return (
        False,
        f"/v1/models {code}: {body[:80]}",
        "Unexpected response — check the URL points at the endpoint root",
    )


def run_checks(settings: Settings | None = None, *, probe: Probe = _http_get) -> list[Check]:
    checks: list[Check] = []
    try:
        settings = settings or Settings.load()
        policy = fallback_policy()
        checks.append(
            Check(
                "config/models.yaml",
                True,
                f"roles: {', '.join(settings.role_names)} · fallback={policy}",
            )
        )
    except ConfigError as exc:
        return [
            Check(
                "config",
                False,
                str(exc),
                "Restore config/models.yaml from git / fix SANTA_FALLBACK",
            )
        ]

    env_path = REPO_ROOT / ".env"
    checks.append(
        Check(
            ".env",
            env_path.is_file(),
            "found" if env_path.is_file() else "missing",
            "cp .env.example .env and fill the Step 0 block",
            required=False,
        )
    )

    for role in PROBED_ROLES:
        required = role in REQUIRED_ROLES
        # fallback first, so the primary row can be downgraded to WARN
        fb = settings.fallback(role) if policy != "off" else None
        fb_ok, fb_detail, fb_fix = _probe_models(fb, probe) if fb else (False, "", "")

        try:
            cfg = settings.role(role)
            ok, detail, fix = _probe_models(cfg, probe)
        except ConfigError as exc:
            ok, detail, cfg = False, str(exc), None
            fix = (
                "Deploy the endpoint (Step 1) and paste its URL + token into .env — or set OPENAI_API_KEY "
                "so the fallback answers"
            )
        covered = (not ok) and fb_ok
        name = f"{role} · {cfg.model}" if cfg else role
        checks.append(
            Check(
                name,
                ok,
                detail,
                fix if not covered else f"{fix} (fallback covers it)".strip(),
                required=required and not covered,
                warn=covered,
            )
        )

        if settings.has_fallback(role):
            if fb is None:
                why = "disabled (SANTA_FALLBACK=off)" if policy == "off" else "not configured"
                checks.append(
                    Check(
                        f"{role} fallback", False, why, "Set OPENAI_API_KEY in .env", required=False
                    )
                )
            else:
                checks.append(
                    Check(
                        f"{role} fallback · {fb.model or fb.adapter}",
                        fb_ok,
                        fb_detail,
                        fb_fix,
                        required=False,
                    )
                )

    # batch / publish plumbing (presence only; verified live by `santa batch`)
    service = os.environ.get("SANTA_SERVICE_URL", "").strip()
    checks.append(
        Check(
            "service · SANTA_SERVICE_URL",
            bool(service),
            service or "not set → cards run locally",
            "Deploy santa-service (docker/service.Dockerfile) and set its URL",
            required=False,
        )
    )
    for var, fix in (
        (
            "NEBIUS_IAM_TOKEN",
            "nebius iam get-access-token → NEBIUS_IAM_TOKEN in .env (only for `santa batch`)",
        ),
        ("NEBIUS_PROJECT_ID", "Set NEBIUS_PROJECT_ID in .env (only for `santa batch`)"),
        ("NEBIUS_BUCKET_ID", "Set NEBIUS_BUCKET_ID in .env (only for `santa batch`)"),
    ):
        val = os.environ.get(var, "").strip()
        checks.append(
            Check(f"jobs · {var}", bool(val), "set" if val else "not set", fix, required=False)
        )
    return checks


def failed(checks: list[Check]) -> bool:
    return any(c.required and not c.ok for c in checks)
