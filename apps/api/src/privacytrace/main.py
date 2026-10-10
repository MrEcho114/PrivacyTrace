"""Local persisted jobs, review audit events, and explicit synthetic demo API."""

import os
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .consistency import evaluate
from .job_store import JobStore
from .models import AnalysisJob, EvaluationInput, EvaluationResult
from .resources import ROOT, read_json, taxonomy
from .runtime_models import JobsResponse, Report, ReviewRequest

STORE_ROOT_ENV = "PRIVACYTRACE_STORE_ROOT"


def operation(action):
    try:
        return action()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(
            status_code=409, detail="Job storage or validation rejected the operation"
        ) from exc


def local_write(request: Request):
    allowed = {"127.0.0.1", "localhost", "::1", "testserver"}
    host = urlparse(str(request.url)).hostname
    origin = request.headers.get("origin")
    if host not in allowed or request.headers.get("X-PrivacyTrace-Local") != "1":
        raise HTTPException(status_code=403, detail="Local write request required")
    if origin:
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in allowed - {
            "testserver"
        }:
            raise HTTPException(status_code=403, detail="Cross-origin write rejected")


def create_app(store_root: Path | None = None):
    app = FastAPI(title="PrivacyTrace", version="0.1.0")
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"]
    )
    # An explicit argument wins; the environment variable lets the acceptance
    # harness boot an isolated instance without touching the repository data dir.
    configured = store_root or (os.environ.get(STORE_ROOT_ENV) or None)
    app.state.job_store = JobStore(Path(configured) if configured else ROOT / "data/jobs")

    @app.middleware("http")
    async def bound_job_writes(request: Request, call_next):
        if request.method == "POST" and request.url.path.startswith("/api/v1/jobs/"):
            size = 0
            chunks = []
            async for chunk in request.stream():
                size += len(chunk)
                if size > 512 * 1024:
                    return JSONResponse(status_code=413, content={"detail": "Request too large"})
                chunks.append(chunk)
            request._body = b"".join(chunks)
        return await call_next(request)

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "version": "0.1.0", "mode": "local-jobs"}

    @app.get("/api/v1/taxonomy")
    def get_taxonomy():
        return taxonomy()

    @app.get("/api/v1/demo/report")
    def demo_report():
        bundle = EvaluationInput.model_validate(read_json("samples/demo/evaluation-input.json"))
        return {
            "demo": True,
            "sample": {
                "name": "PrivacyTrace 示例 App",
                "package_name": "org.privacytrace.demo",
                "version": "synthetic-0.1",
                "input_mode": "SYNTHETIC",
            },
            "job": bundle.job,
            # The demo report is assembled in this response, not loaded from a
            # stored job, so its delivery mode is a live generation.
            "delivery_mode": "LIVE_GENERATED",
            "result": evaluate(bundle),
            "evidence": bundle.evidence,
            "behaviors": bundle.behaviors,
            "policy_documents": bundle.policy_documents,
        }

    @app.get("/api/v1/demo/evidence/{evidence_id}")
    def demo_evidence(evidence_id: str):
        bundle = EvaluationInput.model_validate(read_json("samples/demo/evaluation-input.json"))
        for item in bundle.evidence:
            if item.id == evidence_id:
                return item
        raise HTTPException(status_code=404, detail="Evidence not found")

    @app.post("/api/v1/consistency/evaluate", response_model=EvaluationResult)
    def evaluate_evidence(bundle: EvaluationInput):
        return evaluate(bundle)

    @app.get("/api/v1/jobs", response_model=JobsResponse)
    def list_jobs():
        return operation(lambda: JobsResponse(jobs=app.state.job_store.list()))

    @app.get("/api/v1/jobs/{job_id}", response_model=AnalysisJob)
    def get_job(job_id: str):
        return operation(lambda: app.state.job_store.get(job_id))

    @app.get("/api/v1/jobs/{job_id}/report", response_model=Report)
    def get_report(job_id: str):
        return operation(lambda: app.state.job_store.report(job_id))

    @app.post("/api/v1/jobs/{job_id}/reviews", response_model=Report)
    def review(job_id: str, payload: ReviewRequest, request: Request):
        local_write(request)
        return operation(lambda: app.state.job_store.review(job_id, payload))

    @app.post("/api/v1/jobs/{job_id}/cancel", response_model=AnalysisJob)
    def cancel(job_id: str, request: Request):
        local_write(request)
        return operation(lambda: app.state.job_store.cancel(job_id))

    return app


app = create_app()
