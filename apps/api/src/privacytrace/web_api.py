"""HTTP seam for local private intake; no browser-supplied scanner facts."""

from fastapi import HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import Field

from .models import Model
from .web_models import CandidateInput, DraftInput, ModelSettings, StartInput


class RevisionInput(Model):
    revision: int = Field(ge=1, strict=True)


def web_operation(action):
    try:
        return action()
    except KeyError as exc:
        raise HTTPException(404, detail="DRAFT_NOT_FOUND") from exc
    except (ValueError, OSError) as exc:
        code = (
            "MODEL_NOT_CONFIGURED"
            if str(exc) == "MODEL_NOT_CONFIGURED"
            else "INPUT_OR_VERSION_REJECTED"
        )
        raise HTTPException(409, detail=code) from exc


def install_web_api(app, local_write):
    service = app.state.web_intake

    @app.exception_handler(RequestValidationError)
    async def input_error(request, exc):
        # Pydantic error inputs can contain keys or full private policy text.
        if not request.url.path.startswith("/api/v1/web/"):
            return await request_validation_exception_handler(request, exc)
        return JSONResponse(status_code=422, content={"detail": "INPUT_VALIDATION_FAILED"})

    @app.get("/api/v1/web/settings")
    def settings():
        return web_operation(service.settings)

    @app.post("/api/v1/web/settings")
    def configure(payload: ModelSettings, request: Request):
        local_write(request)
        return web_operation(lambda: service.configure(payload))

    @app.post("/api/v1/web/drafts")
    def create(payload: DraftInput, request: Request):
        local_write(request)
        return web_operation(lambda: service.create(payload))

    @app.get("/api/v1/web/drafts/{draft_id}")
    def get(draft_id: str):
        return web_operation(lambda: service.get(draft_id))

    @app.post("/api/v1/web/drafts/{draft_id}/apk")
    async def upload(draft_id: str, request: Request):
        local_write(request)
        try:
            return await service.upload(draft_id, request)
        except KeyError as exc:
            raise HTTPException(404, detail="DRAFT_NOT_FOUND") from exc
        except (ValueError, OSError) as exc:
            raise HTTPException(409, detail="UPLOAD_REJECTED") from exc

    @app.post("/api/v1/web/drafts/{draft_id}/sources/{source_id}/fetch")
    def fetch(draft_id: str, source_id: str, payload: RevisionInput, request: Request):
        local_write(request)
        return web_operation(lambda: service.fetch_source(draft_id, source_id, payload.revision))

    @app.post("/api/v1/web/drafts/{draft_id}/sources/{source_id}/extract")
    def extract(draft_id: str, source_id: str, payload: RevisionInput, request: Request):
        local_write(request)
        return web_operation(lambda: service.extract(draft_id, source_id, payload.revision))

    @app.post("/api/v1/web/drafts/{draft_id}/candidates")
    def save(draft_id: str, payload: CandidateInput, request: Request):
        local_write(request)
        return web_operation(lambda: service.save_candidates(draft_id, payload))

    @app.post("/api/v1/web/drafts/{draft_id}/start")
    def start(draft_id: str, payload: StartInput, request: Request):
        local_write(request)
        return web_operation(lambda: service.start(draft_id, payload))
