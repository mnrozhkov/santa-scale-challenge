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
    monkeypatch.delenv("SANTA_OPERATOR_TOKEN", raising=False)


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

        def runner(kid, settings, *, out_root=None, llm=None, image=None, on_progress=None, **kw):
            if on_progress is not None:
                on_progress({"type": "active", "node": "token"})
                on_progress(
                    {
                        "type": "step",
                        "step": {"role": "llm", "model": "gpt-oss", "fallback": False, "ms": 10},
                    }
                )
                on_progress({"type": "done", "node": "token", "meta": "0.0 s · gpt-oss"})
                on_progress({"type": "active", "node": "sana"})
                on_progress(
                    {
                        "type": "step",
                        "step": {"role": "image", "model": "sana", "fallback": True, "ms": 40},
                    }
                )
                on_progress(
                    {"type": "done", "node": "sana", "status": "failed", "meta": "fallback"}
                )
                on_progress({"type": "active", "node": "openai"})
                on_progress({"type": "done", "node": "openai", "meta": "0.0 s · sana"})
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


def test_api_cards_stream_emits_progress_then_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from fastapi.testclient import TestClient

    kid = KidProfile(name="Emma", age=7, wishlist=["stars"])
    client = TestClient(create_app(_session(tmp_path, monkeypatch)))
    with client.stream("POST", "/api/cards/stream", json=kid.model_dump()) as resp:
        assert resp.status_code == 200
        events: list[dict] = []
        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            events.append(json.loads(line[6:]))
    types = [e["type"] for e in events]
    assert types[0] == "active" and events[0]["node"] == "token"
    assert "step" in types
    assert "done" in types
    assert types[-1] == "complete"
    assert events[-1]["card"]["recommendation"]["gifts"] == ["telescope"]


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
        assert session.storage.exists(f"cards/{kid_id}/card.png")
        assert session.storage.exists(f"cards/{kid_id}/card.html")
        assert session.storage.exists(f"cards/{kid_id}/card.json")
    dumped = json.loads(session.storage.download("cards/k1/card.json"))
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
    assert session.storage.exists("cards/ok/card.png")
    assert session.storage.exists("cards/ok2/card.png")
    assert not session.storage.exists("cards/bad/card.png")


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
    assert png.json()["key"] == "cards/gift/card.png"
    assert mp4.json()["key"] == "cards/clip/video.mp4"
    assert session.storage.download("cards/gift/card.png") == b"png-bytes"
    assert session.storage.download("cards/clip/video.mp4") == b"mp4-bytes"


def test_api_wall_lists_keys_from_fake_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    session = _session(tmp_path, monkeypatch)
    session.storage.upload("cards/k1/card.png", b"png")
    session.storage.upload("cards/k1/video.mp4", b"mp4")
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
    assert data["cards"] == ["cards/k1/card.png"]
    assert data["videos"] == ["cards/k1/video.mp4"]
    assert data["summary"] == {"run_id": "r1", "kids": 1}  # last uploaded, not lex max
    page = client.get("/wall")
    assert page.status_code == 200
    assert "Wall" in page.text
    assert "/media/cards/k1/card.png" in page.text
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
    form = client.get("/form")
    assert form.status_code == 200
    assert "GiftCard" in form.text or "Generate" in form.text
    wall_json = client.get("/api/wall").json()
    by_id = {item["id"]: item for item in wall_json["items"]}
    assert "k1" in by_id
    assert by_id["k1"]["png_url"] == "/media/cards/k1/card.png"
    assert by_id["g1"]["png_url"] == "/demo/g1/card.png"
    assert by_id["g1"]["model"] == "demo"
    assert len(wall_json["items"]) >= 13  # 12 demo + k1
    demo = client.get("/demo/g1/card.png")
    assert demo.status_code == 200
    assert demo.headers["content-type"].startswith("image/")
    video = client.get("/demo/g1/video.mp4")
    assert video.status_code == 200
    g2_video = client.get("/demo/g2/video.mp4")
    assert g2_video.status_code == 200


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


def test_wall_falls_back_to_local_out_when_bucket_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from santa.storage import MemoryStorage, StorageError

    class BoomStorage(MemoryStorage):
        def list(self, prefix: str = "") -> list[str]:
            raise StorageError("tls")

        def list_with_mtime(self, prefix: str = "") -> list[tuple[str, float]]:
            raise StorageError("tls")

    _env(monkeypatch)
    kid_dir = tmp_path / "local1"
    kid_dir.mkdir()
    (kid_dir / "card.png").write_bytes(b"png")
    (kid_dir / "profile.json").write_text(
        json.dumps({"name": "Mia", "age": 6, "wishlist": ["train"]}), encoding="utf-8"
    )
    session = ServiceSession(
        settings=Settings.load(env_file=NOENV),
        storage=BoomStorage(),
        out_root=tmp_path,
    )
    listing = session.wall()
    by_id = {item["id"]: item for item in listing["items"]}
    assert by_id["local1"]["name"] == "Mia"
    assert by_id["local1"]["png_url"] == "/media/cards/local1/card.png"


def test_root_serves_spa_when_ui_is_built() -> None:
    from fastapi.testclient import TestClient

    from santa.service.app import UI_INDEX

    if not UI_INDEX.is_file():
        pytest.skip("UI not built")
    client = TestClient(create_app())
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Santa Scale Challenge" in resp.text
    assert "/assets/" in resp.text


def test_ui_moods_match_mood_bank() -> None:
    import re

    from santa.config import REPO_ROOT
    from santa.prompts import MOODS

    src = (REPO_ROOT / "santa" / "service" / "ui" / "src" / "App.tsx").read_text(encoding="utf-8")
    match = re.search(r"const MOODS = \[([^\]]+)\]", src)
    assert match, "MOODS list missing from App.tsx"
    labels = [part.strip().strip("'\"") for part in match.group(1).split(",") if part.strip()]
    assert [label.lower() for label in labels] == list(MOODS)


def test_generate_card_uploads_png_json_and_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    session = _session(tmp_path, monkeypatch, runner=_writing_runner(tmp_path))
    kid = KidProfile(id="emma", name="Emma", age=7, wishlist=["stars"])
    client = TestClient(create_app(session))
    resp = client.post("/api/cards", json=kid.model_dump())
    assert resp.status_code == 200
    assert session.storage.exists("cards/emma/card.png")
    assert session.storage.exists("cards/emma/card.json")
    assert session.storage.exists("cards/emma/profile.json")
    profile = json.loads(session.storage.download("cards/emma/profile.json"))
    assert profile["name"] == "Emma"
    wall = client.get("/api/wall").json()
    by_id = {item["id"]: item for item in wall["items"]}
    assert by_id["emma"]["name"] == "Emma"
    assert by_id["emma"]["gift"] == "telescope"


def test_api_kids_reads_workshop_csv() -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app())
    resp = client.get("/api/kids?limit=3")
    assert resp.status_code == 200
    kids = resp.json()["kids"]
    assert len(kids) == 3
    assert kids[0]["name"] == "Emma"


def test_tls_verify_prefers_explicit_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from santa.storage import _tls_verify, use_system_certs

    bundle = tmp_path / "ca.pem"
    bundle.write_text("dummy", encoding="utf-8")
    monkeypatch.setenv("AWS_CA_BUNDLE", str(bundle))
    assert _tls_verify() == str(bundle)
    use_system_certs()


def test_disk_storage_maps_local_out_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from santa.storage import DiskStorage, storage_for_service

    monkeypatch.delenv("NEBIUS_BUCKET_NAME", raising=False)
    monkeypatch.delenv("AWS_S3_BUCKET", raising=False)
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    kid = tmp_path / "k-local"
    kid.mkdir()
    (kid / "card.png").write_bytes(b"png")
    (kid / "card.mp4").write_bytes(b"mp4")
    (kid / "card.json").write_text("{}", encoding="utf-8")
    store = DiskStorage(tmp_path)
    assert store.exists("cards/k-local/card.png")
    assert store.exists("cards/k-local/video.mp4")
    assert "cards/k-local/card.png" in store.list("cards/")
    assert "cards/k-local/video.mp4" in store.list("cards/")
    assert store.download("cards/k-local/video.mp4") == b"mp4"
    fallback = storage_for_service(tmp_path)
    assert isinstance(fallback, DiskStorage)
    monkeypatch.setenv("SANTA_LOCAL_STORAGE", "1")
    monkeypatch.setenv("NEBIUS_BUCKET_NAME", "bucket")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "key")
    forced = storage_for_service(tmp_path)
    assert isinstance(forced, DiskStorage)


def test_api_animate_writes_video(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    def fake_animate(png, **_kw):
        dest = Path(png).with_name("card.mp4")
        dest.write_bytes(b"mp4-bytes")
        return dest

    monkeypatch.setattr("santa.animate.run", fake_animate)
    session = _session(tmp_path, monkeypatch, runner=_writing_runner(tmp_path))
    client = TestClient(create_app(session))
    kid = KidProfile(id="k-anim", name="Emma", age=7, wishlist=["stars"])
    client.post("/api/cards", json=kid.model_dump())
    resp = client.post("/api/cards/k-anim/animate", json={"mood_bank": True})
    assert resp.status_code == 200
    assert resp.json()["video_url"] == "/media/cards/k-anim/video.mp4"
    assert session.storage.download("cards/k-anim/video.mp4") == b"mp4-bytes"


def test_api_runs_submits_jobs_without_waiting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    class Jobs:
        def __init__(self) -> None:
            self.created: list[str] = []

        def create(self, payload) -> str:
            jid = f"job-{len(self.created)}"
            self.created.append(jid)
            return jid

        def get(self, job_id: str) -> str:
            return "RUNNING"

        def cancel(self, job_id: str) -> None:
            return None

    monkeypatch.setenv("NEBIUS_BUCKET_ID", "bucket-id")
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "proj")
    session = _session(tmp_path, monkeypatch, runner=_writing_runner(tmp_path))
    session.settings.models.job.image = "santa-job:test"
    session.job_service = Jobs()
    session.storage.upload("cards/k1/card.png", b"png")
    session.storage.upload("cards/k2/card.png", b"png")
    client = TestClient(create_app(session))
    resp = client.post("/api/runs", json={"jobs": 2})
    assert resp.status_code == 200
    data = resp.json()
    assert data["waiting"] is True
    assert len(data["jobs"]) == 2
    status = client.get(f"/api/runs/{data['run_id']}")
    assert status.status_code == 200
    assert status.json()["jobs"][0]["state"] == "RUNNING"


def test_api_runs_empty_inventory_is_400(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    session = _session(tmp_path, monkeypatch)
    client = TestClient(create_app(session))
    resp = client.post("/api/runs", json={"jobs": 2})
    assert resp.status_code == 400
    assert "cards/" in resp.json()["detail"]


def _blob(data: object) -> str:
    return json.dumps(data).lower()


def test_api_access_returns_role_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    session = _session(tmp_path, monkeypatch)
    monkeypatch.setenv("SANTA_OPERATOR_TOKEN", "op-secret")  # pragma: allowlist secret
    client = TestClient(create_app(session))
    guest = client.get("/api/access")
    assert guest.status_code == 200
    assert guest.json() == {"role": "guest"}
    assert "op-secret" not in guest.text
    op = client.get("/api/access", headers={"X-Santa-Operator": "op-secret"})
    assert op.json() == {"role": "operator"}
    assert set(op.json()) == {"role"}


def test_guest_forbidden_on_animate_and_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    session = _session(tmp_path, monkeypatch, runner=_writing_runner(tmp_path))
    monkeypatch.setenv("SANTA_OPERATOR_TOKEN", "op-secret")  # pragma: allowlist secret
    client = TestClient(create_app(session))
    kid = KidProfile(id="k-anim", name="Emma", age=7, wishlist=["stars"])
    assert client.post("/api/cards", json=kid.model_dump()).status_code == 200
    anim = client.post("/api/cards/k-anim/animate", json={"mood_bank": True})
    runs = client.post("/api/runs", json={"jobs": 2})
    assert anim.status_code == 403
    assert runs.status_code == 403
    assert "op-secret" not in anim.text
    assert "Operator required" in anim.json()["detail"]


def test_operator_header_allows_animate_and_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setenv("NEBIUS_BUCKET_ID", "bucket-id")
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "proj")

    def fake_animate(png, **_kw):
        dest = Path(png).with_name("card.mp4")
        dest.write_bytes(b"mp4-bytes")
        return dest

    monkeypatch.setattr("santa.animate.run", fake_animate)

    class Jobs:
        def create(self, payload) -> str:
            return "job-0"

        def get(self, job_id: str) -> str:
            return "RUNNING"

        def cancel(self, job_id: str) -> None:
            return None

    session = _session(tmp_path, monkeypatch, runner=_writing_runner(tmp_path))
    monkeypatch.setenv("SANTA_OPERATOR_TOKEN", "op-secret")  # pragma: allowlist secret
    session.settings.models.job.image = "santa-job:test"
    session.job_service = Jobs()
    session.storage.upload("cards/k1/card.png", b"png")
    client = TestClient(create_app(session))
    headers = {"X-Santa-Operator": "op-secret"}
    kid = KidProfile(id="k-op", name="Emma", age=7, wishlist=["stars"])
    client.post("/api/cards", json=kid.model_dump(), headers=headers)
    anim = client.post("/api/cards/k-op/animate", json={"mood_bank": True}, headers=headers)
    assert anim.status_code == 200
    runs = client.post("/api/runs", json={"jobs": 1}, headers=headers)
    assert runs.status_code == 200


def test_card_and_wall_json_have_no_endpoint_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    session = _session(tmp_path, monkeypatch, runner=_writing_runner(tmp_path))
    client = TestClient(create_app(session))
    kid = KidProfile(id="emma", name="Emma", age=7, wishlist=["stars"])
    resp = client.post("/api/cards", json=kid.model_dump())
    assert resp.status_code == 200
    blob = _blob(resp.json())
    assert "endpoint" not in resp.json()["card"].get("image", {})
    assert "https://sana.example" not in blob
    assert "image-token" not in blob
    assert "/users/" not in blob
    wall = client.get("/api/wall")
    assert wall.status_code == 200
    wall_blob = _blob(wall.json())
    assert "https://sana.example" not in wall_blob
    assert "image-token" not in wall_blob
    dumped = json.loads(session.storage.download("cards/emma/card.json"))
    assert "endpoint" not in dumped.get("image", {})
    assert "https://sana.example" not in json.dumps(dumped)


def test_config_error_is_generic_and_media_hides_card_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    def boom(*_args: object, **_kwargs: object) -> CardRun:
        raise ConfigError("Set OPENAI_API_KEY and IMAGE_ENDPOINT_URL https://cfg.v1")

    session = _session(tmp_path, monkeypatch, runner=boom)
    client = TestClient(create_app(session))
    kid = KidProfile(name="Emma", age=7, wishlist=["stars"])
    resp = client.post("/api/cards", json=kid.model_dump())
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail == "Card generation failed"
    assert "OPENAI_API_KEY" not in detail
    assert "IMAGE_ENDPOINT" not in detail
    assert "cfg.v1" not in detail

    session2 = _session(tmp_path, monkeypatch, runner=_writing_runner(tmp_path))
    client2 = TestClient(create_app(session2))
    kid2 = KidProfile(id="emma", name="Emma", age=7, wishlist=["stars"])
    assert client2.post("/api/cards", json=kid2.model_dump()).status_code == 200
    hidden = client2.get("/media/cards/emma/card.json")
    assert hidden.status_code == 404
    png = client2.get("/media/cards/emma/card.png")
    assert png.status_code == 200


def test_share_page_has_absolute_og_and_docs_are_disabled() -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app())
    resp = client.get("/s/g1")
    assert resp.status_code == 200
    assert 'property="og:image"' in resp.text
    assert "http://testserver/demo/g1/card.png" in resp.text
    assert 'name="twitter:card"' in resp.text
    assert "summary_large_image" in resp.text
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/s/does-not-exist").status_code == 404
