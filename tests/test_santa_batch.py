"""Batch cards phase: chunking, skip-existing, JobSpec from yaml, fake JobService timeline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from santa.batch import chunk_ids, load_kids, run_cards_phase, skip_existing
from santa.config import Settings
from santa.cost import cost_usd, hourly_rate, on_demand_cost_usd
from santa.nebius_jobs import NebiusJobError, create_and_wait, job_payload
from santa.schemas import KidProfile
from santa.storage import MemoryStorage, staged_write

NOENV = Path("/nonexistent")


def test_chunking_20_kids_into_4_jobs() -> None:
    ids = [f"k{i:02d}" for i in range(20)]
    chunks = chunk_ids(ids, 4)
    assert len(chunks) == 4
    assert [len(c) for c in chunks] == [5, 5, 5, 5]
    assert [x for c in chunks for x in c] == ids


def test_skip_existing_cards_png(tmp_path) -> None:
    kids = [KidProfile(id=f"k{i}", name=f"Kid{i}", age=7) for i in range(3)]
    store = MemoryStorage()
    store.upload("cards/k0.png", b"png")
    todo, skipped = skip_existing(kids, store)
    assert skipped == ["k0"]
    assert [k.id for k in todo] == ["k1", "k2"]


def test_load_kids_from_csv(tmp_path) -> None:
    csv_path = tmp_path / "kids.csv"
    csv_path.write_text(
        "id,name,age,wishlist\na,Emma,7,telescope\nb,Lucas,5,train\n",
        encoding="utf-8",
    )
    kids = load_kids(csv_path, 2)
    assert [k.name for k in kids] == ["Emma", "Lucas"]
    assert kids[0].age == 7 and kids[0].wishlist == ["telescope"]


def test_job_payload_from_yaml_job_block(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", "k")
    monkeypatch.setenv("IMAGE_ENDPOINT_URL", "https://img.example/")
    monkeypatch.setenv("IMAGE_ENDPOINT_TOKEN", "t")
    monkeypatch.setenv("NEBIUS_BUCKET_ID", "bucket-abc")
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "proj-1")
    monkeypatch.setenv("NEBIUS_SUBNET_ID", "subnet-1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    src = Path(__file__).resolve().parents[1] / "config" / "models.yaml"
    text = src.read_text(encoding="utf-8").replace(
        'image: ""', 'image: "cr.example/santa-job:test"'
    )
    path = tmp_path / "models.yaml"
    path.write_text(text, encoding="utf-8")
    s = Settings.load(path, env_file=NOENV)
    p = job_payload(s, run_id="r1", chunk="runs/r1/chunks/0.json")
    assert p.image == "cr.example/santa-job:test"
    assert p.platform == "gpu-h100-sxm"
    assert p.preset == "1gpu-16vcpu-200gb"
    assert p.preemptible is True
    assert p.disk_gb == 250
    assert p.mount_path == "/data"
    assert p.bucket_id == "bucket-abc"
    assert p.env["RUN_ID"] == "r1"
    assert p.env["CHUNK"] == "/data/runs/r1/chunks/0.json"
    assert p.env["HF_HOME"] == "/data/models"


class FakeJobService:
    def __init__(self, states: list[str]) -> None:
        self.states = list(states)
        self.created: list = []
        self.cancelled: list[str] = []
        self._i = 0

    def create(self, payload) -> str:
        self.created.append(payload)
        return "job-1"

    def get(self, job_id: str) -> str:
        i = min(self._i, len(self.states) - 1)
        state = self.states[i]
        self._i += 1
        return state

    def cancel(self, job_id: str) -> None:
        self.cancelled.append(job_id)


def test_create_and_wait_records_timeline() -> None:
    svc = FakeJobService(["PENDING", "RUNNING", "COMPLETED"])
    payload = SimpleNamespace()  # unused beyond create
    result = create_and_wait(svc, payload, poll_s=0, sleep=lambda s: None)
    assert result.job_id == "job-1"
    assert [t.state for t in result.timeline] == ["PENDING", "RUNNING", "COMPLETED"]
    assert svc.cancelled == []


def test_create_and_wait_failed_job_raises() -> None:
    svc = FakeJobService(["PENDING", "FAILED"])
    with pytest.raises(NebiusJobError, match="FAILED"):
        create_and_wait(svc, SimpleNamespace(), poll_s=0, sleep=lambda s: None)


def test_h100_and_cpu_e2_cost_matches_nebius_prices() -> None:
    # docs.nebius.com/compute/resources/pricing — 2026-09-07 (from 1 June 2026)
    assert hourly_rate("gpu-h100-sxm", "1gpu-16vcpu-200gb", preemptible=True).usd_per_hour == 2.15
    assert hourly_rate("gpu-h100-sxm", "1gpu-16vcpu-200gb", preemptible=False).usd_per_hour == 3.85
    cpu = hourly_rate("cpu-e2", "2vcpu-8gb")
    assert cpu.usd_per_hour == pytest.approx(2 * 0.012 + 8 * 0.0032)
    assert cost_usd("gpu-h100-sxm", "1gpu-16vcpu-200gb", 1800, preemptible=True) == pytest.approx(
        1.075
    )
    assert on_demand_cost_usd("gpu-h100-sxm", "1gpu-16vcpu-200gb", 3600) == 3.85


def test_staged_write_renames_into_place(tmp_path) -> None:
    dest = tmp_path / "videos" / "k1.mp4"
    staged_write(dest, b"mp4-bytes")
    assert dest.read_bytes() == b"mp4-bytes"
    assert not list(tmp_path.rglob("*.tmp"))


def test_cards_phase_skips_existing_and_writes_four_chunks(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", "k")
    monkeypatch.setenv("IMAGE_ENDPOINT_URL", "https://img.example/")
    monkeypatch.setenv("IMAGE_ENDPOINT_TOKEN", "t")
    kids = [
        KidProfile(id=f"k{i:02d}", name=f"Kid{i}", age=7, wishlist=["train"]) for i in range(20)
    ]
    store = MemoryStorage()
    store.upload("cards/k00.png", b"already")
    store.upload("cards/k00.json", json.dumps({"wish": {"mood": "cozy"}}).encode())

    @dataclass
    class FakeWish:
        mood: str = "playful"

    @dataclass
    class FakeCard:
        png_path: str
        html_path: str | None
        wish: FakeWish

    @dataclass
    class FakeRun:
        card: FakeCard

    def fake_make(kid, settings, **kw):
        out = Path(kw["out_root"]) / kid.id
        out.mkdir(parents=True, exist_ok=True)
        png = out / "card.png"
        png.write_bytes(b"png")
        (out / "card.json").write_text(json.dumps({"wish": {"mood": "playful"}}), encoding="utf-8")
        return FakeRun(card=FakeCard(png_path=str(png), html_path=None, wish=FakeWish()))

    phase = run_cards_phase(
        kids=kids,
        n_jobs=4,
        run_id="r1",
        run_dir=tmp_path / "r1",
        storage=store,
        settings=Settings.load(env_file=NOENV),
        local=True,
        make_card=fake_make,
    )
    assert phase.skipped == ["k00"]
    assert len(phase.made) == 19
    assert len(phase.chunks) == 4
    first = json.loads(phase.chunks[0].read_text(encoding="utf-8"))
    assert first[0] == {"id": "k00", "mood": "cozy"}  # skipped, mood from cards/k00.json
    assert store.exists("cards/k01.png")
    assert store.exists("runs/r1/chunks/0.json")


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, **kw):
        self.objects[kw["Key"]] = kw["Body"]

    def head_object(self, **kw):
        if kw["Key"] not in self.objects:
            err = Exception("404")
            err.response = {  # type: ignore[attr-defined]
                "Error": {"Code": "404"},
                "ResponseMetadata": {"HTTPStatusCode": 404},
            }
            raise err
        return {}

    def get_object(self, **kw):
        return {"Body": type("B", (), {"read": lambda self: self.objects[kw["Key"]]})()}

    def list_objects_v2(self, **kw):
        prefix = kw.get("Prefix") or ""
        keys = [k for k in self.objects if k.startswith(prefix)]
        return {"Contents": [{"Key": k} for k in keys], "IsTruncated": False}


def test_storage_boto_upload_exists_list_download() -> None:
    from santa.storage import Storage

    s3 = FakeS3()
    store = Storage(s3, "demo-bucket")
    store.upload("cards/a.png", b"png")
    assert store.exists("cards/a.png")
    assert not store.exists("cards/missing.png")
    assert store.list("cards/") == ["cards/a.png"]
    # get_object Body.read on FakeS3 is a bit awkward — re-upload check via objects
    assert s3.objects["cards/a.png"] == b"png"


def test_to_sdk_spec_mounts_bucket_and_env() -> None:
    from santa.nebius_jobs import JobPayload, to_sdk_spec

    payload = JobPayload(
        image="cr.example/santa-job:t",
        platform="gpu-h100-sxm",
        preset="1gpu-16vcpu-200gb",
        preemptible=True,
        disk_gb=250,
        timeout_min=90,
        mount_path="/data",
        bucket_id="bucket-abc",
        env={"RUN_ID": "r1", "CHUNK": "/data/runs/r1/chunks/0.json", "HF_HOME": "/data/models"},
        subnet_id="subnet-1",
    )
    spec = to_sdk_spec(payload)
    assert spec.image == "cr.example/santa-job:t"
    assert spec.platform == "gpu-h100-sxm"
    assert spec.preset == "1gpu-16vcpu-200gb"
    assert spec.preemptible is True
    assert spec.volumes[0].source == "bucket-abc"
    assert spec.volumes[0].container_path == "/data"
    names = {e.name: e.value for e in spec.environment_variables}
    assert names["RUN_ID"] == "r1" and names["HF_HOME"] == "/data/models"


def test_cards_phase_uses_service_when_url_set(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", "k")
    monkeypatch.setenv("IMAGE_ENDPOINT_URL", "https://img.example/")
    monkeypatch.setenv("IMAGE_ENDPOINT_TOKEN", "t")
    kids = [KidProfile(id="k1", name="Emma", age=7)]
    store = MemoryStorage()
    store.upload("cards/k1.json", json.dumps({"wish": {"mood": "playful"}}).encode())
    posted: list = []

    def post(url, batch_kids):
        posted.append((url, [k.id for k in batch_kids]))
        return [k.id for k in batch_kids]

    phase = run_cards_phase(
        kids=kids,
        n_jobs=1,
        run_id="r2",
        run_dir=tmp_path / "r2",
        storage=store,
        settings=Settings.load(env_file=NOENV),
        local=False,
        service_url="https://santa.example",
        post_batch=post,
    )
    assert phase.used_service is True
    assert posted == [("https://santa.example", ["k1"])]
    chunk = json.loads(phase.chunks[0].read_text(encoding="utf-8"))
    assert chunk == [{"id": "k1", "mood": "playful"}]


def test_batch_cli_writes_chunks(tmp_path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from santa.cli import app

    csv_path = tmp_path / "kids.csv"
    csv_path.write_text("id,name,age,wishlist\na,Emma,7,train\nb,Leo,8,sled\n", encoding="utf-8")

    def fake_phase(**kw):
        run_dir = kw["run_dir"]
        (run_dir / "chunks").mkdir(parents=True, exist_ok=True)
        p = run_dir / "chunks" / "0.json"
        p.write_text("[]", encoding="utf-8")
        return SimpleNamespace(
            run_id=kw["run_id"],
            run_dir=run_dir,
            made=["a", "b"],
            skipped=[],
            chunks=[p],
        )

    monkeypatch.setattr("santa.batch.run_cards_phase", fake_phase)
    monkeypatch.setattr("santa.cli.Settings.load", lambda: object())
    monkeypatch.setattr("santa.storage.Storage.from_env", lambda: MemoryStorage())
    result = CliRunner().invoke(
        app,
        [
            "batch",
            "--kids",
            "2",
            "--jobs",
            "1",
            "--local",
            "--kids-csv",
            str(csv_path),
            "--out",
            str(tmp_path),
            "--run-id",
            "cli1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "cli1" in result.output
    assert "made 2" in result.output


def test_sdk_job_service_requires_iam_token(monkeypatch) -> None:
    from santa.nebius_jobs import SdkJobService

    monkeypatch.delenv("NEBIUS_IAM_TOKEN", raising=False)
    with pytest.raises(NebiusJobError, match="NEBIUS_IAM_TOKEN"):
        SdkJobService.from_env()


def test_sdk_job_service_create_uses_project_id() -> None:
    from santa.nebius_jobs import JobPayload, SdkJobService

    captured: dict = {}

    class Wait:
        def wait(self):
            class Op:
                resource_id = "job-live"

                def sync_wait(self):
                    return None

            return Op()

    class Client:
        def create(self, request):
            captured["parent"] = request.metadata.parent_id
            captured["name"] = request.metadata.name
            captured["image"] = request.spec.image
            return Wait()

        def get(self, request):
            return Wait()

        def cancel(self, request):
            captured["cancel"] = request.id
            return Wait()

    svc = SdkJobService(Client(), project_id="proj-fallback")
    payload = JobPayload(
        image="cr.example/santa-job:t",
        platform="gpu-h100-sxm",
        preset="1gpu-16vcpu-200gb",
        preemptible=True,
        disk_gb=1,
        timeout_min=5,
        mount_path="/data",
        bucket_id="b",
        env={"RUN_ID": "r"},
        project_id="proj-1",
        name="santa-r",
    )
    assert svc.create(payload) == "job-live"
    assert captured["parent"] == "proj-1"
    assert captured["image"] == "cr.example/santa-job:t"
    svc.cancel("job-live")
    assert captured["cancel"] == "job-live"
