"""Project files: laptop-core deps, optional groups, no leaked secrets."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Spec D15 / issue 03 — expected names, not the implementation list.
CORE_PACKAGES = (
    "openai",
    "pydantic",
    "pydantic-settings",
    "pyyaml",
    "typer",
    "rich",
    "requests",
    "python-dotenv",
    "pillow",
    "jinja2",
    "imageio-ffmpeg",
    "boto3",
    "nebius",
    "pydantic-ai",
    "truststore",  # laptop TLS; santa.cli injects the OS cert store
)
DROPPED_FROM_CORE = (
    "mlflow",
    "pandas",
    "aiohttp",
    "html2image",
    "fastapi",
    "uvicorn",
)
SERVICE_PACKAGES = ("fastapi", "uvicorn", "jinja2", "python-multipart")
JOB_PACKAGES = ("torch", "diffusers", "transformers", "accelerate", "imageio-ffmpeg")
RESEARCH_PACKAGES = ("mlflow", "pandas", "aiohttp")
ENV_KEYS = (
    "TOKEN_FACTORY_API_KEY",
    "IMAGE_ENDPOINT_URL",
    "IMAGE_ENDPOINT_TOKEN",
    "VIDEO_ENDPOINT_URL",
    "VIDEO_ENDPOINT_TOKEN",
    "AUDIO_ENDPOINT_URL",
    "AUDIO_ENDPOINT_TOKEN",
    "OPENAI_API_KEY",
    "SANTA_FALLBACK",
    "SANTA_SERVICE_URL",
    "NEBIUS_IAM_TOKEN",
    "NEBIUS_PROJECT_ID",
    "NEBIUS_SUBNET_ID",
    "NEBIUS_BUCKET_ID",
    "NEBIUS_BUCKET_NAME",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_ENDPOINT_URL",
)
GITIGNORE_PATTERNS = (".env", "*.pkg", "data/out/", "santa/out/")
# Real tokens, not placeholders like "your_key" or empty values.
SECRETISH = re.compile(r"^[A-Za-z0-9_\-+/=]{32,}$")


def _req_name(req: object) -> str | None:
    if isinstance(req, dict):
        return None
    text = str(req).strip()
    match = re.match(r"([A-Za-z0-9][A-Za-z0-9._-]*)", text)
    return match.group(1).lower() if match else None


def _names(reqs: list[object]) -> set[str]:
    return {n for n in (_req_name(r) for r in reqs) if n}


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())


def test_pyproject_requires_python_and_santa_wheel() -> None:
    data = _pyproject()
    assert data["project"]["requires-python"] == ">=3.11"
    packages = data["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert "santa" in packages
    assert "santa_demo" not in packages


def test_pyproject_core_deps_are_laptop_cli_only() -> None:
    names = _names(_pyproject()["project"]["dependencies"])
    missing = [p for p in CORE_PACKAGES if p not in names]
    leaked = [p for p in DROPPED_FROM_CORE if p in names]
    google = [n for n in names if n.startswith("google-")]
    assert missing == [], missing
    assert leaked == [], leaked
    assert google == [], google


def test_pyproject_optional_groups() -> None:
    groups = _pyproject()["dependency-groups"]
    assert _names(groups["service"]) >= set(SERVICE_PACKAGES)
    assert _names(groups["job"]) >= set(JOB_PACKAGES)
    research = _names(groups["research"])
    assert research >= set(RESEARCH_PACKAGES)
    assert any(n.startswith("google-") for n in research)
    dev = groups["dev"]
    assert any(isinstance(item, dict) and item.get("include-group") == "service" for item in dev)
    assert "job" not in {item.get("include-group") for item in dev if isinstance(item, dict)}
    assert "research" not in {item.get("include-group") for item in dev if isinstance(item, dict)}
    extras = _pyproject()["project"]["optional-dependencies"]
    assert _names(extras["job"]) >= set(JOB_PACKAGES)
    assert _names(extras["service"]) >= set(SERVICE_PACKAGES)


def test_gitignore_blocks_env_pkg_and_outputs() -> None:
    text = (ROOT / ".gitignore").read_text()
    missing = [p for p in GITIGNORE_PATTERNS if p not in text]
    assert missing == [], missing


def test_env_example_documents_workshop_keys_without_secrets() -> None:
    text = (ROOT / ".env.example").read_text()
    missing = [k for k in ENV_KEYS if k not in text]
    assert missing == [], missing
    assert "auto|off|only" in text or "auto | off | only" in text
    for name in ("GLM-5.3-Flash", "Nemotron-3.5-Lightning", "DeepSeek-V4-Pro"):
        assert name in text
    secrets = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        value = stripped.split("=", 1)[1].strip().strip("\"'")
        if SECRETISH.match(value):
            secrets.append(stripped.split("=", 1)[0])
    assert secrets == [], secrets
