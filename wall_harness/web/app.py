from __future__ import annotations

import json
import logging
import os
import secrets
import tempfile
import zipfile
from base64 import b64decode
from collections.abc import Callable
from hashlib import sha256
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from starlette.middleware.base import RequestResponseEndpoint

from wall_harness.models import Item, WallEdition, WallSpec
from wall_harness.pipeline import WallPipeline
from wall_harness.providers.library import (
    assistant_from_spec,
    local_draft_starter,
    local_library_answer,
)
from wall_harness.spec import parse_spec
from wall_harness.state import KnowledgeState

from .reading import (
    DraftCreate,
    DraftStarterRequest,
    DraftUpdate,
    EmailCapture,
    EntryUpdate,
    HighlightCreate,
    LibraryQuestion,
    NoteCreate,
    ReadingEntryCreate,
    ReadingStore,
    TaskCreate,
    TaskUpdate,
    TelegramCapture,
)
from .workspace import WallRecord, WallWorkspace

logger = logging.getLogger(__name__)


class RunRequest(BaseModel):
    use_llm: bool = True
    wall: str | None = None


class ReadingRefreshRequest(BaseModel):
    """Explicitly opt in to provider analysis while refreshing the reading inbox."""

    use_llm: bool = False
    wall: str | None = None
    asynchronous: bool = False


class ReadingRefreshResponse(BaseModel):
    wall_name: str
    item_count: int
    imported_count: int


class ReadingRefreshAccepted(BaseModel):
    job_id: str
    wall_name: str
    status: Literal["queued"] = "queued"


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
    reading_path = state_path.parent / "reading.db"
    static_path = Path(__file__).parent / "static"
    template_path = Path(__file__).parent / "templates" / "index.html"

    app = FastAPI(title="Wall", docs_url="/api/docs", redoc_url=None)
    app.mount("/static", StaticFiles(directory=static_path), name="static")
    app_password = os.getenv("WALL_APP_PASSWORD")
    capture_token = os.getenv("WALL_CAPTURE_TOKEN")
    refresh_token = os.getenv("WALL_REFRESH_TOKEN")
    telegram_secret_token = os.getenv("WALL_TELEGRAM_SECRET_TOKEN")
    telegram_allowed_chat_id = os.getenv("WALL_TELEGRAM_ALLOWED_CHAT_ID")
    capture_paths = {
        "/api/reading/captures/browser",
        "/api/reading/captures/email",
        "/api/reading/captures/telegram",
    }
    telegram_path = "/api/reading/captures/telegram"
    refresh_path = "/api/reading/refresh"
    refresh_status_prefix = "/api/reading/refreshes/"

    def has_valid_password(request: Request) -> bool:
        if not app_password:
            return False
        authorization = request.headers.get("Authorization", "")
        scheme, _, encoded = authorization.partition(" ")
        if scheme.lower() != "basic" or not encoded:
            return False
        try:
            decoded = b64decode(encoded, validate=True).decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            return False
        username, separator, password = decoded.partition(":")
        return bool(separator and username) and secrets.compare_digest(password, app_password)

    def has_valid_bearer_token(request: Request, expected_token: str | None) -> bool:
        if not expected_token:
            return False
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        return (
            bool(token)
            and scheme.lower() == "bearer"
            and secrets.compare_digest(token, expected_token)
        )

    def is_capture_request(request: Request) -> bool:
        return request.method == "POST" and request.url.path in capture_paths

    def has_valid_telegram_secret(request: Request) -> bool:
        supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        return bool(
            telegram_secret_token
            and supplied
            and secrets.compare_digest(supplied, telegram_secret_token)
        )

    def is_refresh_request(request: Request) -> bool:
        return request.method == "POST" and request.url.path == refresh_path

    def is_refresh_status_request(request: Request) -> bool:
        return request.method == "GET" and request.url.path.startswith(refresh_status_prefix)

    @app.middleware("http")
    async def password_protection(request: Request, call_next: RequestResponseEndpoint) -> Response:
        is_public_asset = request.url.path.startswith("/static/")
        is_public_post = request.url.path.startswith("/read/")
        capture_request = is_capture_request(request)
        telegram_request = request.method == "POST" and request.url.path == telegram_path
        refresh_request = is_refresh_request(request) or is_refresh_status_request(request)
        private_request = (
            request.url.path != "/healthz" and not is_public_asset and not is_public_post
        )
        capture_authorized = capture_request and has_valid_bearer_token(request, capture_token)
        telegram_authorized = telegram_request and has_valid_telegram_secret(request)
        refresh_authorized = refresh_request and has_valid_bearer_token(request, refresh_token)
        password_authorized = has_valid_password(request)
        capture_token_required = capture_request and bool(capture_token or telegram_secret_token)
        telegram_secret_required = telegram_request
        refresh_token_required = refresh_request and bool(refresh_token)
        should_reject = private_request and not (
            capture_authorized
            or telegram_authorized
            or refresh_authorized
            or password_authorized
            or (
                not app_password
                and not capture_token_required
                and not refresh_token_required
                and not telegram_secret_required
            )
        )
        if should_reject:
            authentication_header = (
                "Bearer"
                if capture_token_required or refresh_token_required or telegram_secret_required
                else 'Basic realm="Margin"'
            )
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": authentication_header},
            )
        return await call_next(request)

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

    def persist_latest(edition: WallEdition) -> None:
        atomic_write_text(
            latest_path(edition.wall_name),
            json.dumps(edition.model_dump(mode="json"), indent=2),
        )

    def import_edition(edition: WallEdition) -> int:
        imported_count = 0
        with ReadingStore(reading_path) as store:
            for ranked in edition.items:
                item = ranked.item
                entry = store.create_entry_if_new(
                    ReadingEntryCreate(
                        title=item.title,
                        url=item.url,
                        source=item.source,
                        summary=ranked.analysis or item.summary,
                        tags=[*item.tags, f"wall:{edition.wall_name}"],
                        origin="wall",
                    )
                )
                imported_count += int(entry is not None)
        return imported_count

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> HTMLResponse:
        return HTMLResponse(template_path.read_text(encoding="utf-8"))

    @app.get("/favicon.ico", status_code=204)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/reading/entries")
    def list_reading_entries(status: str | None = None) -> list[dict[str, object]]:
        with ReadingStore(reading_path) as store:
            return store.list_entries(status)

    @app.post("/api/reading/entries", status_code=201)
    def create_reading_entry(request: ReadingEntryCreate) -> dict[str, object]:
        with ReadingStore(reading_path) as store:
            return store.create_entry(request)

    @app.post("/api/reading/captures/browser", status_code=201)
    def capture_from_browser(request: ReadingEntryCreate) -> dict[str, object]:
        with ReadingStore(reading_path) as store:
            return store.create_entry(request.model_copy(update={"origin": "browser"}))

    @app.post("/api/reading/captures/email", status_code=201)
    def capture_forwarded_email(request: EmailCapture) -> dict[str, object]:
        with ReadingStore(reading_path) as store:
            return store.create_entry(request.as_entry())

    @app.post("/api/reading/captures/telegram", status_code=201)
    def capture_from_telegram(request: TelegramCapture) -> dict[str, object]:
        if telegram_allowed_chat_id and request.chat_id() != telegram_allowed_chat_id:
            raise HTTPException(status_code=403, detail="Telegram chat is not allowed")
        try:
            entry = request.as_entry()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        with ReadingStore(reading_path) as store:
            return store.create_entry(entry)

    @app.post("/api/reading/import/wall", status_code=201)
    def import_latest_wall(wall: str | None = None) -> dict[str, int]:
        record = select(wall)
        edition_path = latest_path(record.spec.name)
        if not edition_path.exists():
            raise HTTPException(status_code=404, detail="Build a Wall edition before importing it")
        try:
            edition = WallEdition.model_validate_json(edition_path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as exc:
            raise HTTPException(status_code=500, detail="Latest edition is unreadable") from exc
        return {"imported_count": import_edition(edition)}

    def run_reading_refresh(spec: WallSpec, *, use_llm: bool) -> ReadingRefreshResponse:
        try:
            pipeline = make_pipeline(spec)
            edition = pipeline.run(use_llm=use_llm)
            pipeline.write(edition)
        except Exception as exc:
            logger.error("Reading refresh failed (%s)", type(exc).__name__)
            raise
        persist_latest(edition)
        return ReadingRefreshResponse(
            wall_name=edition.wall_name,
            item_count=len(edition.items),
            imported_count=import_edition(edition),
        )

    def run_refresh_job(job_id: str, spec: WallSpec, *, use_llm: bool) -> None:
        try:
            result = run_reading_refresh(spec, use_llm=use_llm)
        except Exception:
            with ReadingStore(reading_path) as store:
                store.fail_refresh_job(job_id)
            return
        with ReadingStore(reading_path) as store:
            store.complete_refresh_job(
                job_id,
                item_count=result.item_count,
                imported_count=result.imported_count,
            )

    @app.post("/api/reading/refresh", response_model=ReadingRefreshResponse, status_code=201)
    def refresh_reading_inbox(
        request: ReadingRefreshRequest, http_request: Request, background_tasks: BackgroundTasks
    ) -> ReadingRefreshResponse | JSONResponse:
        """Build the selected Wall and add only its new signal to Margin's inbox."""

        spec = select(request.wall).spec
        # A scheduler token is intentionally unable to initiate provider calls. It can keep the
        # inbox fresh, while LLM use remains an explicit owner action behind Basic auth.
        use_llm = request.use_llm and not has_valid_bearer_token(http_request, refresh_token)
        if request.asynchronous:
            with ReadingStore(reading_path) as store:
                job = store.create_refresh_job(spec.name)
            background_tasks.add_task(run_refresh_job, str(job["id"]), spec, use_llm=use_llm)
            accepted = ReadingRefreshAccepted(job_id=str(job["id"]), wall_name=spec.name)
            return JSONResponse(
                status_code=202,
                content=accepted.model_dump(),
                background=background_tasks,
            )
        try:
            return run_reading_refresh(spec, use_llm=use_llm)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail="Source refresh failed. Check the server logs for details.",
            ) from exc

    @app.get("/api/reading/refresh-status")
    def get_latest_reading_refresh() -> dict[str, object] | None:
        """Expose scheduler health to the owner dashboard, never to the scheduler token."""

        with ReadingStore(reading_path) as store:
            return store.latest_refresh_job()

    @app.get("/api/reading/refreshes/{job_id}")
    def get_reading_refresh(job_id: str) -> dict[str, object]:
        try:
            with ReadingStore(reading_path) as store:
                return store.get_refresh_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Refresh job not found") from exc

    @app.get("/api/reading/entries/{entry_id}")
    def get_reading_entry(entry_id: str) -> dict[str, object]:
        try:
            with ReadingStore(reading_path) as store:
                return store.get_entry(entry_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Reading entry not found") from exc

    @app.patch("/api/reading/entries/{entry_id}")
    def update_reading_entry(entry_id: str, request: EntryUpdate) -> dict[str, object]:
        try:
            with ReadingStore(reading_path) as store:
                return store.update_entry(entry_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Reading entry not found") from exc

    @app.post("/api/reading/entries/{entry_id}/notes", status_code=201)
    def add_reading_note(entry_id: str, request: NoteCreate) -> dict[str, object]:
        try:
            with ReadingStore(reading_path) as store:
                return store.add_note(entry_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Reading entry not found") from exc

    @app.post("/api/reading/entries/{entry_id}/highlights", status_code=201)
    def add_reading_highlight(entry_id: str, request: HighlightCreate) -> dict[str, object]:
        try:
            with ReadingStore(reading_path) as store:
                return store.add_highlight(entry_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Reading entry not found") from exc

    @app.get("/api/reading/tasks")
    def list_reading_tasks(include_done: bool = True) -> list[dict[str, object]]:
        with ReadingStore(reading_path) as store:
            return store.list_tasks(include_done)

    @app.post("/api/reading/tasks", status_code=201)
    def create_reading_task(request: TaskCreate) -> dict[str, object]:
        try:
            with ReadingStore(reading_path) as store:
                return store.create_task(request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Reading entry not found") from exc

    @app.patch("/api/reading/tasks/{task_id}")
    def update_reading_task(task_id: str, request: TaskUpdate) -> dict[str, object]:
        try:
            with ReadingStore(reading_path) as store:
                return store.update_task(task_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc

    @app.get("/api/reading/drafts")
    def list_reading_drafts(status: str | None = None) -> list[dict[str, object]]:
        with ReadingStore(reading_path) as store:
            return store.list_drafts(status)

    @app.post("/api/reading/drafts/starter")
    def build_draft_starter(request: DraftStarterRequest) -> dict[str, object]:
        spec = select().spec
        with ReadingStore(reading_path) as store:
            sources = store.entries_for_draft_starter(request.entry_ids)
        try:
            assistant = assistant_from_spec(spec)
        except Exception as exc:
            logger.error("Draft assistant configuration unavailable (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=502,
                detail="Draft assistance is unavailable. Your sources and notes remain local.",
            ) from exc
        if assistant is None:
            return {
                "body": local_draft_starter(request.title, request.intent, sources),
                "sources": sources,
                "mode": "local",
            }
        try:
            body = assistant.draft_starter(request.title, request.intent, sources, spec)
        except Exception as exc:
            logger.error("Draft assistant unavailable (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=502,
                detail="Draft assistance is unavailable. Your sources and notes remain local.",
            ) from exc
        return {"body": body, "sources": sources, "mode": "ai"}

    @app.post("/api/reading/drafts", status_code=201)
    def create_reading_draft(request: DraftCreate) -> dict[str, object]:
        try:
            with ReadingStore(reading_path) as store:
                return store.create_draft(request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Reading entry not found") from exc

    @app.get("/api/reading/drafts/{draft_id}")
    def get_reading_draft(draft_id: str) -> dict[str, object]:
        try:
            with ReadingStore(reading_path) as store:
                return store.get_draft(draft_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Draft not found") from exc

    @app.patch("/api/reading/drafts/{draft_id}")
    def update_reading_draft(draft_id: str, request: DraftUpdate) -> dict[str, object]:
        try:
            with ReadingStore(reading_path) as store:
                return store.update_draft(draft_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Draft not found") from exc

    @app.post("/api/reading/drafts/{draft_id}/publish")
    def publish_reading_draft(draft_id: str) -> dict[str, object]:
        try:
            with ReadingStore(reading_path) as store:
                return store.publish_draft(draft_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Draft not found") from exc

    @app.get("/api/reading/review")
    def get_weekly_review() -> dict[str, object]:
        with ReadingStore(reading_path) as store:
            return store.weekly_review()

    @app.post("/api/reading/ask")
    def ask_reading_library(request: LibraryQuestion) -> dict[str, object]:
        spec = select().spec
        with ReadingStore(reading_path) as store:
            sources = store.relevant_material(request.question)
        try:
            assistant = assistant_from_spec(spec)
        except Exception as exc:
            logger.error("Library assistant configuration unavailable (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=502,
                detail="Library assistant is unavailable. Your saved material remains local.",
            ) from exc
        if assistant is None:
            return {
                "answer": local_library_answer(request.question, sources),
                "sources": sources,
                "mode": "local",
            }
        try:
            answer = assistant.answer(request.question, sources, spec)
        except Exception as exc:
            logger.error("Library assistant unavailable (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=502,
                detail="Library assistant is unavailable. Your saved material remains local.",
            ) from exc
        return {"answer": answer, "sources": sources, "mode": "ai"}

    @app.get("/api/reading/export")
    def export_reading_workspace() -> Response:
        with ReadingStore(reading_path) as store:
            entries = store.list_entries()
            drafts = [store.get_draft(str(draft["id"])) for draft in store.list_drafts()]
        bundle = BytesIO()
        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for entry in entries:
                filename = f"reading/{entry['id']}.md"
                tags = entry["tags"]
                assert isinstance(tags, list)
                archive.writestr(
                    filename,
                    "\n".join(
                        [
                            f"# {entry['title']}",
                            "",
                            f"- Source: {entry['source']}",
                            f"- URL: {entry['url'] or ''}",
                            f"- Status: {entry['status']}",
                            f"- Tags: {', '.join(str(tag) for tag in tags)}",
                            "",
                            str(entry["summary"]),
                        ]
                    ),
                )
            for draft in drafts:
                sources = draft["sources"]
                assert isinstance(sources, list)
                source_lines = [
                    f"- [{source['title']}]({source['url']})"
                    for source in sources
                    if isinstance(source, dict) and source.get("url")
                ]
                archive.writestr(
                    f"drafts/{draft['slug'] or draft['id']}.md",
                    "\n".join(
                        [
                            f"# {draft['title']}",
                            "",
                            str(draft["body"]),
                            "",
                            "## Sources",
                            *source_lines,
                        ]
                    ),
                )
        return Response(
            bundle.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=reading-home-export.zip"},
        )

    @app.get("/read/{slug}", response_class=HTMLResponse)
    def published_reading_draft(slug: str) -> HTMLResponse:
        try:
            with ReadingStore(reading_path) as store:
                draft = store.public_draft(slug)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Published post not found") from exc
        sources = draft["sources"]
        assert isinstance(sources, list)
        source_links = "".join(
            f'<li><a href="{escape(str(source["url"]), quote=True)}">'
            f"{escape(str(source['title']))}</a></li>"
            for source in sources
            if isinstance(source, dict) and source.get("url")
        )
        title = escape(str(draft["title"]))
        body = escape(str(draft["body"])).replace("\n", "<br>\n")
        return HTMLResponse(
            "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            "content='width=device-width, initial-scale=1'><title>"
            f"{title} — Margin</title><link rel='stylesheet' href='/static/app.css'></head>"
            "<body class='public-post'><main><p class='eyebrow'>Published from Margin</p>"
            f"<h1>{title}</h1><article>{body}</article>"
            f"<section><h2>Sources</h2><ul>{source_links}</ul></section></main></body></html>"
        )

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
        persist_latest(edition)
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

    @app.get("/api/sources/health")
    def get_source_health(wall: str | None = None) -> list[dict[str, object]]:
        spec = select(wall).spec
        with KnowledgeState(state_path) as state:
            return state.source_health(spec.name)

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
