"""Batch Jobs-only: inventory cards/*.png, skip existing videos, fake JobService."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from santa.batch import BatchError, chunk_ids, inventory_card_ids, load_kids, require_card_ids
from santa.config import Settings
from santa.cost import cost_usd, hourly_rate, on_demand_cost_usd
from santa.nebius_jobs import NebiusJobError, create_and_wait, job_payload
from santa.storage import MemoryStorage, staged_write

NOENV = Path("/nonexistent")


def test_chunking_20_kids_into_4_jobs() -> None:
    ids = [f"k{i:02d}" for i in range(20)]
    chunks = chunk_ids(ids, 4)
    assert len(chunks) == 4
    assert [len(c) for c in chunks] == [5, 5, 5, 5]
    assert [x for c in chunks for x in c] == ids


def test_inventory_lists_png_stems_under_cards() -> None:
    store = MemoryStorage()
    store.upload("cards/k00.png", b"png")
    store.upload("cards/k01.png", b"png")
    store.upload("cards/k01.json", b"{}")
    store.upload("cards/k00.html", b"<html>")
    store.upload("other/k99.png", b"nope")
    assert inventory_card_ids(store) == ["k00", "k01"]


def test_empty_cards_prefix_is_an_error() -> None:
    store = MemoryStorage()
    store.upload("videos/k00.mp4", b"mp4")
    with pytest.raises(BatchError, match="santa card") as exc:
        require_card_ids(store)
    assert "--publish" in str(exc.value)


def test_rerun_chunking_excludes_existing_videos() -> None:
    from santa.batch import ids_missing_videos

    store = MemoryStorage()
    store.upload("videos/k00.mp4", b"mp4")
    store.upload("videos/k01.mp4", b"mp4")
    ids = [f"k{i:02d}" for i in range(4)]
    missing, have = ids_missing_videos(ids, store)
    assert have == ["k00", "k01"]
    assert missing == ["k02", "k03"]
    chunks = chunk_ids(missing, 4)
    assert chunks == [["k02"], ["k03"]]


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


def test_storage_from_env_uses_path_style_on_nebius_endpoint(monkeypatch) -> None:
    from santa.storage import Storage

    captured: dict = {}

    def fake_client(service, **kw):
        captured["service"] = service
        captured.update(kw)
        return FakeS3()

    monkeypatch.setenv("NEBIUS_BUCKET_NAME", "demo-bucket")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIATEST")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("AWS_ENDPOINT_URL", "https://storage.eu-north1.nebius.cloud:443/")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-north1")
    monkeypatch.setattr("boto3.client", fake_client)
    store = Storage.from_env()
    assert store.bucket == "demo-bucket"
    assert captured["aws_access_key_id"] == "AKIATEST"
    assert captured["endpoint_url"] == "https://storage.eu-north1.nebius.cloud"
    assert captured["config"].s3["addressing_style"] == "path"
    assert captured["verify"]  # system CA bundle or True


def test_storage_from_env_requires_access_keys(monkeypatch) -> None:
    from santa.storage import Storage, StorageError

    monkeypatch.setenv("NEBIUS_BUCKET_NAME", "demo-bucket")
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    with pytest.raises(StorageError, match="AWS_ACCESS_KEY_ID"):
        Storage.from_env()


def test_storage_exists_403_names_access_keys() -> None:
    from santa.storage import Storage, StorageError

    class Deny:
        def head_object(self, **kw):
            err = Exception("Forbidden")
            err.response = {  # type: ignore[attr-defined]
                "Error": {"Code": "AccessDenied"},
                "ResponseMetadata": {"HTTPStatusCode": 403},
            }
            raise err

    with pytest.raises(StorageError, match="AWS_ACCESS_KEY"):
        Storage(Deny(), "demo-bucket").exists("cards/k01.png")


def test_storage_list_access_denied_names_bucket() -> None:
    from santa.storage import Storage, StorageError

    class Deny:
        def list_objects_v2(self, **kw):
            err = Exception("AccessDenied")
            err.response = {  # type: ignore[attr-defined]
                "Error": {"Code": "AccessDenied"},
                "ResponseMetadata": {"HTTPStatusCode": 403},
            }
            raise err

    with pytest.raises(StorageError, match="NEBIUS_BUCKET_NAME"):
        Storage(Deny(), "demo-bucket").list("cards/")


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


def _png_store(*ids: str, videos: tuple[str, ...] = ()) -> MemoryStorage:
    store = MemoryStorage()
    for kid_id in ids:
        store.upload(f"cards/{kid_id}.png", b"png")
    for kid_id in videos:
        store.upload(f"videos/{kid_id}.mp4", b"mp4")
    return store


def _wire_batch_cli(tmp_path, monkeypatch, store: MemoryStorage, svc: ScriptedJobService):
    """Inject Settings, in-memory storage, and a fake Job service at CLI boundaries."""
    settings = _job_settings(tmp_path, monkeypatch)
    order: list[str] = []

    def load():
        order.append("load")
        return settings

    def store_from_env():
        order.append("storage")
        return store

    def jobs_from_env():
        order.append("jobs")
        return svc

    monkeypatch.setattr("santa.cli.Settings.load", load)
    monkeypatch.setattr("santa.storage.Storage.from_env", store_from_env)
    monkeypatch.setattr("santa.nebius_jobs.SdkJobService.from_env", jobs_from_env)
    return settings, order


def test_batch_cli_rejects_kids_option() -> None:
    from typer.testing import CliRunner

    from santa.cli import app

    result = CliRunner().invoke(app, ["batch", "--kids", "20"])
    assert result.exit_code != 0
    assert "no such option" in result.output.lower()
    assert "--kids" in result.output
    for flag in ("--kids-csv", "--local"):
        denied = CliRunner().invoke(app, ["batch", flag])
        assert denied.exit_code != 0
        assert "no such option" in denied.output.lower()


def test_batch_cli_empty_cards_exits_before_jobs(tmp_path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from santa.cli import app

    svc = ScriptedJobService([])
    _, order = _wire_batch_cli(tmp_path, monkeypatch, MemoryStorage(), svc)
    result = CliRunner().invoke(app, ["batch", "--jobs", "4", "--out", str(tmp_path)])
    assert result.exit_code != 0, result.output
    assert "santa card" in result.output
    assert "--publish" in result.output
    assert "jobs" not in order  # Job service is constructed only after inventory
    assert svc.created == []


def test_batch_cli_three_pngs_submits_jobs_covering_ids(tmp_path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from santa.cli import app

    store = _png_store("k00", "k01", "k02")
    store.upload("cards/k00.json", json.dumps({"wish": {"mood": "cozy"}}).encode())
    store.upload("videos/k01.mp4", b"mp4")
    svc = ScriptedJobService([["PENDING"], ["PENDING"]])

    def boom_make(*args, **kwargs):
        raise AssertionError("santa batch must not manufacture GiftCards")

    monkeypatch.setattr("santa.card.make_card", boom_make)
    monkeypatch.setenv("SANTA_SERVICE_URL", "https://santa.example")
    _wire_batch_cli(tmp_path, monkeypatch, store, svc)
    result = CliRunner().invoke(
        app,
        ["batch", "--jobs", "4", "--no-wait", "--out", str(tmp_path), "--run-id", "cli1"],
    )
    assert result.exit_code == 0, result.output
    assert "submitted" in result.output
    assert "--status cli1" in result.output
    submitted: list[str] = []
    moods: dict[str, str] = {}
    for payload in svc.created:
        assert payload.image == "cr.example/santa-job:test"
        key = payload.env["CHUNK"].removeprefix("/data/")
        for row in json.loads(store.download(key).decode()):
            submitted.append(row["id"])
            moods[row["id"]] = row["mood"]
    assert sorted(submitted) == ["k00", "k02"]
    assert moods["k00"] == "cozy"
    assert moods["k02"] == "warm"
    assert len(svc.created) == 2  # K shrinks; no empty Jobs


def test_batch_cli_three_pngs_no_videos_covers_all_ids(tmp_path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from santa.cli import app

    store = _png_store("k00", "k01", "k02")
    svc = ScriptedJobService([["PENDING"], ["PENDING"], ["PENDING"]])
    _wire_batch_cli(tmp_path, monkeypatch, store, svc)
    result = CliRunner().invoke(
        app,
        ["batch", "--jobs", "4", "--no-wait", "--out", str(tmp_path), "--run-id", "all3"],
    )
    assert result.exit_code == 0, result.output
    submitted: list[str] = []
    for payload in svc.created:
        key = payload.env["CHUNK"].removeprefix("/data/")
        submitted.extend(row["id"] for row in json.loads(store.download(key).decode()))
    assert sorted(submitted) == ["k00", "k01", "k02"]
    assert len(svc.created) == 3


def test_batch_cli_loads_dotenv_before_storage(tmp_path, monkeypatch) -> None:
    """`.env` is only loaded in Settings.load(); storage must not run first (empty env)."""
    from typer.testing import CliRunner

    from santa.cli import app

    store = _png_store("a")
    svc = ScriptedJobService([["PENDING"]])
    _, order = _wire_batch_cli(tmp_path, monkeypatch, store, svc)
    result = CliRunner().invoke(
        app,
        ["batch", "--jobs", "1", "--no-wait", "--out", str(tmp_path), "--run-id", "dotenv1"],
    )
    assert result.exit_code == 0, result.output
    assert order[:2] == ["load", "storage"]


def test_batch_cli_status_resumes(tmp_path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from santa.cli import app

    run_dir = tmp_path / "runs" / "st1"
    run_dir.mkdir(parents=True)
    (run_dir / "ticket.json").write_text(
        json.dumps({"run_id": "st1", "kids": ["a"], "jobs": []}) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        "santa.batch.resume_jobs_phase",
        lambda **kw: {
            "run_id": "st1",
            "jobs": [],
            "totals": {
                "done": 1,
                "skipped": 0,
                "failed": 0,
                "cost_usd": 0,
                "on_demand_cost_usd": 0,
            },
            "savings_usd": 0,
        },
    )
    monkeypatch.setattr("santa.cli.Settings.load", lambda: object())
    monkeypatch.setattr("santa.storage.Storage.from_env", lambda: MemoryStorage())
    monkeypatch.setattr("santa.nebius_jobs.SdkJobService.from_env", lambda: object())
    result = CliRunner().invoke(app, ["batch", "--status", "st1", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "done 1" in result.output


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


def test_summary_math_from_fake_records() -> None:
    from santa.batch import JobRecord, build_run_summary

    rec = JobRecord(
        job_id="job-1",
        chunk="runs/r1/chunks/0.json",
        platform="gpu-h100-sxm",
        preset="1gpu-16vcpu-200gb",
        preemptible=True,
        state_transitions=[{"state": "COMPLETED", "at": 1.0}],
        run_s=1800.0,
        done=["a"],
        skipped=["b"],
        failed=[],
    )
    summary = build_run_summary("r1", kids=["a", "b"], jobs=[rec])
    assert summary["jobs"][0]["cost_usd"] == pytest.approx(1.075)
    assert summary["jobs"][0]["on_demand_cost_usd"] == pytest.approx(1.925)
    assert summary["totals"]["cost_usd"] == pytest.approx(1.075)
    assert summary["totals"]["on_demand_cost_usd"] == pytest.approx(1.925)
    assert summary["savings_usd"] == pytest.approx(0.85)
    assert summary["totals"]["done"] == 1
    assert summary["totals"]["skipped"] == 1
    assert summary["totals"]["failed"] == 0


def _job_settings(tmp_path: Path, monkeypatch) -> Settings:
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", "k")
    monkeypatch.setenv("IMAGE_ENDPOINT_URL", "https://img.example/")
    monkeypatch.setenv("IMAGE_ENDPOINT_TOKEN", "t")
    monkeypatch.setenv("NEBIUS_BUCKET_ID", "bucket-abc")
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "proj-1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    src = Path(__file__).resolve().parents[1] / "config" / "models.yaml"
    text = src.read_text(encoding="utf-8").replace(
        'image: ""', 'image: "cr.example/santa-job:test"'
    )
    path = tmp_path / "models.yaml"
    path.write_text(text, encoding="utf-8")
    return Settings.load(path, env_file=NOENV)


class ScriptedJobService:
    """One state script per job, keyed by chunk index in the payload name (``santa-run-k``)."""

    def __init__(self, scripts: list[list[str]]) -> None:
        self.scripts = scripts
        self.created: list = []
        self.cancelled: list[str] = []
        self._idx: dict[str, int] = {}
        self._lock = threading.Lock()

    def create(self, payload) -> str:
        stem = str(getattr(payload, "name", "") or "").rsplit("-", 1)[-1]
        jid = f"job-{stem}" if stem else f"job-{len(self.created)}"
        with self._lock:
            self.created.append(payload)
            self._idx.setdefault(jid, 0)
        return jid

    def get(self, job_id: str) -> str:
        states = self.scripts[int(job_id.split("-")[1])]
        with self._lock:
            i = self._idx.get(job_id, 0)
            self._idx[job_id] = i + 1
        return states[min(i, len(states) - 1)]

    def cancel(self, job_id: str) -> None:
        self.cancelled.append(job_id)


def test_one_error_job_summary_has_three_done_and_failed_ids(tmp_path, monkeypatch) -> None:
    from santa.batch import run_jobs_phase

    settings = _job_settings(tmp_path, monkeypatch)
    store = MemoryStorage()
    kids = [f"k{i:02d}" for i in range(20)]
    run_dir = tmp_path / "r1"
    # 4 chunks of 5: jobs 0–2 succeed and wrote status; job 3 ERRORs with no json
    for k in range(3):
        ids = kids[k * 5 : (k + 1) * 5]
        store.upload(
            f"runs/r1/jobs/{k}.json",
            json.dumps(
                {
                    "run_id": "r1",
                    "chunk": str(k),
                    "items": [{"id": i, "status": "done", "seconds": 1.0} for i in ids],
                }
            ).encode(),
        )
    svc = ScriptedJobService(
        [
            ["PENDING", "RUNNING", "COMPLETED"],
            ["PENDING", "RUNNING", "COMPLETED"],
            ["PENDING", "RUNNING", "COMPLETED"],
            ["PENDING", "ERROR"],
        ]
    )
    summary = run_jobs_phase(
        kids=kids,
        n_jobs=4,
        run_id="r1",
        run_dir=run_dir,
        storage=store,
        settings=settings,
        service=svc,
        wait=True,
        poll_s=0,
        sleep=lambda _s: None,
    )
    assert len(svc.created) == 4
    assert summary["totals"]["done"] == 15
    assert summary["jobs"][3]["failed"] == ["k15", "k16", "k17", "k18", "k19"]
    assert summary["totals"]["failed"] == 5
    completed = [j for j in summary["jobs"] if j["failed"] == []]
    assert len(completed) == 3
    assert store.exists("runs/r1/summary.json")
    assert (run_dir / "summary.json").is_file()


def test_kill_one_rerun_only_resubmits_the_gap(tmp_path, monkeypatch) -> None:
    """Cancelling/ERROR on one job, then same run-id, only missing videos are chunked."""
    from santa.batch import run_jobs_phase

    settings = _job_settings(tmp_path, monkeypatch)
    store = MemoryStorage()
    kids = [f"k{i:02d}" for i in range(4)]
    store.upload(
        "runs/gap/jobs/0.json",
        json.dumps(
            {
                "run_id": "gap",
                "chunk": "0",
                "items": [
                    {"id": "k00", "status": "done", "seconds": 1},
                    {"id": "k01", "status": "done", "seconds": 1},
                ],
            }
        ).encode(),
    )
    first = ScriptedJobService([["COMPLETED"], ["ERROR"]])
    run_jobs_phase(
        kids=kids,
        n_jobs=2,
        run_id="gap",
        run_dir=tmp_path / "gap",
        storage=store,
        settings=settings,
        service=first,
        wait=True,
        poll_s=0,
        sleep=lambda _s: None,
    )
    store.upload("videos/k00.mp4", b"mp4")
    store.upload("videos/k01.mp4", b"mp4")
    store.upload(
        "runs/gap/jobs/0.json",
        json.dumps(
            {
                "run_id": "gap",
                "chunk": "0",
                "items": [{"id": "k02", "status": "done", "seconds": 1}],
            }
        ).encode(),
    )
    store.upload(
        "runs/gap/jobs/1.json",
        json.dumps(
            {
                "run_id": "gap",
                "chunk": "1",
                "items": [{"id": "k03", "status": "done", "seconds": 1}],
            }
        ).encode(),
    )
    second = ScriptedJobService([["COMPLETED"], ["COMPLETED"]])
    summary = run_jobs_phase(
        kids=kids,
        n_jobs=2,
        run_id="gap",
        run_dir=tmp_path / "gap",
        storage=store,
        settings=settings,
        service=second,
        wait=True,
        poll_s=0,
        sleep=lambda _s: None,
    )
    assert len(second.created) == 2
    submitted: list[str] = []
    for payload in second.created:
        key = payload.env["CHUNK"].removeprefix("/data/")
        submitted.extend(row["id"] for row in json.loads(store.download(key).decode()))
    assert sorted(submitted) == ["k02", "k03"]
    assert summary["totals"]["done"] == 2


def test_jobs_phase_rerun_submits_only_missing_videos(tmp_path, monkeypatch) -> None:
    from santa.batch import run_jobs_phase

    settings = _job_settings(tmp_path, monkeypatch)
    store = MemoryStorage()
    kids = [f"k{i:02d}" for i in range(4)]
    for i in ("k00", "k01"):
        store.upload(f"videos/{i}.mp4", b"mp4")
    store.upload(
        "runs/r2/jobs/0.json",
        json.dumps(
            {"run_id": "r2", "chunk": "0", "items": [{"id": "k02", "status": "done", "seconds": 1}]}
        ).encode(),
    )
    store.upload(
        "runs/r2/jobs/1.json",
        json.dumps(
            {"run_id": "r2", "chunk": "1", "items": [{"id": "k03", "status": "done", "seconds": 1}]}
        ).encode(),
    )
    svc = ScriptedJobService([["COMPLETED"], ["COMPLETED"]])
    summary = run_jobs_phase(
        kids=kids,
        n_jobs=4,
        run_id="r2",
        run_dir=tmp_path / "r2",
        storage=store,
        settings=settings,
        service=svc,
        wait=True,
        poll_s=0,
        sleep=lambda _s: None,
    )
    assert len(svc.created) == 2
    ids_submitted = []
    for payload in svc.created:
        chunk_key = payload.env["CHUNK"].removeprefix("/data/")
        ids_submitted.extend(json.loads(store.download(chunk_key).decode()))
    assert [row["id"] for row in ids_submitted] == ["k02", "k03"]
    assert summary["totals"]["done"] == 2


def test_no_wait_writes_ticket_not_summary(tmp_path, monkeypatch) -> None:
    from santa.batch import run_jobs_phase

    settings = _job_settings(tmp_path, monkeypatch)
    store = MemoryStorage()
    svc = ScriptedJobService([["PENDING"], ["PENDING"]])
    result = run_jobs_phase(
        kids=["a", "b"],
        n_jobs=2,
        run_id="r3",
        run_dir=tmp_path / "r3",
        storage=store,
        settings=settings,
        service=svc,
        wait=False,
    )
    assert result["waiting"] is True
    assert len(result["jobs"]) == 2
    assert store.exists("runs/r3/ticket.json")
    assert not store.exists("runs/r3/summary.json")
    assert (tmp_path / "r3" / "ticket.json").is_file()


def test_resume_waits_on_ticket_jobs(tmp_path, monkeypatch) -> None:
    from santa.batch import resume_jobs_phase, run_jobs_phase

    settings = _job_settings(tmp_path, monkeypatch)
    store = MemoryStorage()
    create_svc = ScriptedJobService([["PENDING"], ["PENDING"]])
    ticket_run = run_jobs_phase(
        kids=["a", "b"],
        n_jobs=2,
        run_id="r4",
        run_dir=tmp_path / "r4",
        storage=store,
        settings=settings,
        service=create_svc,
        wait=False,
    )
    for k, kid in enumerate(["a", "b"]):
        store.upload(
            f"runs/r4/jobs/{k}.json",
            json.dumps(
                {
                    "run_id": "r4",
                    "chunk": str(k),
                    "items": [{"id": kid, "status": "done", "seconds": 1}],
                }
            ).encode(),
        )
    wait_svc = ScriptedJobService([["RUNNING", "COMPLETED"], ["COMPLETED"]])
    wait_svc.created = list(create_svc.created)

    def get(job_id: str) -> str:
        return ScriptedJobService.get(wait_svc, job_id)

    wait_svc.get = get  # type: ignore[method-assign]
    # ScriptedJobService.get uses create-order index from job-0, job-1 ids
    wait_svc._idx = {"job-0": 0, "job-1": 0}
    summary = resume_jobs_phase(
        ticket=json.loads((tmp_path / "r4" / "ticket.json").read_text(encoding="utf-8")),
        run_dir=tmp_path / "r4",
        storage=store,
        settings=settings,
        service=wait_svc,
        poll_s=0,
        sleep=lambda _s: None,
    )
    assert summary["totals"]["done"] == 2
    assert ticket_run["waiting"] is True


def test_interrupt_cancels_all_submitted_jobs(tmp_path, monkeypatch) -> None:
    from santa.batch import run_jobs_phase

    settings = _job_settings(tmp_path, monkeypatch)

    class Boom(ScriptedJobService):
        def get(self, job_id: str) -> str:
            raise KeyboardInterrupt

    svc = Boom([["PENDING"], ["PENDING"]])
    with pytest.raises(KeyboardInterrupt):
        run_jobs_phase(
            kids=["a", "b"],
            n_jobs=2,
            run_id="r5",
            run_dir=tmp_path / "r5",
            storage=MemoryStorage(),
            settings=settings,
            service=svc,
            wait=True,
            poll_s=0,
            sleep=lambda _s: None,
        )
    assert set(svc.cancelled) == {"job-0", "job-1"}
