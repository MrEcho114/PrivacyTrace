"""HTTP seam for local private intake; no browser-supplied scanner facts."""

from zipfile import BadZipFile

from fastapi import HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import Field

from .auth import authorize_draft_access
from .isolated_scan import ScanError
from .models import Model
from .package_set import PackageSetIntegrityError
from .web_intake import UploadTooLarge
from .web_models import (
    CandidateInput,
    DraftInput,
    ExternalPolicyExportInput,
    ModelSettings,
    StartInput,
)


class RevisionInput(Model):
    revision: int = Field(ge=1, strict=True)


def web_operation(action):
    try:
        return action()
    except KeyError as exc:
        raise HTTPException(404, detail="DRAFT_NOT_FOUND") from exc
    except ScanError as exc:
        raise HTTPException(503, detail="ISOLATED_INSPECTION_UNAVAILABLE") from exc
    except (ValueError, OSError) as exc:
        allowed = {"MODEL_NOT_CONFIGURED", "MODEL_CONFIGURATION_INCOMPLETE"}
        code = str(exc) if str(exc) in allowed else "INPUT_OR_VERSION_REJECTED"
        raise HTTPException(409, detail=code) from exc


def install_web_api(app, local_write):
    service = app.state.web_intake

    @app.exception_handler(RequestValidationError)
    async def input_error(request, exc):
        # Pydantic error inputs can contain keys or full private policy text.
        if not request.url.path.startswith("/api/v1/web/"):
            res = await request_validation_exception_handler(request, exc)
            body = res.body.decode("utf-8")
            if "pt_cap_" in body:
                import json
                import re

                body = re.sub(r"pt_cap_[A-Za-z0-9_-]{20,}", "pt_cap_***", body)
                return JSONResponse(status_code=422, content=json.loads(body))
            return res
        return JSONResponse(status_code=422, content={"detail": "INPUT_VALIDATION_FAILED"})

    @app.get("/api/v1/web/settings")
    def settings(request: Request):
        if getattr(app.state, "config", None) and app.state.config.mode == "remote":
            raise HTTPException(403, detail="SETTINGS_FORBIDDEN_IN_REMOTE_MODE")
        return web_operation(service.settings)

    @app.post("/api/v1/web/settings")
    def configure(payload: ModelSettings, request: Request):
        if getattr(app.state, "config", None) and app.state.config.mode == "remote":
            raise HTTPException(403, detail="SETTINGS_FORBIDDEN_IN_REMOTE_MODE")
        local_write(request)
        return web_operation(lambda: service.configure(payload))

    def draft_access(request: Request, draft_id: str) -> None:
        if app.state.config.mode != "remote":
            if request.method != "GET":
                local_write(request)
            return
        authorize_draft_access(request, service, draft_id)

    @app.post("/api/v1/web/drafts")
    def create(payload: DraftInput, request: Request):
        is_remote = (
            getattr(app.state, "config", None) and app.state.config.mode == "remote"
        )
        if not is_remote:
            local_write(request)
        if is_remote:
            from .auth import generate_capability_token

            token, digest = generate_capability_token()
            owner_ip = getattr(request.state, "client_ip", "unknown")
            res = web_operation(
                lambda: service.create(payload, token_digest=digest, owner_ip=owner_ip)
            )
        else:
            res = web_operation(lambda: service.create(payload))
        if is_remote:
            draft_dict = res if isinstance(res, dict) else res.model_dump()
            draft_dict["capability_token"] = token
            draft_dict["token"] = token
            draft_dict["secret_token"] = token
            return draft_dict
        return res

    @app.get("/api/v1/web/drafts/{draft_id}")
    def get(draft_id: str, request: Request):
        draft_access(request, draft_id)
        return web_operation(lambda: service.get(draft_id))

    @app.post("/api/v1/web/drafts/{draft_id}/apk")
    async def upload(draft_id: str, request: Request):
        draft_access(request, draft_id)
        try:
            return await service.upload(draft_id, request, expect_package_set=False)
        except KeyError as exc:
            raise HTTPException(404, detail="DRAFT_NOT_FOUND") from exc
        except UploadTooLarge as exc:
            raise HTTPException(413, detail="UPLOAD_TOO_LARGE") from exc
        except ScanError as exc:
            raise HTTPException(503, detail="ISOLATED_INSPECTION_UNAVAILABLE") from exc
        except PackageSetIntegrityError as exc:
            raise HTTPException(status_code=exc.http_status, detail=exc.code) from exc
        except (ValueError, OSError) as exc:
            raise HTTPException(409, detail="UPLOAD_REJECTED") from exc
        except (BadZipFile, EOFError) as exc:
            raise HTTPException(status_code=400, detail="CORRUPTED_FILE") from exc

    @app.post("/api/v1/web/drafts/{draft_id}/package-set")
    async def upload_package_set(draft_id: str, request: Request):
        draft_access(request, draft_id)
        try:
            return await service.upload(draft_id, request, expect_package_set=True)
        except KeyError as exc:
            raise HTTPException(404, detail="DRAFT_NOT_FOUND") from exc
        except UploadTooLarge as exc:
            raise HTTPException(413, detail="UPLOAD_TOO_LARGE") from exc
        except ScanError as exc:
            raise HTTPException(503, detail="ISOLATED_INSPECTION_UNAVAILABLE") from exc
        except PackageSetIntegrityError as exc:
            raise HTTPException(status_code=exc.http_status, detail=exc.code) from exc
        except (ValueError, OSError) as exc:
            raise HTTPException(409, detail="UPLOAD_REJECTED") from exc
        except (BadZipFile, EOFError) as exc:
            raise HTTPException(status_code=400, detail="CORRUPTED_FILE") from exc

    @app.post("/api/v1/web/drafts/{draft_id}/sources/{source_id}/fetch")
    def fetch(draft_id: str, source_id: str, payload: RevisionInput, request: Request):
        draft_access(request, draft_id)
        return web_operation(lambda: service.fetch_source(draft_id, source_id, payload.revision))

    @app.post("/api/v1/web/drafts/{draft_id}/sources/{source_id}/extract")
    def extract(draft_id: str, source_id: str, payload: RevisionInput, request: Request):
        draft_access(request, draft_id)
        return web_operation(lambda: service.extract(draft_id, source_id, payload.revision))

    @app.post("/api/v1/web/drafts/{draft_id}/candidates")
    def save(draft_id: str, payload: CandidateInput, request: Request):
        draft_access(request, draft_id)
        return web_operation(lambda: service.save_candidates(draft_id, payload))

    @app.post("/api/v1/web/drafts/{draft_id}/start")
    def start(draft_id: str, payload: StartInput, request: Request):
        draft_access(request, draft_id)
        return web_operation(lambda: service.start(draft_id, payload))

    @app.post("/api/v1/web/drafts/{draft_id}/sources/discover")
    def discover_sources(draft_id: str, request: Request):
        draft_access(request, draft_id)
        return web_operation(lambda: service.discover_sources(draft_id))

    @app.post("/api/v1/web/drafts/{draft_id}/import-external")
    def import_external(
        draft_id: str, payload: ExternalPolicyExportInput, request: Request
    ):
        draft_access(request, draft_id)
        return web_operation(lambda: service.import_external(draft_id, payload))
