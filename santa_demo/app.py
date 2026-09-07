"""Presenter web app — thin driver over DemoSession."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from santa_demo.config import ImageEndpointConfigError, TokenFactoryConfigError
from santa_demo.jobs import JobRunnerConfigError
from santa_demo.session import DemoSession, ProfileValidationError, validate_profile
from santa_demo.video import VideoEndpointConfigError, VideoEndpointError

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

app = FastAPI(title="Santa Serverless Demo")
_session: DemoSession | None = None


def get_session() -> DemoSession:
    global _session
    if _session is None:
        _session = DemoSession.from_env()
    return _session


@app.get("/", response_class=HTMLResponse)
def index(request: Request, error: str | None = None) -> HTMLResponse:
    session = None
    config_error = None
    try:
        session = get_session()
    except (ImageEndpointConfigError, TokenFactoryConfigError) as exc:
        config_error = str(exc)
    return TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {
            "error": error or config_error,
            "card": session.last_card if session else None,
            "video_path": session.last_video_path if session else None,
            "jobs": session.last_jobs if session else [],
            "has_live_png": bool(session and session.last_card and session.last_card.png_path),
        },
    )


@app.post("/generate", response_class=HTMLResponse)
def generate(
    request: Request,
    name: str = Form(""),
    age: str = Form(""),
    wish: str = Form(""),
) -> HTMLResponse:
    try:
        profile = validate_profile(name, age, wish)
        session = get_session()
        session.generate_card(profile)
        error = None
        card = session.last_card
    except (
        ProfileValidationError,
        ImageEndpointConfigError,
        TokenFactoryConfigError,
        RuntimeError,
    ) as exc:
        error = str(exc)
        card = _session.last_card if _session else None
    return TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {
            "error": error,
            "card": card,
            "video_path": _session.last_video_path if _session else None,
            "jobs": _session.last_jobs if _session else [],
            "has_live_png": bool(card and card.png_path),
        },
    )


@app.get("/card.png")
def card_png() -> FileResponse:
    session = get_session()
    if not session.last_card or not session.last_card.png_path:
        return HTMLResponse("No card PNG yet", status_code=404)
    path = Path(session.last_card.png_path)
    if not path.exists():
        return HTMLResponse("PNG file missing", status_code=404)
    return FileResponse(path, media_type="image/png")


@app.get("/card.html", response_class=HTMLResponse)
def card_html() -> HTMLResponse:
    session = get_session()
    if not session.last_card:
        return HTMLResponse("No card yet", status_code=404)
    return HTMLResponse(session.last_card.html)


def _page(request: Request, error: str | None = None) -> HTMLResponse:
    session = _session
    return TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {
            "error": error,
            "card": session.last_card if session else None,
            "video_path": session.last_video_path if session else None,
            "jobs": session.last_jobs if session else [],
            "has_live_png": bool(session and session.last_card and session.last_card.png_path),
        },
    )


@app.post("/animate", response_class=HTMLResponse)
def animate(request: Request) -> HTMLResponse:
    try:
        get_session().animate()
        return _page(request)
    except (VideoEndpointConfigError, VideoEndpointError, FileNotFoundError) as exc:
        return _page(request, error=str(exc))


@app.post("/batch", response_class=HTMLResponse)
def batch(request: Request, include_last: str = Form("")) -> HTMLResponse:
    try:
        get_session().batch_videos(include_last=include_last == "on")
        return _page(request)
    except (JobRunnerConfigError, FileNotFoundError, RuntimeError) as exc:
        return _page(request, error=str(exc))


@app.post("/batch/refresh", response_class=HTMLResponse)
def batch_refresh(request: Request) -> HTMLResponse:
    try:
        get_session().refresh_jobs()
        return _page(request)
    except JobRunnerConfigError as exc:
        return _page(request, error=str(exc))


@app.get("/card.mp4")
def card_mp4() -> FileResponse:
    session = get_session()
    if not session.last_video_path or not Path(session.last_video_path).exists():
        return HTMLResponse("No MP4 yet", status_code=404)
    return FileResponse(session.last_video_path, media_type="video/mp4")


def main() -> None:
    import uvicorn

    uvicorn.run("santa_demo.app:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
