"""Demo session seam tests — fakes only, no Token Factory / endpoints / Recraft."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from src.data_scheme import GiftCard, KidProfile

from santa_demo.config import DemoConfig, ImageEndpointConfigError
from santa_demo.session import DemoCard, DemoSession, ProfileValidationError, validate_profile


def _env(monkeypatch, **values: str) -> None:
    monkeypatch.setenv("IMAGE_ENDPOINT_URL", values.get("image_url", "https://sana.example/v1"))
    monkeypatch.setenv("IMAGE_ENDPOINT_TOKEN", values.get("image_token", "image-token"))
    monkeypatch.setenv(
        "TOKEN_FACTORY_API_KEY", values.get("tf_key", "tf-key")
    )  # pragma: allowlist secret
    monkeypatch.setenv(
        "TOKEN_FACTORY_BASE_URL", values.get("tf_url", "https://api.tokenfactory.nebius.com/v1")
    )


def _fake_runner_factory(seen: list) -> callable:
    def runner(profile, llm_client, image_client, output_dir, intermediate_dir):
        seen.append(
            {
                "profile": profile,
                "image_base_url": image_client.base_url,
                "llm_base_url": llm_client.base_url,
            }
        )
        gift_card = GiftCard(
            kid_id=profile.id,
            recommendation_id="rec-1",
            wish_id="wish-1",
            image_id="img-1",
            rendered_url=str(output_dir / f"{profile.id}.png"),
            status="completed",
        )
        return DemoCard(
            profile=profile,
            gifts=["telescope"],
            wish_text="May your nights be full of stars.",
            html="<html>card</html>",
            png_path=gift_card.rendered_url,
            gift_card=gift_card,
            image_endpoint_url=image_client.base_url,
        )

    return runner


def test_from_env_fails_before_recraft_when_image_endpoint_missing(monkeypatch):
    monkeypatch.delenv("IMAGE_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("IMAGE_ENDPOINT_TOKEN", raising=False)
    monkeypatch.setenv("RECRAFT_API_KEY", "recraft-should-not-be-used")  # pragma: allowlist secret
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", "tf-key")  # pragma: allowlist secret

    with pytest.raises(ImageEndpointConfigError, match="does not fall back to Recraft"):
        DemoConfig.from_env()


def test_from_env_fails_when_only_image_token_missing(monkeypatch):
    monkeypatch.setenv("IMAGE_ENDPOINT_URL", "https://sana.example/v1")
    monkeypatch.delenv("IMAGE_ENDPOINT_TOKEN", raising=False)
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", "tf-key")  # pragma: allowlist secret
    monkeypatch.setenv("RECRAFT_API_KEY", "recraft-should-not-be-used")  # pragma: allowlist secret

    with pytest.raises(ImageEndpointConfigError):
        DemoConfig.from_env()


def test_generate_card_uses_image_endpoint_not_recraft(monkeypatch):
    _env(monkeypatch)
    seen: list = []
    image = SimpleNamespace(base_url="https://sana.example/v1")
    llm = SimpleNamespace(base_url="https://api.tokenfactory.nebius.com/v1")
    session = DemoSession.from_env(
        llm_client=llm,
        image_client=image,
        card_runner=_fake_runner_factory(seen),
    )

    profile = KidProfile(name="Emma", age=7, wishlist=["stars"])
    card = session.generate_card(profile)

    assert card.gifts == ["telescope"]
    assert card.wish_text == "May your nights be full of stars."
    assert "recraft" not in card.image_endpoint_url.lower()
    assert card.image_endpoint_url == "https://sana.example/v1"
    assert seen[0]["image_base_url"] == "https://sana.example/v1"
    assert session.last_card is card


def test_from_env_rejects_recraft_image_client(monkeypatch):
    _env(monkeypatch)
    recraft = SimpleNamespace(base_url="https://external.api.recraft.ai/v1")
    llm = SimpleNamespace(base_url="https://api.tokenfactory.nebius.com/v1")

    with pytest.raises(ImageEndpointConfigError, match="Recraft"):
        DemoSession.from_env(
            llm_client=llm, image_client=recraft, card_runner=_fake_runner_factory([])
        )


def test_empty_name_rejected_before_runner(monkeypatch):
    _env(monkeypatch)
    called: list = []

    def boom(*_args, **_kwargs):
        called.append(True)
        raise AssertionError("card_runner must not be called")

    image = SimpleNamespace(base_url="https://sana.example/v1")
    llm = SimpleNamespace(base_url="https://api.tokenfactory.nebius.com/v1")
    session = DemoSession.from_env(llm_client=llm, image_client=image, card_runner=boom)

    with pytest.raises(ProfileValidationError, match="Name"):
        session.generate_card(KidProfile(name="   ", age=7, wishlist=[]))
    assert called == []


def test_validate_profile_rejects_empty_name():
    with pytest.raises(ProfileValidationError, match="Name"):
        validate_profile("", 8, "a bike")


def test_validate_profile_rejects_invalid_age():
    with pytest.raises(ProfileValidationError, match="Age"):
        validate_profile("Noah", 0, "a ball")
    with pytest.raises(ProfileValidationError, match="Age"):
        validate_profile("Noah", "nope", "a ball")


def test_validate_profile_builds_kid_profile():
    profile = validate_profile("Noah", 12, "a telescope")
    assert profile.name == "Noah"
    assert profile.age == 12
    assert profile.wishlist == ["a telescope"]
