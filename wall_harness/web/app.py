from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from starlette.middleware.base import RequestResponseEndpoint

from wall_harness.models import Item, WallEdition, WallSpec
from wall_harness.pipeline import WallPipeline
from wall_harness.spec import parse_spec
from wall_harness.state import KnowledgeState

from .workspace import WallRecord, WallWorkspace

logger = logging.getLogger(__name__)


class RunRequest(BaseModel):
    use_llm: bool = True
    wall: str | None = None


class SpecUpdate(BaseModel):
    yaml: str = Field(max_length=1_000_000)


class FeedbackRequest(BaseModel):
    item: Item
    action: Literal["save", "hide", "known", "more_like_this"]
    wall: str | None = None


PipelineFactory = Callable[[WallSpec], WallPipeline]


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent, text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def create_app(
    spec_path: Path,
    *,
    state_path: Path | None = None,
    pipeline_factory: PipelineFactory | None = None,
) -> FastAPI:
    workspace = WallWorkspace(spec_path)
    workspace.records()
    state_path = (state_path or workspace.root / ".wall" / "state.db").resolve()
    static_path = Path(__file__).parent / "static"
    template_path = Path(__file__).parent / "templates" / "index.html"

    app = FastAPI(title="Wall", docs_url="/api/docs", redoc_url=None)
    app.mount("/static", StaticFiles(directory=static_path), name="static")

    @app.middleware("http")
    async def security_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def make_pipeline(spec: WallSpec) -> WallPipeline:
        if pipeline_factory:
            return pipeline_factory(spec)
        return WallPipeline(spec, state_path=state_path)

    def select(wall: str | None = None) -> WallRecord:
        try:
            return workspace.resolve(wall)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown wall: {wall}") from exc

    def latest_path(wall_name: str) -> Path:
        identifier = sha256(wall_name.encode()).hexdigest()[:12]
        return state_path.parent / f"latest-{identifier}.json"

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> HTMLResponse:
        return HTMLResponse(template_path.read_text(encoding="utf-8"))

    @app.get("/favicon.ico", status_code=204)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/api/walls")
    def get_walls() -> list[dict[str, str]]:
        return [
            {"name": record.spec.name, "goal": record.spec.goal} for record in workspace.records()
        ]

    @app.get("/api/spec", response_model=WallSpec)
    def get_spec(wall: str | None = None) -> WallSpec:
        return select(wall).spec

    @app.get("/api/spec/source")
    def get_spec_source(wall: str | None = None) -> dict[str, str]:
        return {"content": select(wall).path.read_text(encoding="utf-8")}

    @app.put("/api/spec", response_model=WallSpec)
    def update_spec(update: SpecUpdate, wall: str | None = None) -> WallSpec:
        record = select(wall)
        try:
            spec = parse_spec(update.yaml)
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if any(
            other.path != record.path and other.spec.name == spec.name
            for other in workspace.records()
        ):
            raise HTTPException(
                status_code=422,
                detail="Every WallSpec in a workspace must have a unique name",
            )
        spec_path = record.path
        atomic_write_text(spec_path, update.yaml)
        return spec

    @app.post("/api/run", response_model=WallEdition)
    def run_wall(request: RunRequest) -> WallEdition:
        spec = select(request.wall).spec
        try:
            pipeline = make_pipeline(spec)
            edition = pipeline.run(use_llm=request.use_llm)
            pipeline.write(edition)
            pipeline.deliver(edition)
        except Exception as exc:
            logger.error("Wall build failed (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=502,
                detail="Wall build failed. Check the server logs for details.",
            ) from exc
        edition_path = latest_path(spec.name)
        atomic_write_text(
            edition_path,
            json.dumps(edition.model_dump(mode="json"), indent=2),
        )
        return edition

    @app.get("/api/edition", response_model=WallEdition | None)
    def get_edition(wall: str | None = None) -> WallEdition | None:
        edition_path = latest_path(select(wall).spec.name)
        if not edition_path.exists():
            return None
        try:
            return WallEdition.model_validate_json(edition_path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as exc:
            raise HTTPException(status_code=500, detail="Latest edition is unreadable") from exc

    @app.post("/api/feedback", status_code=204)
    def record_feedback(request: FeedbackRequest) -> Response:
        spec = select(request.wall).spec
        with KnowledgeState(state_path) as state:
            state.record_feedback(spec.name, request.item, request.action)
        return Response(status_code=204)

    @app.get("/api/feedback")
    def get_feedback(wall: str | None = None) -> dict[str, str]:
        spec = select(wall).spec
        edition = get_edition(wall)
        item_ids = [result.item.id for result in edition.items] if edition else []
        with KnowledgeState(state_path) as state:
            return state.feedback_actions(spec.name, item_ids)

    return app
