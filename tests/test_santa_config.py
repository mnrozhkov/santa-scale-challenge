"""Settings: yaml + env → resolved roles and fallbacks; errors name the fix."""

from __future__ import annotations

from pathlib import Path

import pytest

from santa.config import ConfigError, Settings, fallback_policy

NOENV = Path("/nonexistent")
OA_KEY = "oa"  # pragma: allowlist secret
REQUIRED_ENV = {
    "TOKEN_FACTORY_API_KEY": "tf-key",  # pragma: allowlist secret
    "IMAGE_ENDPOINT_URL": "https://img.example/",
    "IMAGE_ENDPOINT_TOKEN": "img-token",  # pragma: allowlist secret
}
CLEAR = (
    "SANTA_LLM_MODEL",
    "SANTA_FALLBACK",
    "OPENAI_API_KEY",
    "VIDEO_ENDPOINT_URL",
    "AUDIO_ENDPOINT_URL",
)


@pytest.fixture
def env(monkeypatch):
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    for k in CLEAR:
        monkeypatch.delenv(k, raising=False)
    yield monkeypatch


def test_repo_models_yaml_is_valid(env):
    s = Settings.load(env_file=NOENV)
    assert set(s.role_names) == {"llm", "image", "video", "audio"}
    assert all(s.has_fallback(r) for r in s.role_names)
    assert s.job.platform == "gpu-h100-sxm" and s.job.preemptible is True


def test_roles_resolve_from_env(env):
    s = Settings.load(env_file=NOENV)
    llm, image = s.role("llm"), s.role("image")
    assert llm.adapter == "openai_chat"
    assert llm.api_key == REQUIRED_ENV["TOKEN_FACTORY_API_KEY"]
    assert llm.v1.endswith("/v1")
    assert image.adapter == "openai_images"
    assert image.base_url == "https://img.example/" and image.v1 == "https://img.example/v1"
    assert image.api_key == REQUIRED_ENV["IMAGE_ENDPOINT_TOKEN"]
    assert image.is_fallback is False


def test_env_override_of_llm_model_does_not_touch_fallback(env):
    env.setenv("SANTA_LLM_MODEL", "zai-org/GLM-5.3-Flash")
    env.setenv("OPENAI_API_KEY", OA_KEY)
    s = Settings.load(env_file=NOENV)
    assert s.role("llm").model == "zai-org/GLM-5.3-Flash"
    assert s.fallback("llm").model == "gpt-4o-mini"


def test_missing_url_names_the_env_var(env):
    env.delenv("IMAGE_ENDPOINT_URL")
    with pytest.raises(ConfigError, match="IMAGE_ENDPOINT_URL"):
        Settings.load(env_file=NOENV).role("image")


def test_missing_api_key_names_the_env_var(env):
    env.delenv("TOKEN_FACTORY_API_KEY")
    with pytest.raises(ConfigError, match="TOKEN_FACTORY_API_KEY"):
        Settings.load(env_file=NOENV).role("llm")


def test_missing_image_token_names_the_env_var(env):
    env.delenv("IMAGE_ENDPOINT_TOKEN")
    with pytest.raises(ConfigError, match="IMAGE_ENDPOINT_TOKEN"):
        Settings.load(env_file=NOENV).role("image")


def test_unknown_role(env):
    with pytest.raises(ConfigError, match="Unknown role"):
        Settings.load(env_file=NOENV).role("smell")


def test_fallbacks_are_openai_and_need_the_key(env):
    s = Settings.load(env_file=NOENV)
    assert (
        s.fallback("llm") is None and s.fallback("image") is None
    )  # OPENAI_API_KEY unset → unusable
    env.setenv("OPENAI_API_KEY", OA_KEY)
    s = Settings.load(env_file=NOENV)
    for role, model in (("llm", "gpt-4o-mini"), ("image", "gpt-image-1"), ("video", "sora-2")):
        fb = s.fallback(role)
        assert fb.is_fallback and fb.model == model
        assert fb.api_key == OA_KEY
        assert fb.base_url == "https://api.openai.com/v1"


def test_audio_fallback_is_local_and_needs_no_key(env):
    fb = Settings.load(env_file=NOENV).fallback("audio")
    assert fb is not None and fb.adapter == "local_tracks" and fb.base_url == ""


def test_fallback_policy_values(env):
    assert fallback_policy() == "auto"
    env.setenv("SANTA_FALLBACK", "only")
    assert fallback_policy() == "only"
    env.setenv("SANTA_FALLBACK", "sometimes")
    with pytest.raises(ConfigError, match="SANTA_FALLBACK"):
        fallback_policy()


def test_bad_yaml_is_a_config_error(tmp_path, env):
    p = tmp_path / "m.yaml"
    p.write_text("roles: {image: {}}", encoding="utf-8")
    with pytest.raises(ConfigError, match="not a valid models file"):
        Settings.load(p, env_file=NOENV)


def test_santa_imports_without_prototype_on_sys_path():
    """Schemas and prompts live in santa/; no sys.path hack, no proto.py."""
    import santa.prompts
    import santa.schemas

    assert santa.schemas.KidProfile is not None
    assert callable(santa.prompts.gift_recommendation_prompt)
    assert not (Path(__file__).resolve().parent.parent / "santa_demo" / "proto.py").exists()
