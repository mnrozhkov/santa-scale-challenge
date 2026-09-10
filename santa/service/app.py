"""Presenter web app — thin driver over ServiceSession."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from santa.batch import DEFAULT_KIDS_CSV, BatchError, load_kids
from santa.card import ProfileError, validate_profile
from santa.config import ConfigError
from santa.nebius_jobs import NebiusJobError
from santa.schemas import KidProfile
from santa.service.session import ServiceSession
from santa.storage import StorageError

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
STATIC_DIR = Path(__file__).resolve().parent / "static"
UI_INDEX = STATIC_DIR / "index.html"


class BatchRequest(BaseModel):
    kids: list[KidProfile]


class AnimateRequest(BaseModel):
    mood_bank: bool = True


class RunRequest(BaseModel):
    jobs: int = Field(default=4, ge=1, le=32)


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


def _http_error(exc: Exception, *, status: int) -> HTTPException:
    return HTTPException(status_code=status, detail=str(exc))


def create_app(session: ServiceSession | None = None) -> FastAPI:
    application = FastAPI(title="Santa Service")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
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

    @application.get("/", response_class=HTMLResponse)
    def index(request: Request) -> Any:
        if UI_INDEX.is_file():
            return FileResponse(UI_INDEX)
        try:
            return _page(request, current())
        except (ConfigError, StorageError, RuntimeError) as exc:
            return _page(request, None, error=str(exc))

    @application.get("/form", response_class=HTMLResponse)
    def form(request: Request) -> HTMLResponse:
        try:
            return _page(request, current())
        except (ConfigError, StorageError, RuntimeError) as exc:
            return _page(request, None, error=str(exc))

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
            return _page(request, state["session"], error=str(exc))

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
        try:
            data = current().read_object(key)
        except StorageError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if key.endswith(".png"):
            media_type = "image/png"
        elif key.endswith(".mp4"):
            media_type = "video/mp4"
        else:
            media_type = "application/octet-stream"
        return Response(content=data, media_type=media_type)

    @application.post("/api/cards")
    def api_cards(kid: KidProfile) -> dict[str, Any]:
        try:
            run = current().generate_card(kid)
        except (ProfileError, ConfigError, StorageError, RuntimeError) as exc:
            raise _http_error(exc, status=400) from exc
        kid_id = run.card.kid_id
        return {
            "card": json.loads(run.card.model_dump_json()),
            "kid": json.loads(kid.model_dump_json()),
            "steps": run.steps,
            "png_url": f"/cards/{kid_id}.png" if run.card.png_path else None,
            "html_url": f"/cards/{kid_id}.html" if run.card.html_path else None,
        }

    @application.post("/api/cards/batch")
    def api_batch(body: BatchRequest) -> dict[str, Any]:
        result = current().generate_batch(body.kids)
        return {"ids": result.ids, "failures": result.failures}

    @application.post("/api/cards/{kid_id}/animate")
    def api_animate(kid_id: str, body: AnimateRequest | None = None) -> dict[str, Any]:
        mood_bank = True if body is None else body.mood_bank
        try:
            return current().animate_card(kid_id, mood_bank=mood_bank)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ConfigError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @application.post("/api/publish")
    async def api_publish(file: UploadFile = File(...)) -> dict[str, Any]:
        data = await file.read()
        key = current().publish(file.filename or "upload", data, file.content_type or "")
        return {"key": key}

    @application.get("/api/wall")
    def api_wall() -> dict[str, Any]:
        try:
            return current().wall()
        except (ConfigError, StorageError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @application.get("/api/kids")
    def api_kids(limit: int = 20) -> dict[str, Any]:
        path = DEFAULT_KIDS_CSV
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"kids CSV missing: {path}")
        try:
            n = limit if limit > 0 else None
            kids = load_kids(path, n=n)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"kids": [json.loads(k.model_dump_json()) for k in kids]}

    @application.post("/api/runs")
    def api_runs(body: RunRequest | None = None) -> dict[str, Any]:
        jobs = 4 if body is None else body.jobs
        try:
            return current().submit_run(jobs=jobs)
        except BatchError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (NebiusJobError, ConfigError, StorageError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @application.get("/api/runs/{run_id}")
    def api_run(run_id: str) -> dict[str, Any]:
        try:
            return current().run_status(run_id)
        except StorageError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (NebiusJobError, ConfigError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @application.get("/wall", response_class=HTMLResponse)
    def wall(request: Request) -> HTMLResponse:
        try:
            listing = current().wall()
            return TEMPLATES.TemplateResponse(request, "wall.html", {"error": None, **listing})
        except (ConfigError, StorageError, RuntimeError) as exc:
            return TEMPLATES.TemplateResponse(
                request,
                "wall.html",
                {
                    "error": str(exc),
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

    return application


app = create_app()


def main() -> None:
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("santa.service.app:app", host=host, port=port)


if __name__ == "__main__":
    main()
