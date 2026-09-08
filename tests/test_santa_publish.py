"""``santa.publish``: upload card/video files via the CPU service or Storage. No network."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from santa.cli import app
from santa.publish import PublishError, object_key, publish_files
from santa.storage import MemoryStorage


class FakeResponse:
    def __init__(self, key: str, status: int = 200) -> None:
        self._key = key
        self.status_code = status

    def json(self) -> dict[str, str]:
        return {"key": self._key}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_object_key_routes_png_html_json_to_cards_and_mp4_to_videos(tmp_path: Path) -> None:
    assert object_key(tmp_path / "gift.png") == "cards/gift.png"
    assert object_key(tmp_path / "gift.html") == "cards/gift.html"
    assert object_key(tmp_path / "card.json") == "cards/card.json"
    assert object_key(tmp_path / "clip.mp4") == "videos/clip.mp4"
    assert object_key("clip.bin", content_type="video/mp4") == "videos/clip.bin"
    kid = tmp_path / "k01" / "card.png"
    kid.parent.mkdir()
    kid.write_bytes(b"x")
    assert object_key(kid) == "cards/k01.png"
    assert object_key(tmp_path / "k01" / "card.html") == "cards/k01.html"
    assert object_key(tmp_path / "k01" / "card.mp4") == "videos/k01.mp4"
    assert object_key(tmp_path / "k01" / "card.png", object_id="k99") == "cards/k99.png"


def test_publish_files_posts_multipart_to_service(tmp_path: Path) -> None:
    png = tmp_path / "gift.png"
    html = tmp_path / "gift.html"
    png.write_bytes(b"png-bytes")
    html.write_text("<html/>", encoding="utf-8")
    posted: list[dict] = []

    def fake_post(url: str, files=None, timeout=None):
        name, data, ctype = files["file"]
        posted.append({"url": url, "name": name, "data": data, "ctype": ctype})
        prefix = "videos" if name.endswith(".mp4") else "cards"
        return FakeResponse(f"{prefix}/{name}")

    keys = publish_files(
        [png, html],
        service_url="http://santa.test",
        post=fake_post,
    )
    assert keys == ["cards/gift.png", "cards/gift.html"]
    assert posted[0]["url"] == "http://santa.test/api/publish"
    assert posted[0]["data"] == b"png-bytes"
    assert posted[0]["ctype"] == "image/png"
    assert posted[1]["ctype"] == "text/html"


def test_publish_files_requires_service_url_unless_local(tmp_path: Path) -> None:
    png = tmp_path / "gift.png"
    png.write_bytes(b"png")
    with pytest.raises(PublishError, match="SANTA_SERVICE_URL"):
        publish_files([png], service_url="", local=False)


def test_publish_files_local_uploads_via_storage(tmp_path: Path) -> None:
    png = tmp_path / "gift.png"
    mp4 = tmp_path / "clip.mp4"
    png.write_bytes(b"png-bytes")
    mp4.write_bytes(b"mp4-bytes")
    store = MemoryStorage()
    keys = publish_files([png, mp4], local=True, storage=store)
    assert keys == ["cards/gift.png", "videos/clip.mp4"]
    assert store.download("cards/gift.png") == b"png-bytes"
    assert store.download("videos/clip.mp4") == b"mp4-bytes"


def test_cli_publish_command_posts_to_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    png = tmp_path / "gift.png"
    png.write_bytes(b"png-bytes")
    monkeypatch.setenv("SANTA_SERVICE_URL", "http://santa.test")
    posted: list[str] = []

    def fake_post(url: str, files=None, timeout=None):
        posted.append(url)
        name = files["file"][0]
        return FakeResponse(f"cards/{name}")

    monkeypatch.setattr("santa.publish.requests.post", fake_post)
    result = CliRunner().invoke(app, ["publish", str(png)])
    assert result.exit_code == 0, result.output
    assert posted == ["http://santa.test/api/publish"]
    assert "cards/gift.png" in result.output


def test_cli_publish_command_local_uses_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mp4 = tmp_path / "clip.mp4"
    mp4.write_bytes(b"mp4-bytes")
    store = MemoryStorage()
    monkeypatch.setattr("santa.publish.Storage.from_env", lambda: store)
    monkeypatch.delenv("SANTA_SERVICE_URL", raising=False)
    result = CliRunner().invoke(app, ["publish", str(mp4), "--local"])
    assert result.exit_code == 0, result.output
    assert store.download("videos/clip.mp4") == b"mp4-bytes"
    assert "videos/clip.mp4" in result.output


def test_cli_publish_errors_when_service_url_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    png = tmp_path / "gift.png"
    png.write_bytes(b"png-bytes")
    monkeypatch.delenv("SANTA_SERVICE_URL", raising=False)
    result = CliRunner().invoke(app, ["publish", str(png)])
    assert result.exit_code == 1
    assert "SANTA_SERVICE_URL" in result.output
    assert "--local" in result.output


def test_cli_card_publish_uploads_png_and_html_as_kid_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from santa.card import CardRun
    from santa.schemas import CardImage, GiftCard, GiftRecommendation, Wish

    out = tmp_path / "kid"
    out.mkdir()
    png = out / "card.png"
    html = out / "card.html"
    (out / "card.json").write_text("{}", encoding="utf-8")
    png.write_bytes(b"png-bytes")
    html.write_text("<html/>", encoding="utf-8")
    seen: dict[str, str] = {}

    def fake_make(kid, settings, **kw):
        seen["id"] = kid.id
        rec = GiftRecommendation(kid_id=kid.id, gifts=["train"], rationale="r", model_version="x")
        wish = Wish(kid_id=kid.id, text="Merry Christmas!", mood="warm", model_version="x")
        image = CardImage(kid_id=kid.id, path=str(png), model_version="x")
        card = GiftCard(
            kid_id=kid.id,
            recommendation=rec,
            wish=wish,
            image=image,
            png_path=str(png),
            html_path=str(html),
        )
        return CardRun(card=card, out_dir=out, steps=[])

    monkeypatch.setenv("SANTA_SERVICE_URL", "http://santa.test")
    monkeypatch.setattr("santa.card.make_card", fake_make)
    monkeypatch.setattr("santa.config.Settings.load", lambda *a, **k: object())
    posted: list[str] = []

    def fake_post(url: str, files=None, timeout=None):
        name = files["file"][0]
        posted.append(name)
        return FakeResponse(f"cards/{name}")

    monkeypatch.setattr("santa.publish.requests.post", fake_post)
    result = CliRunner().invoke(
        app, ["card", "--name", "Mia", "--age", "7", "--wish", "trains", "--publish"]
    )
    assert result.exit_code == 0, result.output
    assert posted == [f"{seen['id']}.png", f"{seen['id']}.html"]
    assert f"cards/{seen['id']}.png" in result.output


def test_cli_card_publish_without_service_url_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from santa.card import CardRun
    from santa.schemas import CardImage, GiftCard, GiftRecommendation, Wish

    png = tmp_path / "card.png"
    html = tmp_path / "card.html"
    png.write_bytes(b"png")
    html.write_text("<html/>", encoding="utf-8")

    def fake_make(kid, settings, **kw):
        rec = GiftRecommendation(kid_id=kid.id, gifts=["train"], rationale="r", model_version="x")
        wish = Wish(kid_id=kid.id, text="Merry Christmas!", mood="warm", model_version="x")
        image = CardImage(kid_id=kid.id, path=str(png), model_version="x")
        card = GiftCard(
            kid_id=kid.id,
            recommendation=rec,
            wish=wish,
            image=image,
            png_path=str(png),
            html_path=str(html),
        )
        return CardRun(card=card, out_dir=tmp_path, steps=[])

    monkeypatch.delenv("SANTA_SERVICE_URL", raising=False)
    monkeypatch.setattr("santa.card.make_card", fake_make)
    monkeypatch.setattr("santa.config.Settings.load", lambda *a, **k: object())
    result = CliRunner().invoke(
        app, ["card", "--name", "Mia", "--age", "7", "--wish", "trains", "--publish"]
    )
    assert result.exit_code == 1
    assert "SANTA_SERVICE_URL" in result.output


def test_cli_animate_publish_uploads_mp4(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    png = tmp_path / "card.png"
    mp4 = tmp_path / "card.mp4"
    png.write_bytes(b"png")
    mp4.write_bytes(b"mp4-bytes")
    monkeypatch.setenv("SANTA_SERVICE_URL", "http://santa.test")
    monkeypatch.setattr("santa.cli.Settings.load", lambda: object())
    monkeypatch.setattr("santa.cli.run", lambda *a, **k: mp4)
    posted: list[tuple[str, bytes]] = []

    def fake_post(url: str, files=None, timeout=None):
        name, data, _ctype = files["file"]
        posted.append((name, data))
        return FakeResponse(f"videos/{name}")

    monkeypatch.setattr("santa.publish.requests.post", fake_post)
    result = CliRunner().invoke(app, ["animate", str(png), "--publish"])
    assert result.exit_code == 0, result.output
    assert posted == [("card.mp4", b"mp4-bytes")]
    assert "videos/card.mp4" in result.output


def test_cli_animate_no_wait_does_not_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    png = tmp_path / "card.png"
    png.write_bytes(b"png")
    monkeypatch.setenv("SANTA_SERVICE_URL", "http://santa.test")
    monkeypatch.setattr("santa.cli.Settings.load", lambda: object())
    monkeypatch.setattr("santa.cli.run", lambda *a, **k: {"job_id": "job-1", "png": str(png)})
    posted: list[str] = []
    monkeypatch.setattr(
        "santa.publish.requests.post",
        lambda *a, **k: posted.append("hit") or FakeResponse("x"),
    )
    result = CliRunner().invoke(app, ["animate", str(png), "--publish", "--no-wait"])
    assert result.exit_code == 0, result.output
    assert posted == []
    assert "job-1" in result.output


def test_cli_animate_status_publish_uploads_when_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    png = tmp_path / "card.png"
    mp4 = tmp_path / "card.mp4"
    ticket = tmp_path / "animate.ticket.json"
    png.write_bytes(b"png")
    mp4.write_bytes(b"mp4-bytes")
    ticket.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("SANTA_SERVICE_URL", "http://santa.test")
    monkeypatch.setattr("santa.cli.Settings.load", lambda: object())
    monkeypatch.setattr("santa.cli.poll_ticket", lambda *a, **k: mp4)
    posted: list[str] = []

    def fake_post(url: str, files=None, timeout=None):
        posted.append(files["file"][0])
        return FakeResponse(f"videos/{files['file'][0]}")

    monkeypatch.setattr("santa.publish.requests.post", fake_post)
    result = CliRunner().invoke(app, ["animate", "--status", str(ticket), "--publish"])
    assert result.exit_code == 0, result.output
    assert posted == ["card.mp4"]
    assert "videos/card.mp4" in result.output


def test_cli_animate_publish_local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    png = tmp_path / "card.png"
    mp4 = tmp_path / "card.mp4"
    png.write_bytes(b"png")
    mp4.write_bytes(b"mp4-bytes")
    store = MemoryStorage()
    monkeypatch.delenv("SANTA_SERVICE_URL", raising=False)
    monkeypatch.setattr("santa.cli.Settings.load", lambda: object())
    monkeypatch.setattr("santa.cli.run", lambda *a, **k: mp4)
    monkeypatch.setattr("santa.publish.Storage.from_env", lambda: store)
    result = CliRunner().invoke(app, ["animate", str(png), "--publish", "--local"])
    assert result.exit_code == 0, result.output
    assert store.download("videos/card.mp4") == b"mp4-bytes"
