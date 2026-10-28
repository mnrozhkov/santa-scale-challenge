"""Experiment B: evaluate-before-escalate agent tests (fakes + FunctionModel)."""

from __future__ import annotations

import base64
import json
import subprocess
from types import SimpleNamespace

import pytest
from PIL import Image
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import FunctionModel

from santa.agent.judge import evaluate_video, motion_metric
from santa.agent.policy import Policy
from santa.agent.runner import run_kids
from santa.agent.state import Evaluation
from santa.card import generate_image, recommend_gift, validate_profile
from santa.config import Settings
from santa.cost import cost_usd
from santa.mux import ffmpeg_exe
from santa.prompts import image_prompt

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self._t = start

    def time(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds


class FakeLLM:
    used_fallback = False
    model_version = "fake-llm"
    last_metrics = {"latency_ms": 12, "fallback": False}
    cfg = SimpleNamespace(model="fake-llm", base_url="https://tf.example", is_fallback=False)

    def generate_json(self, prompt: str, **kw):
        if "rationale" in prompt:
            return {"gifts": ["telescope", "star chart"], "rationale": "loves the sky"}
        return {
            "wish": "Dear Alex, may your telescope find a bright new star. Merry Christmas!",
            "mood": "warm",
        }


class FakeImage:
    used_fallback = False
    model_version = "fake-image"
    last_metrics = {"latency_ms": 1000, "fallback": False}
    cfg = SimpleNamespace(model="sana", base_url="https://img.example/", is_fallback=False)

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def generate(self, prompt: str, *, seed=None) -> bytes:
        self.calls.append({"prompt": prompt, "seed": seed})
        return PNG_1PX


class FakeVideo:
    used_fallback = False
    model_version = "fake-video"
    last_metrics = {"latency_ms": 2000, "fallback": False}
    cfg = SimpleNamespace(model="wan", base_url="https://vid.example/", is_fallback=False)

    def __init__(self, mp4_bytes: bytes) -> None:
        self.mp4_bytes = mp4_bytes
        self.calls: list[dict] = []

    def generate(self, prompt: str, *, image: bytes, seed=None) -> bytes:
        self.calls.append({"prompt": prompt, "seed": seed, "image_len": len(image)})
        return self.mp4_bytes


class FakeVLM:
    used_fallback = False
    model_version = "fake-vlm"
    last_metrics = {"latency_ms": 5, "fallback": False}
    cfg = SimpleNamespace(model="fake-vlm", base_url="https://vlm.example", is_fallback=False)

    def __init__(self, script: list[Evaluation] | None = None) -> None:
        self.script = list(script or [])
        self.calls = 0

    def generate_json_vision(self, prompt: str, images: list[bytes], **kw):
        self.calls += 1
        if not self.script:
            return {
                "decision": "PASS",
                "score": 90,
                "reasons": ["ok"],
                "fix": "none",
                "prompt_suffix": "",
                "cause": "none",
            }
        return self.script.pop(0).model_dump()


def _tiny_mp4(tmp_path) -> bytes:
    """Short mp4 with real motion so the static-frame override does not fire."""
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    Image.new("RGB", (64, 64), color=(200, 100, 50)).save(a)
    Image.new("RGB", (64, 64), color=(50, 100, 200)).save(b)
    list_file = tmp_path / "frames.txt"
    # 8 frames alternating — enough motion for metric ∈ (0.01, 0.35)
    lines = []
    for i in range(8):
        lines.append(f"file '{a if i < 4 else b}'")
        lines.append("duration 0.05")
    lines.append(f"file '{b}'")
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = tmp_path / "tiny.mp4"
    cmd = [
        ffmpeg_exe(),
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "16",
        str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out.read_bytes()


def _done_tools(messages) -> list[str]:
    done: list[str] = []
    for message in messages:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, ToolReturnPart):
                    done.append(part.tool_name)
    return done


def _last_return(messages, tool: str) -> dict | None:
    for message in reversed(messages):
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, ToolReturnPart) and part.tool_name == tool:
                    content = part.content
                    if isinstance(content, dict):
                        return content
                    if isinstance(content, str):
                        try:
                            return json.loads(content)
                        except json.JSONDecodeError:
                            return {"raw": content}
    return None


def _settings() -> Settings:
    return Settings.load()


@pytest.fixture
def mp4_bytes(tmp_path) -> bytes:
    return _tiny_mp4(tmp_path)


def test_prompt_suffix_empty_keeps_baseline() -> None:
    kid = validate_profile("Alex", 7, "telescope")
    llm, image = FakeLLM(), FakeImage()
    rec = recommend_gift(kid, llm)
    _, meta = generate_image(kid, rec, image, prompt_suffix="")
    assert meta.prompt == image_prompt(kid, rec)


def test_yaml_loads_with_policy_and_compute() -> None:
    s = Settings.load()
    assert s.policy.budget_usd == 1.50
    assert s.role("image").compute is not None
    assert s.role("image").compute.platform.startswith("gpu-l40s")


def _happy_model(clock: FakeClock | None = None):
    def model_fn(messages, info):
        done = _done_tools(messages)
        if "recommend_gift" not in done:
            return ModelResponse(parts=[ToolCallPart("recommend_gift", {})])
        if "write_wish" not in done:
            return ModelResponse(parts=[ToolCallPart("write_wish", {})])
        if "generate_image" not in done:
            if clock:
                clock.advance(1.0)
            return ModelResponse(parts=[ToolCallPart("generate_image", {"seed": 1})])
        if "evaluate_image" not in done:
            return ModelResponse(parts=[ToolCallPart("evaluate_image", {"n": 1})])
        if "generate_video" not in done:
            if clock:
                clock.advance(2.0)
            return ModelResponse(parts=[ToolCallPart("generate_video", {"image_n": 1, "seed": 1})])
        if "evaluate_video" not in done:
            return ModelResponse(parts=[ToolCallPart("evaluate_video", {"n": 1})])
        if "accept" not in done:
            return ModelResponse(
                parts=[ToolCallPart("accept", {"image_n": 1, "video_n": 1, "reason": "both PASS"})]
            )
        return ModelResponse(parts=[TextPart("done")])

    return model_fn


def test_happy_path_one_image_one_video(tmp_path, mp4_bytes) -> None:
    kid = validate_profile("Alex", 7, "telescope")
    kid.id = "k01"
    vlm = FakeVLM(
        [
            Evaluation(decision="PASS", score=88, reasons=["gift ok"], judge_model="fake"),
            Evaluation(
                decision="PASS", score=85, reasons=["motion ok"], cause="none", judge_model="fake"
            ),
        ]
    )
    image, video = FakeImage(), FakeVideo(mp4_bytes)
    report = run_kids(
        [kid],
        policy=Policy(budget_usd=5.0, estimate_image_seconds=1, estimate_video_seconds=2),
        settings=_settings(),
        out_root=tmp_path,
        run_id="happy",
        llm=FakeLLM(),
        image=image,
        video=video,
        vlm=vlm,
        model=FunctionModel(_happy_model()),
        live=False,
    )
    kr = report.kids[0]
    assert kr.status == "accepted"
    assert kr.image_attempts == 1 and kr.video_attempts == 1
    assert kr.h100_seconds_on_rejected_images == 0
    events = (tmp_path / "happy" / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert any(
        json.loads(line).get("check") == "gate_video_on_image_pass"
        and json.loads(line).get("result") == "allowed"
        for line in events
    )
    expected = cost_usd("gpu-l40s-a", "1gpu-8vcpu-32gb", 1.0, preemptible=True) + cost_usd(
        "gpu-h100-sxm", "1gpu-16vcpu-200gb", 2.0, preemptible=True
    )
    assert kr.cost_usd == pytest.approx(expected, rel=1e-3)


def test_image_retry_seed_then_video_from_pass(tmp_path, mp4_bytes) -> None:
    kid = validate_profile("Alex", 7, "telescope")
    kid.id = "k02"
    vlm = FakeVLM(
        [
            Evaluation(
                decision="RETRY",
                score=40,
                reasons=["garbled letters"],
                fix="seed",
                judge_model="fake",
            ),
            Evaluation(decision="PASS", score=90, reasons=["ok"], judge_model="fake"),
            Evaluation(decision="PASS", score=80, reasons=["ok"], cause="none", judge_model="fake"),
        ]
    )
    image, video = FakeImage(), FakeVideo(mp4_bytes)

    def model_fn(messages, info):
        done = _done_tools(messages)
        if "recommend_gift" not in done:
            return ModelResponse(parts=[ToolCallPart("recommend_gift", {})])
        if "write_wish" not in done:
            return ModelResponse(parts=[ToolCallPart("write_wish", {})])
        imgs, evals = done.count("generate_image"), done.count("evaluate_image")
        if imgs == 0:
            return ModelResponse(parts=[ToolCallPart("generate_image", {"seed": 1})])
        if evals == 0:
            return ModelResponse(parts=[ToolCallPart("evaluate_image", {"n": 1})])
        if imgs == 1:
            return ModelResponse(parts=[ToolCallPart("generate_image", {"seed": 99})])
        if evals == 1:
            return ModelResponse(parts=[ToolCallPart("evaluate_image", {"n": 2})])
        if "generate_video" not in done:
            return ModelResponse(parts=[ToolCallPart("generate_video", {"image_n": 2})])
        if "evaluate_video" not in done:
            return ModelResponse(parts=[ToolCallPart("evaluate_video", {"n": 1})])
        if "accept" not in done:
            return ModelResponse(
                parts=[ToolCallPart("accept", {"image_n": 2, "video_n": 1, "reason": "pass"})]
            )
        return ModelResponse(parts=[TextPart("done")])

    report = run_kids(
        [kid],
        policy=Policy(budget_usd=5.0),
        settings=_settings(),
        out_root=tmp_path,
        run_id="retry-seed",
        llm=FakeLLM(),
        image=image,
        video=video,
        vlm=vlm,
        model=FunctionModel(model_fn),
        live=False,
    )
    kr = report.kids[0]
    assert kr.image_attempts == 2 and kr.video_attempts == 1
    assert kr.h100_seconds_on_rejected_images == 0
    assert [c["seed"] for c in image.calls] == [1, 99]
    assert len(video.calls) == 1


def test_image_retry_prompt_suffix(tmp_path, mp4_bytes) -> None:
    kid = validate_profile("Alex", 7, "telescope")
    kid.id = "k03"
    suffix = "Show a clear brass telescope as the hero object."
    vlm = FakeVLM(
        [
            Evaluation(
                decision="RETRY",
                score=30,
                reasons=["gift missing"],
                fix="prompt",
                prompt_suffix=suffix,
                judge_model="fake",
            ),
            Evaluation(decision="PASS", score=92, reasons=["ok"], judge_model="fake"),
            Evaluation(decision="PASS", score=80, reasons=["ok"], cause="none", judge_model="fake"),
        ]
    )
    image, video = FakeImage(), FakeVideo(mp4_bytes)

    def model_fn(messages, info):
        done = _done_tools(messages)
        if "recommend_gift" not in done:
            return ModelResponse(parts=[ToolCallPart("recommend_gift", {})])
        if "write_wish" not in done:
            return ModelResponse(parts=[ToolCallPart("write_wish", {})])
        if done.count("generate_image") == 0:
            return ModelResponse(parts=[ToolCallPart("generate_image", {})])
        if done.count("evaluate_image") == 0:
            return ModelResponse(parts=[ToolCallPart("evaluate_image", {"n": 1})])
        if done.count("generate_image") == 1:
            ret = _last_return(messages, "evaluate_image") or {}
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "generate_image",
                        {"prompt_suffix": ret.get("prompt_suffix") or suffix, "seed": 2},
                    )
                ]
            )
        if done.count("evaluate_image") == 1:
            return ModelResponse(parts=[ToolCallPart("evaluate_image", {"n": 2})])
        if "generate_video" not in done:
            return ModelResponse(parts=[ToolCallPart("generate_video", {"image_n": 2})])
        if "evaluate_video" not in done:
            return ModelResponse(parts=[ToolCallPart("evaluate_video", {"n": 1})])
        if "accept" not in done:
            return ModelResponse(
                parts=[ToolCallPart("accept", {"image_n": 2, "video_n": 1, "reason": "fixed"})]
            )
        return ModelResponse(parts=[TextPart("done")])

    report = run_kids(
        [kid],
        policy=Policy(budget_usd=5.0),
        settings=_settings(),
        out_root=tmp_path,
        run_id="retry-prompt",
        llm=FakeLLM(),
        image=image,
        video=video,
        vlm=vlm,
        model=FunctionModel(model_fn),
        live=False,
    )
    assert report.kids[0].status == "accepted"
    baseline = image_prompt(kid, recommend_gift(kid, FakeLLM())).rstrip()
    assert image.calls[0]["prompt"].rstrip() == baseline
    assert "brass telescope" in image.calls[1]["prompt"]


def test_gate_blocks_video_before_eval(tmp_path, mp4_bytes) -> None:
    kid = validate_profile("Alex", 7, "telescope")
    kid.id = "k04"
    vlm = FakeVLM(
        [
            Evaluation(decision="PASS", score=90, reasons=["ok"], judge_model="fake"),
            Evaluation(decision="PASS", score=80, reasons=["ok"], cause="none", judge_model="fake"),
        ]
    )
    video = FakeVideo(mp4_bytes)
    turn = {"i": 0}
    plan = [
        ("recommend_gift", {}),
        ("write_wish", {}),
        ("generate_image", {}),
        ("generate_video", {"image_n": 1}),  # gate refusal → ModelRetry → next turn
        ("evaluate_image", {"n": 1}),
        ("generate_video", {"image_n": 1}),
        ("evaluate_video", {"n": 1}),
        ("accept", {"image_n": 1, "video_n": 1, "reason": "ok"}),
    ]

    def model_fn(messages, info):
        i = turn["i"]
        turn["i"] += 1
        if i >= len(plan):
            return ModelResponse(parts=[TextPart("done")])
        name, args = plan[i]
        return ModelResponse(parts=[ToolCallPart(name, args)])

    report = run_kids(
        [kid],
        policy=Policy(budget_usd=5.0),
        settings=_settings(),
        out_root=tmp_path,
        run_id="gate",
        llm=FakeLLM(),
        image=FakeImage(),
        video=video,
        vlm=vlm,
        model=FunctionModel(model_fn),
        live=False,
    )
    assert len(video.calls) == 1
    assert report.kids[0].h100_seconds_on_rejected_images == 0
    assert report.kids[0].status == "accepted"


def test_video_weak_motion_retries_same_image(tmp_path, mp4_bytes) -> None:
    kid = validate_profile("Alex", 7, "telescope")
    kid.id = "k05"
    vlm = FakeVLM(
        [
            Evaluation(decision="PASS", score=90, reasons=["ok"], judge_model="fake"),
            Evaluation(
                decision="WEAK", score=40, reasons=["warped"], cause="motion", judge_model="fake"
            ),
            Evaluation(decision="PASS", score=85, reasons=["ok"], cause="none", judge_model="fake"),
        ]
    )
    video = FakeVideo(mp4_bytes)

    def model_fn(messages, info):
        done = _done_tools(messages)
        if "recommend_gift" not in done:
            return ModelResponse(parts=[ToolCallPart("recommend_gift", {})])
        if "write_wish" not in done:
            return ModelResponse(parts=[ToolCallPart("write_wish", {})])
        if "generate_image" not in done:
            return ModelResponse(parts=[ToolCallPart("generate_image", {"seed": 1})])
        if "evaluate_image" not in done:
            return ModelResponse(parts=[ToolCallPart("evaluate_image", {"n": 1})])
        vids, vevals = done.count("generate_video"), done.count("evaluate_video")
        if vids == 0:
            return ModelResponse(parts=[ToolCallPart("generate_video", {"image_n": 1, "seed": 1})])
        if vevals == 0:
            return ModelResponse(parts=[ToolCallPart("evaluate_video", {"n": 1})])
        if vids == 1:
            return ModelResponse(parts=[ToolCallPart("generate_video", {"image_n": 1, "seed": 7})])
        if vevals == 1:
            return ModelResponse(parts=[ToolCallPart("evaluate_video", {"n": 2})])
        if "accept" not in done:
            return ModelResponse(
                parts=[
                    ToolCallPart("accept", {"image_n": 1, "video_n": 2, "reason": "motion fixed"})
                ]
            )
        return ModelResponse(parts=[TextPart("done")])

    report = run_kids(
        [kid],
        policy=Policy(budget_usd=5.0),
        settings=_settings(),
        out_root=tmp_path,
        run_id="weak-motion",
        llm=FakeLLM(),
        image=FakeImage(),
        video=video,
        vlm=vlm,
        model=FunctionModel(model_fn),
        live=False,
    )
    assert report.kids[0].status == "accepted"
    assert report.kids[0].image_attempts == 1 and report.kids[0].video_attempts == 2
    assert [c["seed"] for c in video.calls] == [1, 7]


def test_video_weak_image_regenerates(tmp_path, mp4_bytes) -> None:
    kid = validate_profile("Alex", 7, "telescope")
    kid.id = "k06"
    vlm = FakeVLM(
        [
            Evaluation(decision="PASS", score=70, reasons=["ok"], judge_model="fake"),
            Evaluation(
                decision="WEAK",
                score=30,
                reasons=["face appeared"],
                cause="image",
                judge_model="fake",
            ),
            Evaluation(decision="PASS", score=90, reasons=["ok"], judge_model="fake"),
            Evaluation(decision="PASS", score=85, reasons=["ok"], cause="none", judge_model="fake"),
        ]
    )

    def model_fn(messages, info):
        done = _done_tools(messages)
        if "recommend_gift" not in done:
            return ModelResponse(parts=[ToolCallPart("recommend_gift", {})])
        if "write_wish" not in done:
            return ModelResponse(parts=[ToolCallPart("write_wish", {})])
        imgs, ie = done.count("generate_image"), done.count("evaluate_image")
        vids, ve = done.count("generate_video"), done.count("evaluate_video")
        if imgs == 0:
            return ModelResponse(parts=[ToolCallPart("generate_image", {"seed": 1})])
        if ie == 0:
            return ModelResponse(parts=[ToolCallPart("evaluate_image", {"n": 1})])
        if vids == 0:
            return ModelResponse(parts=[ToolCallPart("generate_video", {"image_n": 1})])
        if ve == 0:
            return ModelResponse(parts=[ToolCallPart("evaluate_video", {"n": 1})])
        if imgs == 1:
            return ModelResponse(parts=[ToolCallPart("generate_image", {"seed": 2})])
        if ie == 1:
            return ModelResponse(parts=[ToolCallPart("evaluate_image", {"n": 2})])
        if vids == 1:
            return ModelResponse(parts=[ToolCallPart("generate_video", {"image_n": 2})])
        if ve == 1:
            return ModelResponse(parts=[ToolCallPart("evaluate_video", {"n": 2})])
        if "accept" not in done:
            return ModelResponse(
                parts=[ToolCallPart("accept", {"image_n": 2, "video_n": 2, "reason": "new image"})]
            )
        return ModelResponse(parts=[TextPart("done")])

    report = run_kids(
        [kid],
        policy=Policy(budget_usd=5.0),
        settings=_settings(),
        out_root=tmp_path,
        run_id="weak-image",
        llm=FakeLLM(),
        image=FakeImage(),
        video=FakeVideo(mp4_bytes),
        vlm=vlm,
        model=FunctionModel(model_fn),
        live=False,
    )
    assert report.kids[0].status == "accepted"
    assert report.kids[0].image_attempts == 2 and report.kids[0].video_attempts == 2


def test_attempts_exhausted_keep_best(tmp_path, mp4_bytes) -> None:
    kid = validate_profile("Alex", 7, "telescope")
    kid.id = "k07"
    vlm = FakeVLM(
        [
            Evaluation(decision="RETRY", score=20, reasons=["bad"], fix="seed", judge_model="fake"),
            Evaluation(
                decision="RETRY", score=40, reasons=["still bad"], fix="seed", judge_model="fake"
            ),
        ]
    )
    video = FakeVideo(mp4_bytes)

    def model_fn(messages, info):
        done = _done_tools(messages)
        if "recommend_gift" not in done:
            return ModelResponse(parts=[ToolCallPart("recommend_gift", {})])
        if "write_wish" not in done:
            return ModelResponse(parts=[ToolCallPart("write_wish", {})])
        imgs, ie = done.count("generate_image"), done.count("evaluate_image")
        if imgs < 2:
            if ie < imgs:
                return ModelResponse(parts=[ToolCallPart("evaluate_image", {"n": imgs})])
            return ModelResponse(parts=[ToolCallPart("generate_image", {"seed": imgs + 1})])
        if ie < 2:
            return ModelResponse(parts=[ToolCallPart("evaluate_image", {"n": 2})])
        if "keep_best" not in done:
            return ModelResponse(
                parts=[ToolCallPart("keep_best", {"reason": "attempts exhausted"})]
            )
        return ModelResponse(parts=[TextPart("done")])

    report = run_kids(
        [kid],
        policy=Policy(max_image_attempts=2, budget_usd=5.0),
        settings=_settings(),
        out_root=tmp_path,
        run_id="keep-best",
        llm=FakeLLM(),
        image=FakeImage(),
        video=video,
        vlm=vlm,
        model=FunctionModel(model_fn),
        live=False,
    )
    assert report.kids[0].status == "kept_best"
    assert report.kids[0].image_attempts == 2
    assert len(video.calls) == 1  # keep_best animates best RETRY image
    assert (tmp_path / "keep-best" / "k07" / "card.mp4").is_file()
    assert report.kids[0].video_attempts == 1


def test_budget_exhausted_keep_best(tmp_path, mp4_bytes) -> None:
    kid = validate_profile("Alex", 7, "telescope")
    kid.id = "k08"
    policy = Policy(budget_usd=0.001, estimate_image_seconds=1, estimate_video_seconds=120)
    vlm = FakeVLM([Evaluation(decision="PASS", score=90, reasons=["ok"], judge_model="fake")])
    video = FakeVideo(mp4_bytes)
    turn = {"i": 0}
    plan = [
        ("recommend_gift", {}),
        ("write_wish", {}),
        ("generate_image", {}),
        ("evaluate_image", {"n": 1}),
        ("generate_video", {"image_n": 1}),  # BudgetExceeded → ModelRetry
        ("keep_best", {"reason": "budget"}),
    ]

    def model_fn(messages, info):
        i = turn["i"]
        turn["i"] += 1
        if i >= len(plan):
            return ModelResponse(parts=[TextPart("done")])
        name, args = plan[i]
        return ModelResponse(parts=[ToolCallPart(name, args)])

    report = run_kids(
        [kid],
        policy=policy,
        settings=_settings(),
        out_root=tmp_path,
        run_id="budget",
        llm=FakeLLM(),
        image=FakeImage(),
        video=video,
        vlm=vlm,
        model=FunctionModel(model_fn),
        live=False,
    )
    assert report.kids[0].status == "kept_best"
    assert report.totals["cost"] <= policy.budget_usd + 1e-6
    assert len(video.calls) == 0


def test_two_kids_budget_contention(tmp_path, mp4_bytes) -> None:
    kids = [validate_profile("A", 7, "x"), validate_profile("B", 8, "y")]
    kids[0].id, kids[1].id = "ka", "kb"
    policy = Policy(
        budget_usd=0.01, estimate_image_seconds=1, estimate_video_seconds=5, max_parallel_kids=2
    )
    vlm = FakeVLM(
        [
            Evaluation(decision="PASS", score=90, reasons=["ok"], judge_model="fake"),
            Evaluation(decision="PASS", score=80, reasons=["ok"], cause="none", judge_model="fake"),
            Evaluation(decision="PASS", score=90, reasons=["ok"], judge_model="fake"),
            Evaluation(decision="PASS", score=80, reasons=["ok"], cause="none", judge_model="fake"),
            Evaluation(decision="PASS", score=90, reasons=["ok"], judge_model="fake"),
            Evaluation(decision="PASS", score=80, reasons=["ok"], cause="none", judge_model="fake"),
        ]
    )

    def model_fn(messages, info):
        done = _done_tools(messages)
        if "recommend_gift" not in done:
            return ModelResponse(parts=[ToolCallPart("recommend_gift", {})])
        if "write_wish" not in done:
            return ModelResponse(parts=[ToolCallPart("write_wish", {})])
        if "generate_image" not in done:
            return ModelResponse(parts=[ToolCallPart("generate_image", {})])
        if "evaluate_image" not in done:
            return ModelResponse(parts=[ToolCallPart("evaluate_image", {"n": 1})])
        if "generate_video" not in done:
            return ModelResponse(parts=[ToolCallPart("generate_video", {"image_n": 1})])
        if "evaluate_video" not in done:
            return ModelResponse(parts=[ToolCallPart("evaluate_video", {"n": 1})])
        if "accept" not in done and "keep_best" not in done:
            return ModelResponse(
                parts=[ToolCallPart("accept", {"image_n": 1, "video_n": 1, "reason": "ok"})]
            )
        if "keep_best" not in done:
            return ModelResponse(parts=[ToolCallPart("keep_best", {"reason": "budget"})])
        return ModelResponse(parts=[TextPart("done")])

    report = run_kids(
        kids,
        policy=policy,
        settings=_settings(),
        out_root=tmp_path,
        run_id="contend",
        llm=FakeLLM(),
        image=FakeImage(),
        video=FakeVideo(mp4_bytes),
        vlm=vlm,
        model=FunctionModel(model_fn),
        live=False,
    )
    assert report.totals["cost"] <= policy.budget_usd + 1e-6


def test_motion_metric_override_static(tmp_path, mp4_bytes) -> None:
    a = tmp_path / "a.png"
    Image.new("RGB", (64, 64), color=(10, 10, 10)).save(a)
    assert motion_metric(a, a) < 0.01
    # Truly static mp4 (single color loop)
    static = tmp_path / "static.mp4"
    cmd = [
        ffmpeg_exe(),
        "-y",
        "-loop",
        "1",
        "-i",
        str(a),
        "-c:v",
        "libx264",
        "-t",
        "0.3",
        "-pix_fmt",
        "yuv420p",
        str(static),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    vlm = FakeVLM(
        [
            Evaluation(
                decision="PASS", score=99, reasons=["looks fine"], cause="none", judge_model="fake"
            )
        ]
    )
    ev = evaluate_video(a.read_bytes(), static, vlm, frames_dir=tmp_path / "fr")
    assert ev.decision == "WEAK"
    assert ev.cause == "motion"


def test_events_jsonl_required_names(tmp_path, mp4_bytes) -> None:
    kid = validate_profile("Alex", 7, "telescope")
    kid.id = "k12"
    vlm = FakeVLM(
        [
            Evaluation(decision="PASS", score=90, reasons=["ok"], judge_model="fake"),
            Evaluation(decision="PASS", score=80, reasons=["ok"], cause="none", judge_model="fake"),
        ]
    )
    run_kids(
        [kid],
        policy=Policy(budget_usd=5.0),
        settings=_settings(),
        out_root=tmp_path,
        run_id="events",
        llm=FakeLLM(),
        image=FakeImage(),
        video=FakeVideo(mp4_bytes),
        vlm=vlm,
        model=FunctionModel(_happy_model()),
        live=False,
    )
    path = tmp_path / "events" / "events.jsonl"
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    names = {json.loads(line)["event"] for line in lines}
    for required in (
        "run_started",
        "tool_call",
        "endpoint_call_completed",
        "artifact_evaluated",
        "budget_updated",
        "run_completed",
    ):
        assert required in names


def test_bench_scorecard_wasted_h100(tmp_path, mp4_bytes) -> None:
    from santa.agent.bench import run_bench

    kid = validate_profile("Alex", 7, "telescope")
    kid.id = "kb"

    class PipelineVLM(FakeVLM):
        def generate_json_vision(self, prompt: str, images: list[bytes], **kw):
            self.calls += 1
            if "three video frames" in prompt.lower() or "Compare the three" in prompt:
                return {"decision": "PASS", "score": 80, "reasons": ["ok"], "cause": "none"}
            return {
                "decision": "RETRY",
                "score": 20,
                "reasons": ["garbled"],
                "fix": "seed",
                "prompt_suffix": "",
            }

    def agent_model(messages, info):
        done = _done_tools(messages)
        if "recommend_gift" not in done:
            return ModelResponse(parts=[ToolCallPart("recommend_gift", {})])
        if "write_wish" not in done:
            return ModelResponse(parts=[ToolCallPart("write_wish", {})])
        if "generate_image" not in done:
            return ModelResponse(parts=[ToolCallPart("generate_image", {})])
        if "evaluate_image" not in done:
            return ModelResponse(parts=[ToolCallPart("evaluate_image", {"n": 1})])
        if "keep_best" not in done:
            return ModelResponse(parts=[ToolCallPart("keep_best", {"reason": "image retry"})])
        return ModelResponse(parts=[TextPart("done")])

    path = run_bench(
        [kid],
        modes=["pipeline", "agent"],
        policy=Policy(budget_usd=5.0, max_image_attempts=1, max_video_attempts=1),
        settings=_settings(),
        out_root=tmp_path / "bench2",
        llm=FakeLLM(),
        image=FakeImage(),
        video=FakeVideo(mp4_bytes),
        vlm=PipelineVLM(),
        model=FunctionModel(agent_model),
    )
    text = path.read_text(encoding="utf-8")
    assert "H100 seconds on rejected images" in text
    pipe = json.loads((path.parent / "pipeline" / "report.json").read_text())
    agent = json.loads((path.parent / "agent" / "report.json").read_text())
    assert pipe["totals"]["wasted_h100_s"] > 0
    assert agent["totals"]["wasted_h100_s"] == 0
