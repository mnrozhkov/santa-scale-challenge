"""Service session seam — injected fakes, no cloud."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from santa.card import CardRun, ProfileError
from santa.config import ConfigError, Settings
from santa.schemas import CardImage, GiftCard, GiftRecommendation, KidProfile, Wish
from santa.service.app import create_app
from santa.service.session import ServiceSession
from santa.storage import MemoryStorage

NOENV = Path("/nonexistent")


def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", "tf-key")  # pragma: allowlist secret
    monkeypatch.setenv("IMAGE_ENDPOINT_URL", "https://sana.example/v1")
    monkeypatch.setenv("IMAGE_ENDPOINT_TOKEN", "image-token")  # pragma: allowlist secret
    monkeypatch.setenv("RECRAFT_API_KEY", "recraft-should-not-be-used")  # pragma: allowlist secret
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def _gift_card(kid: KidProfile, tmp_path: Path) -> GiftCard:
    rec = GiftRecommendation(
        kid_id=kid.id, gifts=["telescope"], rationale="stars", model_version="tf"
    )
    wish = Wish(
        kid_id=kid.id, text="May your nights be full of stars.", mood="warm", model_version="tf"
    )
    image = CardImage(
        kid_id=kid.id,
        path=str(tmp_path / "card.png"),
        model_version="sana",
        endpoint="https://sana.example/v1",
    )
    return GiftCard(
        kid_id=kid.id,
        recommendation=rec,
        wish=wish,
        image=image,
        png_path=str(tmp_path / f"{kid.id}.png"),
        html_path=str(tmp_path / f"{kid.id}.html"),
    )


def test_generate_card_uses_injected_fakes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    seen: list[dict] = []

    def runner(kid, settings, *, out_root=None, llm=None, image=None, **kw):
        seen.append({"kid": kid, "image": image, "llm": llm})
        return CardRun(card=_gift_card(kid, tmp_path), out_dir=tmp_path)

    image = SimpleNamespace(base_url="https://sana.example/v1")
    llm = SimpleNamespace(base_url="https://api.tokenfactory.nebius.com/v1")
    session = ServiceSession(
        settings=Settings.load(env_file=NOENV),
        storage=MemoryStorage(),
        llm=llm,
        image=image,
        card_runner=runner,
        out_root=tmp_path,
    )
    profile = KidProfile(name="Emma", age=7, wishlist=["stars"])
    run = session.generate_card(profile)

    assert run.card.recommendation.gifts == ["telescope"]
    assert run.card.wish.text == "May your nights be full of stars."
    assert session.last_run is run
    assert seen[0]["image"] is image
    assert seen[0]["llm"] is llm


def test_empty_name_rejected_before_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    called: list[bool] = []

    def boom(*_args: object, **_kwargs: object) -> CardRun:
        called.append(True)
        raise AssertionError("card_runner must not be called")

    session = ServiceSession(
        settings=Settings.load(env_file=NOENV),
        storage=MemoryStorage(),
        card_runner=boom,
        out_root=tmp_path,
    )
    with pytest.raises(ProfileError, match="Name"):
        session.generate_card(KidProfile(name="   ", age=7, wishlist=[]))
    assert called == []


def test_image_comes_from_settings_not_recraft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env(monkeypatch)
    seen: list[str] = []

    def runner(kid, settings, *, out_root=None, llm=None, image=None, **kw):
        seen.append(settings.role("image").base_url)
        return CardRun(card=_gift_card(kid, tmp_path), out_dir=tmp_path)

    session = ServiceSession(
        settings=Settings.load(env_file=NOENV),
        storage=MemoryStorage(),
        card_runner=runner,
        out_root=tmp_path,
    )
    session.generate_card(KidProfile(name="Emma", age=7, wishlist=["stars"]))
    assert seen == ["https://sana.example/v1"]
    assert "recraft" not in seen[0].lower()

    recraft = SimpleNamespace(base_url="https://external.api.recraft.ai/v1")
    with pytest.raises(ConfigError, match="Recraft"):
        ServiceSession(
            settings=Settings.load(env_file=NOENV),
            storage=MemoryStorage(),
            image=recraft,
            card_runner=runner,
            out_root=tmp_path,
        )


def _session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner=None) -> ServiceSession:
    _env(monkeypatch)
    if runner is None:

        def runner(kid, settings, *, out_root=None, llm=None, image=None, **kw):
            return CardRun(
                card=_gift_card(kid, tmp_path),
                out_dir=tmp_path,
                steps=[
                    {"role": "llm", "model": "gpt-oss", "fallback": False, "ms": 10},
                    {"role": "image", "model": "sana", "fallback": True, "ms": 40},
                ],
            )

    return ServiceSession(
        settings=Settings.load(env_file=NOENV),
        storage=MemoryStorage(),
        card_runner=runner,
        out_root=tmp_path,
    )


def test_api_cards_returns_card_json_with_model_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    kid = KidProfile(name="Emma", age=7, wishlist=["stars"])
    client = TestClient(create_app(_session(tmp_path, monkeypatch)))
    resp = client.post("/api/cards", json=kid.model_dump())
    assert resp.status_code == 200
    data = resp.json()
    assert data["card"]["recommendation"]["gifts"] == ["telescope"]
    assert data["card"]["wish"]["mood"] == "warm"
    steps = {s["role"]: s for s in data["steps"]}
    assert steps["image"]["model"] == "sana"
    assert steps["image"]["fallback"] is True
    assert steps["llm"]["fallback"] is False
    assert "png_url" in data and "html_url" in data
    assert data["png_url"] == f"/cards/{data['card']['kid_id']}.png"


def test_api_cards_urls_are_per_kid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    session = _session(tmp_path, monkeypatch, runner=_writing_runner(tmp_path))
    client = TestClient(create_app(session))
    first = KidProfile(id="k-a", name="Emma", age=7, wishlist=["stars"])
    second = KidProfile(id="k-b", name="Noah", age=8, wishlist=["trains"])
    a = client.post("/api/cards", json=first.model_dump())
    b = client.post("/api/cards", json=second.model_dump())
    assert a.json()["png_url"] == "/cards/k-a.png"
    assert b.json()["png_url"] == "/cards/k-b.png"
    png_a = client.get("/cards/k-a.png")
    png_b = client.get("/cards/k-b.png")
    assert png_a.status_code == 200
    assert png_b.status_code == 200
    assert png_a.content == b"png-bytes"


def _writing_runner(tmp_path: Path):
    def runner(kid, settings, *, out_root=None, llm=None, image=None, **kw):
        out = Path(out_root or tmp_path) / kid.id
        out.mkdir(parents=True, exist_ok=True)
        png = out / "card.png"
        html = out / "card.html"
        png.write_bytes(b"png-bytes")
        html.write_text("<html>card</html>", encoding="utf-8")
        card = _gift_card(kid, out).model_copy(
            update={"png_path": str(png), "html_path": str(html)}
        )
        (out / "card.json").write_text(card.model_dump_json(), encoding="utf-8")
        return CardRun(card=card, out_dir=out)

    return runner


def test_api_batch_writes_cards_to_memory_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    kids = [
        KidProfile(id="k1", name="Emma", age=7, wishlist=["stars"]),
        KidProfile(id="k2", name="Noah", age=8, wishlist=["trains"]),
    ]
    session = _session(tmp_path, monkeypatch, runner=_writing_runner(tmp_path))
    client = TestClient(create_app(session))
    resp = client.post("/api/cards/batch", json={"kids": [k.model_dump() for k in kids]})
    assert resp.status_code == 200
    data = resp.json()
    assert set(data["ids"]) == {"k1", "k2"}
    assert data["failures"] == []
    for kid_id in ("k1", "k2"):
        assert session.storage.exists(f"cards/{kid_id}.png")
        assert session.storage.exists(f"cards/{kid_id}.html")
        assert session.storage.exists(f"cards/{kid_id}.json")
    dumped = json.loads(session.storage.download("cards/k1.json"))
    assert dumped["wish"]["mood"] == "warm"


def test_api_batch_records_failures_without_aborting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    write = _writing_runner(tmp_path)

    def runner(kid, settings, *, out_root=None, llm=None, image=None, **kw):
        if kid.id == "bad":
            raise RuntimeError("image endpoint 500")
        return write(kid, settings, out_root=out_root, llm=llm, image=image, **kw)

    kids = [
        KidProfile(id="ok", name="Emma", age=7, wishlist=["stars"]),
        KidProfile(id="bad", name="Noah", age=8, wishlist=["trains"]),
        KidProfile(id="ok2", name="Mia", age=6, wishlist=["books"]),
    ]
    session = _session(tmp_path, monkeypatch, runner=runner)
    client = TestClient(create_app(session))
    resp = client.post("/api/cards/batch", json={"kids": [k.model_dump() for k in kids]})
    assert resp.status_code == 200
    data = resp.json()
    assert set(data["ids"]) == {"ok", "ok2"}
    assert len(data["failures"]) == 1
    assert data["failures"][0]["id"] == "bad"
    assert "500" in data["failures"][0]["error"]
    assert session.storage.exists("cards/ok.png")
    assert session.storage.exists("cards/ok2.png")
    assert not session.storage.exists("cards/bad.png")


def test_api_publish_uploads_bytes_by_content_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    session = _session(tmp_path, monkeypatch)
    client = TestClient(create_app(session))
    png = client.post("/api/publish", files={"file": ("gift.png", b"png-bytes", "image/png")})
    mp4 = client.post("/api/publish", files={"file": ("clip.mp4", b"mp4-bytes", "video/mp4")})
    assert png.status_code == 200
    assert mp4.status_code == 200
    assert png.json()["key"] == "cards/gift.png"
    assert mp4.json()["key"] == "videos/clip.mp4"
    assert session.storage.download("cards/gift.png") == b"png-bytes"
    assert session.storage.download("videos/clip.mp4") == b"mp4-bytes"


def test_api_wall_lists_keys_from_fake_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    session = _session(tmp_path, monkeypatch)
    session.storage.upload("cards/k1.png", b"png")
    session.storage.upload("videos/k1.mp4", b"mp4")
    session.storage.upload(
        "runs/r2/summary.json",
        json.dumps({"run_id": "r2", "kids": 2}).encode(),
        content_type="application/json",
    )
    session.storage.upload(
        "runs/r1/summary.json",
        json.dumps({"run_id": "r1", "kids": 1}).encode(),
        content_type="application/json",
    )
    client = TestClient(create_app(session))
    resp = client.get("/api/wall")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cards"] == ["cards/k1.png"]
    assert data["videos"] == ["videos/k1.mp4"]
    assert data["summary"] == {"run_id": "r1", "kids": 1}  # last uploaded, not lex max
    page = client.get("/wall")
    assert page.status_code == 200
    assert "Wall" in page.text
    assert "/media/cards/k1.png" in page.text
    assert "display: grid" in page.text
    assert "autoplay" in page.text
    assert "muted" in page.text
    assert "loop" in page.text
    assert 'http-equiv="refresh"' in page.text
    assert 'content="10"' in page.text
    assert 'class="counter"' in page.text
    assert ">1<" in page.text or ">1 done<" in page.text or "1 done" in page.text
    assert data.get("counter") == 1
    home = client.get("/")
    assert home.status_code == 200
    assert "GiftCard" in home.text or "Generate" in home.text


def test_wall_counter_prefers_totals_done(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session(tmp_path, monkeypatch)
    session.storage.upload(
        "runs/r1/summary.json",
        json.dumps(
            {"run_id": "r1", "kids": 20, "totals": {"done": 7, "skipped": 2, "failed": 1}}
        ).encode(),
        content_type="application/json",
    )
    listing = session.wall()
    assert listing["counter"] == 7
    assert listing["summary"]["kids"] == 20
