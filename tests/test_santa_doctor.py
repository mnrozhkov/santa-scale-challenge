"""doctor: one row per dependency (+ fallback rows), fix text on failure, WARN when a fallback covers."""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from santa.config import Settings
from santa.doctor import failed, run_checks

NOENV = Path("/nonexistent")
OA_KEY = "oa"  # pragma: allowlist secret


def OK(url, headers):
    return 200, "{}"


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", "k")  # pragma: allowlist secret
    monkeypatch.setenv("IMAGE_ENDPOINT_URL", "https://img.example")
    monkeypatch.setenv("IMAGE_ENDPOINT_TOKEN", "t")
    for var in (
        "OPENAI_API_KEY",
        "SANTA_FALLBACK",
        "SANTA_SERVICE_URL",
        "NEBIUS_IAM_TOKEN",
        "NEBIUS_PROJECT_ID",
        "NEBIUS_BUCKET_ID",
        "VIDEO_ENDPOINT_URL",
        "AUDIO_ENDPOINT_URL",
    ):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def row(checks, prefix):
    return next(c for c in checks if c.name.startswith(prefix))


def test_all_green_when_endpoints_answer(env):
    checks = run_checks(Settings.load(env_file=NOENV), probe=OK)
    assert row(checks, "llm ·").ok and row(checks, "image ·").ok
    assert row(checks, "video").status == "SKIP"  # Step 7 role, not configured, not required
    assert row(checks, "llm fallback").status == "SKIP"  # no OPENAI_API_KEY
    assert not failed(checks)


def test_502_means_still_loading(env):
    def probe(url, h):
        return (502, "failed to connect") if "img.example" in url else (200, "{}")

    checks = run_checks(Settings.load(env_file=NOENV), probe=probe)
    img = row(checks, "image ·")
    assert (
        img.status == "FAIL"
        and "weights still loading" in img.detail
        and "re-run doctor" in img.fix
    )
    assert failed(checks)


def test_401_sends_bearer_and_points_at_token(env):
    seen = {}

    def probe(url, headers):
        if "img.example" in url:
            seen["auth"] = headers.get("Authorization")
            return 401, ""
        return 200, "{}"

    img = row(run_checks(Settings.load(env_file=NOENV), probe=probe), "image ·")
    assert seen["auth"] == "Bearer t" and "token" in img.fix.lower()


def test_unreachable_is_reported_not_raised(env):
    def probe(url, headers):
        raise requests.ConnectionError("boom")

    checks = run_checks(Settings.load(env_file=NOENV), probe=probe)
    assert "unreachable" in row(checks, "llm ·").detail and failed(checks)


def test_fallback_downgrades_failure_to_warn(env):
    env.setenv("OPENAI_API_KEY", OA_KEY)

    def probe(url, h):
        return (200, "{}") if "openai.com" in url or "tokenfactory" in url else (502, "")

    checks = run_checks(Settings.load(env_file=NOENV), probe=probe)
    img = row(checks, "image ·")
    assert img.status == "WARN" and "fallback covers it" in img.fix
    assert row(checks, "image fallback · gpt-image-1").ok
    assert not failed(checks)


def test_missing_image_env_without_key_fails(env):
    env.delenv("IMAGE_ENDPOINT_URL")
    checks = run_checks(Settings.load(env_file=NOENV), probe=OK)
    img = row(checks, "image")
    assert img.status == "FAIL" and "IMAGE_ENDPOINT_URL" in img.detail and failed(checks)


def test_missing_image_env_with_key_is_warn(env):
    env.delenv("IMAGE_ENDPOINT_URL")
    env.setenv("OPENAI_API_KEY", OA_KEY)
    checks = run_checks(Settings.load(env_file=NOENV), probe=OK)
    assert row(checks, "image").status == "WARN" and not failed(checks)


def test_policy_off_hides_fallback_rows(env):
    env.setenv("OPENAI_API_KEY", OA_KEY)
    env.setenv("SANTA_FALLBACK", "off")
    checks = run_checks(Settings.load(env_file=NOENV), probe=OK)
    assert "disabled" in row(checks, "llm fallback").detail


def test_probes_token_factory_and_image_endpoint(env):
    seen: list[str] = []

    def probe(url, headers):
        seen.append(url)
        return 200, "{}"

    run_checks(Settings.load(env_file=NOENV), probe=probe)
    assert any(u.endswith("/v1/models") and "tokenfactory" in u for u in seen)
    assert any(u.endswith("/v1/models") and "img.example" in u for u in seen)


def test_audio_fallback_tracks_dir_is_repo_rooted_not_cwd(env, monkeypatch, tmp_path):
    moods = tmp_path / "data" / "fallback" / "moods"
    moods.mkdir(parents=True)
    (moods / "warm.mp3").write_bytes(b"id3")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setattr("santa.doctor.REPO_ROOT", tmp_path)
    monkeypatch.chdir(elsewhere)
    checks = run_checks(Settings.load(env_file=NOENV), probe=OK)
    assert row(checks, "audio fallback").ok
    assert "has tracks" in row(checks, "audio fallback").detail


def test_batch_plumbing_presence_is_optional(env):
    checks = run_checks(Settings.load(env_file=NOENV), probe=OK)
    assert row(checks, "service ·").status == "SKIP"
    assert row(checks, "jobs · NEBIUS_IAM_TOKEN").status == "SKIP"
    assert row(checks, "jobs · NEBIUS_PROJECT_ID").status == "SKIP"
    assert row(checks, "jobs · NEBIUS_BUCKET_ID").status == "SKIP"
    env.setenv("SANTA_SERVICE_URL", "https://svc.example")
    env.setenv("NEBIUS_IAM_TOKEN", "tok")
    env.setenv("NEBIUS_PROJECT_ID", "proj")
    env.setenv("NEBIUS_BUCKET_ID", "bucket-id")
    checks = run_checks(Settings.load(env_file=NOENV), probe=OK)
    assert row(checks, "service ·").ok and row(checks, "service ·").detail == "https://svc.example"
    assert row(checks, "jobs · NEBIUS_IAM_TOKEN").ok
    assert row(checks, "jobs · NEBIUS_PROJECT_ID").ok
    assert row(checks, "jobs · NEBIUS_BUCKET_ID").ok
