"""Settings = config/models.yaml (roles + fallbacks, job) + .env (secrets, URLs).

Code asks for a *role* (``settings.role("image")``); it never names a model.
Every role may declare a ``fallback`` block (OpenAI by default) used when the primary
is not configured or fails — see ``santa.models.adapter_for`` and ``SANTA_FALLBACK``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml  # type: ignore[import-untyped]
from dotenv import load_dotenv
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODELS_YAML = REPO_ROOT / "config" / "models.yaml"
FallbackPolicy = Literal["auto", "off", "only"]


class ConfigError(ValueError):
    """A role cannot be resolved (missing env, unknown role, bad yaml)."""


class RoleSpec(BaseModel):
    """One role block as written in models.yaml (unresolved)."""

    adapter: str
    model: str | None = None
    base_url: str | None = None
    url_env: str | None = None
    api_key_env: str | None = None
    token_env: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    fallback: RoleSpec | None = None


RoleSpec.model_rebuild()


class RoleConfig(BaseModel):
    """A resolved role: everything an adapter needs to make a call."""

    name: str
    adapter: str
    base_url: str = ""
    api_key: str = ""
    model: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    is_fallback: bool = False

    @property
    def v1(self) -> str:
        """Base URL normalised to end with ``/v1`` (OpenAI-style servers)."""
        cleaned = self.base_url.rstrip("/")
        return cleaned if cleaned.endswith("/v1") else f"{cleaned}/v1"

    @property
    def label(self) -> str:
        return (
            f"{self.name}{' (fallback)' if self.is_fallback else ''} · {self.model or self.adapter}"
        )


class JobSpec(BaseModel):
    image: str = ""
    model: str = ""
    platform: str = "gpu-h100-sxm"
    preset: str = "1gpu-16vcpu-200gb"
    preemptible: bool = True
    disk_gb: int = 250
    timeout_min: int = 90
    mount_path: str = "/data"
    hf_home: str = "/data/models"


class ModelsFile(BaseModel):
    roles: dict[str, RoleSpec]
    job: JobSpec = Field(default_factory=JobSpec)


def _env(name: str | None) -> str:
    return (os.environ.get(name) or "").strip() if name else ""


def fallback_policy() -> FallbackPolicy:
    value = (os.environ.get("SANTA_FALLBACK") or "auto").strip().lower()
    if value not in ("auto", "off", "only"):
        raise ConfigError(f"SANTA_FALLBACK must be auto|off|only, got {value!r}")
    return value  # type: ignore[return-value]


class Settings:
    """Resolved configuration for one process."""

    def __init__(self, models: ModelsFile) -> None:
        self.models = models

    # ── loading ────────────────────────────────────────────────────────────────
    @classmethod
    def load(
        cls, models_yaml: Path | str | None = None, *, env_file: Path | str | None = None
    ) -> Settings:
        load_dotenv(env_file or REPO_ROOT / ".env", override=False)
        path = Path(models_yaml or os.environ.get("SANTA_MODELS_YAML") or DEFAULT_MODELS_YAML)
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except FileNotFoundError as exc:
            raise ConfigError(f"models.yaml not found at {path}") from exc
        try:
            models = ModelsFile.model_validate(raw)
        except Exception as exc:  # pydantic ValidationError
            raise ConfigError(f"{path} is not a valid models file: {exc}") from exc
        return cls(models)

    @property
    def job(self) -> JobSpec:
        return self.models.job

    @property
    def role_names(self) -> list[str]:
        return list(self.models.roles)

    # ── resolution ─────────────────────────────────────────────────────────────
    def _spec(self, name: str) -> RoleSpec:
        spec = self.models.roles.get(name)
        if spec is None:
            raise ConfigError(f"Unknown role '{name}'. Known: {', '.join(self.role_names)}")
        return spec

    def role(self, name: str) -> RoleConfig:
        """Resolve the primary config of a role. Raises ``ConfigError`` naming the missing env var."""
        return self._resolve(name, self._spec(name), is_fallback=False)

    def fallback(self, name: str) -> RoleConfig | None:
        """Resolve the fallback of a role; ``None`` if not declared or its env is missing."""
        spec = self._spec(name).fallback
        if spec is None:
            return None
        try:
            return self._resolve(name, spec, is_fallback=True)
        except ConfigError:
            return None

    def has_fallback(self, name: str) -> bool:
        return self._spec(name).fallback is not None

    def _resolve(self, name: str, spec: RoleSpec, *, is_fallback: bool) -> RoleConfig:
        model = (_env(f"SANTA_{name.upper()}_MODEL") if not is_fallback else "") or spec.model
        base_url = spec.base_url or _env(spec.url_env)
        needs_url = spec.adapter != "local_tracks"
        if needs_url and not base_url:
            hint = spec.url_env or "base_url"
            raise ConfigError(f"Role '{name}' has no URL. Set {hint} in .env.")
        api_key = _env(spec.api_key_env) or _env(spec.token_env)
        needed_key = spec.api_key_env or spec.token_env
        if needed_key and not api_key:
            raise ConfigError(f"Role '{name}' needs {needed_key} in .env")
        return RoleConfig(
            name=name,
            adapter=spec.adapter,
            base_url=base_url,
            api_key=api_key,
            model=model,
            options=dict(spec.options),
            is_fallback=is_fallback,
        )
