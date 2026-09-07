"""GiftCard pipeline from fakes: no network, adapters injected at the make_card seam."""

from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from santa.card import make_card
from santa.cli import app
from santa.config import RoleConfig, Settings
from santa.models import AdapterError, Resilient
from santa.schemas import GiftCard, KidProfile

NOENV = Path("/nonexistent")
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


class FakeLLM:
    used_fallback = False
    model_version = "openai/gpt-oss-120b@https://tf.example/v1"
    last_metrics = {"latency_ms": 12, "fallback": False}
    cfg = SimpleNamespace(
        model="openai/gpt-oss-120b",
        base_url="https://tf.example",
        is_fallback=False,
        label="llm",
    )

    def generate_json(self, prompt: str, **kw):
        if "rationale" in prompt:
            return {"gifts": ["wooden train", "storybook"], "rationale": "loves trains"}
        return {
            "wish": "Dear Mia, may your wooden train race through the snow. Merry Christmas!",
            "mood": "warm",
        }


class FakeImage:
    used_fallback = False
    model_version = "sana@https://img.example"
    last_metrics = {"latency_ms": 40, "fallback": False}
    cfg = SimpleNamespace(model="sana", base_url="https://img.example/", is_fallback=False)

    def generate(self, prompt: str, *, seed=None) -> bytes:
        return PNG_1PX


def test_make_card_from_fakes_attributes_image_to_primary(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", "k")
    monkeypatch.setenv("IMAGE_ENDPOINT_URL", "https://img.example/")
    monkeypatch.setenv("IMAGE_ENDPOINT_TOKEN", "t")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    kid = KidProfile(name="Mia", age=7, wishlist=["trains"])
    run = make_card(
        kid,
        Settings.load(env_file=NOENV),
        out_root=tmp_path,
        llm=FakeLLM(),
        image=FakeImage(),
    )
    assert isinstance(run.card, GiftCard)
    assert run.card.recommendation.gifts == ["wooden train", "storybook"]
    assert "Mia" in run.card.wish.text
    assert run.card.image.endpoint == "https://img.example/"
    assert Path(run.card.png_path).is_file()
    assert Path(run.card.html_path).is_file()
    assert (tmp_path / kid.id / "card.png").is_file()


def _image_cfg(**kw) -> RoleConfig:
    base = {
        "name": "image",
        "adapter": "openai_images",
        "base_url": "https://img.example/",
        "api_key": "t",
        "model": "sana",
        "options": {"size": "1024x1024"},
    }
    return RoleConfig(**{**base, **kw})


class BoomImage:
    def __init__(self) -> None:
        self.cfg = _image_cfg()
        self.last_metrics: dict = {}
        self.model_version = self.cfg.model or "sana"

    def generate(self, prompt: str, *, seed=None) -> bytes:
        raise AdapterError("primary down")


class FineImage:
    def __init__(self) -> None:
        self.cfg = _image_cfg(
            base_url="https://api.openai.com/v1", model="gpt-image-1", is_fallback=True
        )
        self.last_metrics = {"latency_ms": 9}
        self.model_version = "gpt-image-1@https://api.openai.com/v1"

    def generate(self, prompt: str, *, seed=None) -> bytes:
        self.last_metrics = {"latency_ms": 9}
        return PNG_1PX


def test_image_primary_failure_records_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", "k")
    monkeypatch.setenv("IMAGE_ENDPOINT_URL", "https://img.example/")
    monkeypatch.setenv("IMAGE_ENDPOINT_TOKEN", "t")
    monkeypatch.setenv("OPENAI_API_KEY", "oa")
    kid = KidProfile(name="Mia", age=7, wishlist=["trains"])
    image = Resilient(BoomImage(), FineImage(), "auto", "image")
    run = make_card(
        kid,
        Settings.load(env_file=NOENV),
        out_root=tmp_path,
        llm=FakeLLM(),
        image=image,
    )
    img_steps = [s for s in run.steps if s["role"] == "image"]
    assert img_steps and img_steps[-1]["fallback"] is True
    assert run.card.image.endpoint == "https://api.openai.com/v1"


class BoomLLM:
    cfg = SimpleNamespace(
        model="boom", base_url="https://tf.example", is_fallback=False, label="llm"
    )
    last_metrics: dict = {}
    model_version = "boom"

    def generate_json(self, prompt: str, **kw):
        raise AdapterError("primary down")


def test_llm_primary_failure_records_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", "k")
    monkeypatch.setenv("IMAGE_ENDPOINT_URL", "https://img.example/")
    monkeypatch.setenv("IMAGE_ENDPOINT_TOKEN", "t")
    monkeypatch.setenv("OPENAI_API_KEY", "oa")
    kid = KidProfile(name="Mia", age=7, wishlist=["trains"])
    llm = Resilient(BoomLLM(), FakeLLM(), "auto", "llm")
    run = make_card(
        kid,
        Settings.load(env_file=NOENV),
        out_root=tmp_path,
        llm=llm,
        image=FakeImage(),
    )
    llm_steps = [s for s in run.steps if s["role"] == "llm"]
    assert llm_steps and all(s["fallback"] is True for s in llm_steps)


def _spy_adapter_for(monkeypatch):
    calls = []

    def boom(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("adapters must not be constructed for an invalid profile")

    monkeypatch.setattr("santa.models.adapter_for", boom)
    monkeypatch.setattr("santa.card.adapter_for", boom)
    return calls


def test_empty_name_rejected_before_adapters(monkeypatch) -> None:
    calls = _spy_adapter_for(monkeypatch)
    result = CliRunner().invoke(app, ["card", "--name", "", "--age", "7", "--wish", "trains"])
    assert result.exit_code != 0
    assert "No such command" not in result.output
    assert "name" in result.output.lower()
    assert calls == []


def test_age_out_of_range_rejected_before_adapters(monkeypatch) -> None:
    calls = _spy_adapter_for(monkeypatch)
    runner = CliRunner()
    for age in ("0", "19"):
        result = runner.invoke(app, ["card", "--name", "Mia", "--age", age, "--wish", "trains"])
        assert result.exit_code != 0, age
        assert "No such command" not in result.output
        assert "18" in result.output
    assert calls == []


def test_card_cli_prints_primary_and_fallback(tmp_path, monkeypatch) -> None:
    from santa.card import CardRun
    from santa.schemas import CardImage, GiftRecommendation, Wish

    def fake_make(kid, settings, **kw):
        rec = GiftRecommendation(
            kid_id=kid.id, gifts=["wooden train"], rationale="r", model_version="x"
        )
        wish = Wish(kid_id=kid.id, text="Merry Christmas!", mood="warm", model_version="x")
        image = CardImage(kid_id=kid.id, path="p", model_version="x")
        card = GiftCard(
            kid_id=kid.id,
            recommendation=rec,
            wish=wish,
            image=image,
            png_path=str(tmp_path / "card.png"),
            html_path=str(tmp_path / "card.html"),
        )
        return CardRun(
            card=card,
            out_dir=tmp_path,
            steps=[
                {"role": "llm", "model": "gpt-oss", "fallback": False, "ms": 10},
                {"role": "image", "model": "gpt-image-1", "fallback": True, "ms": 20},
            ],
        )

    monkeypatch.setattr("santa.card.make_card", fake_make)
    monkeypatch.setattr("santa.config.Settings.load", lambda *a, **k: object(), raising=True)
    result = CliRunner().invoke(
        app, ["card", "--name", "Mia", "--age", "7", "--wish", "trains", "--out", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert "primary" in result.output and "fallback" in result.output
    assert "gpt-oss" in result.output and "gpt-image-1" in result.output
