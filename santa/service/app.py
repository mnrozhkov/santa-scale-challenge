"""Presenter web app — thin driver over ServiceSession."""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from santa.batch import DEFAULT_KIDS_CSV, BatchError, load_kids
from santa.card import ProfileError, validate_profile
from santa.config import REPO_ROOT, ConfigError
from santa.nebius_jobs import NebiusJobError
from santa.schemas import KidProfile
from santa.service.demo_gallery import GALLERY_DIR
from santa.service.redact import looks_like_secret, redact_public
from santa.service.session import ServiceSession
from santa.storage import StorageError, use_system_certs

use_system_certs()
load_dotenv(REPO_ROOT / ".env", override=False)

log = logging.getLogger("santa.service")

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
STATIC_DIR = Path(__file__).resolve().parent / "static"
UI_INDEX = STATIC_DIR / "index.html"
OPERATOR_HEADER = "x-santa-operator"
_CARD_SLOTS = threading.Semaphore(2)

_MEDIA_OK = (".png", ".mp4", ".html")


class BatchRequest(BaseModel):
    kids: list[KidProfile]


class AnimateRequest(BaseModel):
    mood_bank: bool = True


class RunRequest(BaseModel):
    jobs: int = Field(default=4, ge=1, le=32)


class AgentRequest(BaseModel):
    kids: list[KidProfile] | None = None
    limit: int = Field(default=4, ge=1, le=32)
    budget_usd: float | None = None
    publish: bool = True


def _page(
    request: Request, session: ServiceSession | None, error: str | None = None
) -> HTMLResponse:
    run = session.last_run if session else None
    card = run.card if run else None
    return TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {
            "error": error,
            "run": run,
            "card": card,
            "kid": session.last_kid if session else None,
            "steps": run.steps if run else [],
            "has_png": bool(card and card.png_path and Path(card.png_path).exists()),
        },
    )


def _operator_token() -> str:
    return (os.environ.get("SANTA_OPERATOR_TOKEN") or "").strip()


def _is_operator(request: Request) -> bool:
    expected = _operator_token()
    if not expected:
        return True
    got = (request.headers.get(OPERATOR_HEADER) or "").strip()
    if len(got) != len(expected):
        return False
    return secrets.compare_digest(got, expected)


def _require_operator(request: Request) -> None:
    if not _is_operator(request):
        raise HTTPException(status_code=403, detail="Operator required")


def _public_detail(exc: Exception, *, fallback: str) -> str:
    if isinstance(exc, ProfileError):
        msg = str(exc)
        if looks_like_secret(msg):
            return fallback
        return msg
    if isinstance(exc, BatchError):
        msg = str(exc)
        if looks_like_secret(msg):
            return fallback
        return msg
    return fallback


def _http_error(exc: Exception, *, status: int, fallback: str) -> HTTPException:
    log.exception("service error")
    return HTTPException(status_code=status, detail=_public_detail(exc, fallback=fallback))


def _spa() -> FileResponse:
    return FileResponse(
        UI_INDEX,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


def _origin(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _absolute(request: Request, path: str | None) -> str | None:
    if not path:
        return None
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"{_origin(request)}{path if path.startswith('/') else '/' + path}"


def create_app(session: ServiceSession | None = None) -> FastAPI:
    application = FastAPI(
        title="Santa Service",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    state: dict[str, ServiceSession | None] = {"session": session}

    def current() -> ServiceSession:
        bound = state["session"]
        if bound is None:
            bound = ServiceSession.from_env()
            state["session"] = bound
        return bound

    def _card_response(run: Any, kid: KidProfile) -> dict[str, Any]:
        kid_id = run.card.kid_id
        payload = {
            "card": json.loads(run.card.model_dump_json()),
            "kid": json.loads(kid.model_dump_json()),
            "steps": run.steps,
            "png_url": f"/cards/{kid_id}.png" if run.card.png_path else None,
            "html_url": f"/cards/{kid_id}.html" if run.card.html_path else None,
        }
        return redact_public(payload)

    @application.get("/", response_class=HTMLResponse)
    def index(request: Request) -> Any:
        if UI_INDEX.is_file():
            return _spa()
        try:
            return _page(request, current())
        except (ConfigError, StorageError, RuntimeError) as exc:
            log.exception("index failed")
            return _page(request, None, error=_public_detail(exc, fallback="Service unavailable"))

    @application.get("/qr", response_class=HTMLResponse)
    def qr() -> Any:
        if UI_INDEX.is_file():
            return _spa()
        raise HTTPException(status_code=404, detail="UI not built")

    @application.get("/form", response_class=HTMLResponse)
    def form(request: Request) -> HTMLResponse:
        try:
            return _page(request, current())
        except (ConfigError, StorageError, RuntimeError) as exc:
            log.exception("form failed")
            return _page(request, None, error=_public_detail(exc, fallback="Service unavailable"))

    @application.post("/generate", response_class=HTMLResponse)
    def generate(
        request: Request,
        name: str = Form(""),
        age: str = Form(""),
        wish: str = Form(""),
    ) -> HTMLResponse:
        try:
            profile = validate_profile(name, age, wish)
            bound = current()
            bound.generate_card(profile)
            return _page(request, bound)
        except (ProfileError, ConfigError, StorageError, RuntimeError) as exc:
            log.exception("generate failed")
            return _page(
                request,
                state["session"],
                error=_public_detail(exc, fallback="Card generation failed"),
            )

    @application.get("/card.png")
    def card_png() -> FileResponse:
        run = current().last_run
        if not run or not run.card.png_path:
            raise HTTPException(status_code=404, detail="No card PNG yet")
        path = Path(run.card.png_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="PNG file missing")
        return FileResponse(path, media_type="image/png")

    @application.get("/card.html", response_class=HTMLResponse)
    def card_html() -> HTMLResponse:
        run = current().last_run
        if not run or not run.card.html_path:
            raise HTTPException(status_code=404, detail="No card yet")
        path = Path(run.card.html_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="HTML file missing")
        return HTMLResponse(path.read_text(encoding="utf-8"))

    @application.get("/cards/{kid_id}.png")
    def card_id_png(kid_id: str) -> FileResponse:
        path = current().out_root / kid_id / "card.png"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="PNG file missing")
        return FileResponse(path, media_type="image/png")

    @application.get("/cards/{kid_id}.html", response_class=HTMLResponse)
    def card_id_html(kid_id: str) -> HTMLResponse:
        path = current().out_root / kid_id / "card.html"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="HTML file missing")
        return HTMLResponse(path.read_text(encoding="utf-8"))

    @application.get("/media/{key:path}")
    def media(key: str) -> Any:
        from fastapi.responses import Response

        if ".." in Path(key).parts:
            raise HTTPException(status_code=400, detail="Invalid key")
        lowered = key.lower()
        if not lowered.endswith(_MEDIA_OK):
            raise HTTPException(status_code=404, detail="Not found")
        try:
            data = current().read_object(key)
        except StorageError:
            raise HTTPException(status_code=404, detail="Not found") from None
        if lowered.endswith(".png"):
            media_type = "image/png"
        elif lowered.endswith(".mp4"):
            media_type = "video/mp4"
        else:
            media_type = "text/html"
        return Response(content=data, media_type=media_type)

    @application.get("/s/{kid_id}", response_class=HTMLResponse)
    def share(kid_id: str, request: Request) -> HTMLResponse:
        if "/" in kid_id or ".." in kid_id:
            raise HTTPException(status_code=404, detail="Not found")
        try:
            listing = current().wall()
        except (ConfigError, StorageError, RuntimeError):
            log.exception("share wall failed")
            raise HTTPException(status_code=404, detail="Not found") from None
        item = next(
            (row for row in listing.get("items") or [] if str(row.get("id")) == kid_id),
            None,
        )
        if not isinstance(item, dict) or not item.get("png_url"):
            raise HTTPException(status_code=404, detail="Not found")
        name = str(item.get("name") or "friend")
        wish = str(item.get("wish") or "Merry Christmas!")
        png_url = str(item["png_url"])
        og_image = _absolute(request, png_url) or png_url
        share_url = _absolute(request, f"/s/{kid_id}") or f"/s/{kid_id}"
        title = f"A Christmas card for {name}"
        return TEMPLATES.TemplateResponse(
            request,
            "share.html",
            {
                "title": title,
                "description": wish,
                "name": name,
                "wish": wish,
                "png_url": png_url,
                "og_image": og_image,
                "share_url": share_url,
            },
        )

    @application.get("/api/access")
    def api_access(request: Request) -> dict[str, str]:
        return {"role": "operator" if _is_operator(request) else "guest"}

    @application.post("/api/cards")
    def api_cards(kid: KidProfile) -> dict[str, Any]:
        with _CARD_SLOTS:
            try:
                run = current().generate_card(kid)
            except (ProfileError, ConfigError, StorageError, RuntimeError) as exc:
                raise _http_error(exc, status=400, fallback="Card generation failed") from exc
        return _card_response(run, kid)

    @application.post("/api/cards/stream")
    def api_cards_stream(kid: KidProfile) -> StreamingResponse:
        from concurrent.futures import ThreadPoolExecutor
        from queue import Queue

        q: Queue[dict[str, Any] | None] = Queue()

        def worker() -> None:
            with _CARD_SLOTS:
                try:
                    run = current().generate_card(kid, on_progress=q.put)
                    q.put({"type": "complete", **_card_response(run, kid)})
                except (ProfileError, ConfigError, StorageError, RuntimeError) as exc:
                    log.exception("card stream failed")
                    q.put(
                        {
                            "type": "error",
                            "detail": _public_detail(exc, fallback="Card generation failed"),
                        }
                    )
                except Exception:
                    log.exception("card stream failed")
                    q.put({"type": "error", "detail": "Card generation failed"})
                finally:
                    q.put(None)

        def generate() -> Any:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(worker)
                while True:
                    item = q.get()
                    if item is None:
                        break
                    payload = redact_public(item) if isinstance(item, dict) else item
                    # SSE comment padding — some proxies buffer small chunks until ~2 KB.
                    yield f"data: {json.dumps(payload)}\n\n: pad {' ' * 2048}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @application.post("/api/cards/batch")
    def api_batch(body: BatchRequest) -> dict[str, Any]:
        result = current().generate_batch(body.kids)
        return redact_public({"ids": result.ids, "failures": result.failures})

    @application.post("/api/cards/{kid_id}/animate")
    def api_animate(
        kid_id: str, request: Request, body: AnimateRequest | None = None
    ) -> dict[str, Any]:
        _require_operator(request)
        mood_bank = True if body is None else body.mood_bank
        try:
            return redact_public(current().animate_card(kid_id, mood_bank=mood_bank))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Card not found") from exc
        except StorageError as exc:
            raise HTTPException(status_code=404, detail="Card not found") from exc
        except (ConfigError, RuntimeError) as exc:
            raise _http_error(exc, status=503, fallback="Animate failed") from exc

    @application.post("/api/publish")
    async def api_publish(file: UploadFile = File(...)) -> dict[str, Any]:
        data = await file.read()
        key = current().publish(file.filename or "upload", data, file.content_type or "")
        return {"key": key}

    @application.get("/api/wall")
    def api_wall() -> dict[str, Any]:
        try:
            return redact_public(current().wall())
        except (ConfigError, StorageError, RuntimeError) as exc:
            raise _http_error(exc, status=503, fallback="Gallery unavailable") from exc

    @application.get("/api/kids")
    def api_kids(limit: int = 20) -> dict[str, Any]:
        path = DEFAULT_KIDS_CSV
        if not path.is_file():
            raise HTTPException(status_code=404, detail="kids CSV missing")
        try:
            n = limit if limit > 0 else None
            kids = load_kids(path, n=n)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"kids": [json.loads(k.model_dump_json()) for k in kids]}

    @application.post("/api/runs")
    def api_runs(request: Request, body: RunRequest | None = None) -> dict[str, Any]:
        _require_operator(request)
        jobs = 4 if body is None else body.jobs
        try:
            return redact_public(current().submit_run(jobs=jobs))
        except BatchError as exc:
            raise _http_error(exc, status=400, fallback="Run failed") from exc
        except (NebiusJobError, ConfigError, StorageError, RuntimeError) as exc:
            raise _http_error(exc, status=503, fallback="Run failed") from exc

    @application.get("/api/runs/{run_id}")
    def api_run(run_id: str, request: Request) -> dict[str, Any]:
        _require_operator(request)
        try:
            return redact_public(current().run_status(run_id))
        except StorageError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc
        except (NebiusJobError, ConfigError, RuntimeError) as exc:
            raise _http_error(exc, status=503, fallback="Run failed") from exc

    @application.post("/api/agent/stream")
    def api_agent_stream(request: Request, body: AgentRequest | None = None) -> StreamingResponse:
        """Experiment B — evaluate-before-escalate. Operator-only (GPU spend)."""
        _require_operator(request)
        from concurrent.futures import ThreadPoolExecutor
        from queue import Queue

        req = body or AgentRequest()
        if req.kids:
            kids = req.kids
        else:
            path = DEFAULT_KIDS_CSV
            if not path.is_file():
                raise HTTPException(status_code=404, detail="kids CSV missing")
            try:
                kids = load_kids(path, n=req.limit)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        q: Queue[dict[str, Any] | None] = Queue()

        def worker() -> None:
            try:
                report = current().run_agent_kids(
                    kids,
                    budget_usd=req.budget_usd,
                    publish=req.publish,
                    on_event=q.put,
                )
                from santa.storage import card_png_key, card_video_key

                payload = json.loads(report.model_dump_json())
                for kid in payload.get("kids") or []:
                    kid_id = kid.get("kid_id")
                    if not kid_id:
                        continue
                    kid["png_url"] = f"/media/{card_png_key(kid_id)}"
                    kid["video_url"] = f"/media/{card_video_key(kid_id)}"
                q.put({"type": "complete", "report": payload})
            except (ProfileError, ConfigError, StorageError, RuntimeError) as exc:
                log.exception("agent stream failed")
                q.put(
                    {
                        "type": "error",
                        "detail": _public_detail(exc, fallback="Agent run failed"),
                    }
                )
            except Exception:
                log.exception("agent stream failed")
                q.put({"type": "error", "detail": "Agent run failed"})
            finally:
                q.put(None)

        def generate() -> Any:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(worker)
                while True:
                    item = q.get()
                    if item is None:
                        break
                    payload = redact_public(item) if isinstance(item, dict) else item
                    yield f"data: {json.dumps(payload)}\n\n: pad {' ' * 2048}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @application.get("/wall", response_class=HTMLResponse)
    def wall(request: Request) -> HTMLResponse:
        try:
            listing = current().wall()
            return TEMPLATES.TemplateResponse(request, "wall.html", {"error": None, **listing})
        except (ConfigError, StorageError, RuntimeError):
            log.exception("wall failed")
            return TEMPLATES.TemplateResponse(
                request,
                "wall.html",
                {
                    "error": "Gallery unavailable",
                    "cards": [],
                    "videos": [],
                    "items": [],
                    "summary": None,
                    "counter": None,
                },
            )

    assets = STATIC_DIR / "assets"
    if assets.is_dir():
        application.mount("/assets", StaticFiles(directory=assets), name="ui-assets")
    if GALLERY_DIR.is_dir():
        application.mount("/demo", StaticFiles(directory=GALLERY_DIR), name="demo-gallery")

    return application


app = create_app()


def main() -> None:
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("santa.service.app:app", host=host, port=port)


if __name__ == "__main__":
    main()
