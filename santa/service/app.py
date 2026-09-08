"""Presenter web app — thin driver over ServiceSession."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from santa.card import ProfileError, validate_profile
from santa.config import ConfigError
from santa.schemas import KidProfile
from santa.service.session import ServiceSession
from santa.storage import StorageError

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


class BatchRequest(BaseModel):
    kids: list[KidProfile]


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


def create_app(session: ServiceSession | None = None) -> FastAPI:
    application = FastAPI(title="Santa Service")
    state: dict[str, ServiceSession | None] = {"session": session}

    def current() -> ServiceSession:
        bound = state["session"]
        if bound is None:
            bound = ServiceSession.from_env()
            state["session"] = bound
        return bound

    @application.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
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
            data = current().storage.download(key)
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
        run = current().generate_card(kid)
        kid_id = run.card.kid_id
        return {
            "card": json.loads(run.card.model_dump_json()),
            "steps": run.steps,
            "png_url": f"/cards/{kid_id}.png" if run.card.png_path else None,
            "html_url": f"/cards/{kid_id}.html" if run.card.html_path else None,
        }

    @application.post("/api/cards/batch")
    def api_batch(body: BatchRequest) -> dict[str, Any]:
        result = current().generate_batch(body.kids)
        return {"ids": result.ids, "failures": result.failures}

    @application.post("/api/publish")
    async def api_publish(file: UploadFile = File(...)) -> dict[str, Any]:
        data = await file.read()
        key = current().publish(file.filename or "upload", data, file.content_type or "")
        return {"key": key}

    @application.get("/api/wall")
    def api_wall() -> dict[str, Any]:
        return current().wall()

    @application.get("/wall", response_class=HTMLResponse)
    def wall(request: Request) -> HTMLResponse:
        try:
            listing = current().wall()
            return TEMPLATES.TemplateResponse(request, "wall.html", {"error": None, **listing})
        except (ConfigError, StorageError, RuntimeError) as exc:
            return TEMPLATES.TemplateResponse(
                request,
                "wall.html",
                {"error": str(exc), "cards": [], "videos": [], "summary": None, "counter": None},
            )

    return application


app = create_app()


def main() -> None:
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("santa.service.app:app", host=host, port=port)


if __name__ == "__main__":
    main()
