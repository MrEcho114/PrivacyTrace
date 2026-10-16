"""Local persisted jobs, review audit events, and explicit synthetic demo API."""

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request

from .auth import SecuritySeam, generate_capability_token
from .config import ServerConfig
from .consistency import evaluate
from .job_store import JobStore
from .middleware import (
    JobWriteBoundsMiddleware,
    RemoteTransportSecurityMiddleware,
    install_log_redaction,
)
from .models import AnalysisJob, EvaluationInput, EvaluationResult, SourceOrigin
from .resources import ROOT, read_json, taxonomy
from .runtime_models import JobsResponse, Report, ReviewRequest
from .web_api import install_web_api
from .web_intake import WebIntake

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


def create_app(
    store_root: Path | None = None,
    mode: str | None = None,
    config: ServerConfig | None = None,
    allowed_hosts: list[str] | None = None,
):
    install_log_redaction()
    if config is None:
        config = ServerConfig.from_env(
            store_root=store_root, mode=mode, allowed_hosts=allowed_hosts
        )

    @asynccontextmanager
    async def lifespan(app):
        app.state.web_intake.start_service()
        try:
            yield
        finally:
            app.state.web_intake.close()

    app = FastAPI(title="PrivacyTrace", version="0.1.0", lifespan=lifespan)
    app.state.config = config

    app.add_middleware(RemoteTransportSecurityMiddleware, config=config)
    app.add_middleware(JobWriteBoundsMiddleware, config=config)

    # An explicit argument wins; the environment variable lets the acceptance
    # harness boot an isolated instance without touching the repository data dir.
    configured = store_root or (os.environ.get(STORE_ROOT_ENV) or None)
    app.state.job_store = JobStore(
        Path(configured) if configured else ROOT / "data/jobs"
    )
    app.state.web_intake = WebIntake(app.state.job_store)
    app.state.security_seam = SecuritySeam(config, app.state.job_store)
    install_web_api(app, local_write)

    @app.get("/api/v1/health")
    def health():
        mode_val = "remote" if config.mode == "remote" else "local-jobs"
        return {"status": "ok", "version": "0.1.0", "mode": mode_val}

    @app.get("/api/v1/taxonomy")
    def get_taxonomy():
        return taxonomy()

    @app.get("/api/v1/demo/report")
    def demo_report():
        bundle = EvaluationInput.model_validate(
            read_json("samples/demo/evaluation-input.json")
        )
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
        bundle = EvaluationInput.model_validate(
            read_json("samples/demo/evaluation-input.json")
        )
        for item in bundle.evidence:
            if item.id == evidence_id:
                return item
        raise HTTPException(status_code=404, detail="Evidence not found")

    @app.post("/api/v1/consistency/evaluate", response_model=EvaluationResult)
    def evaluate_evidence(bundle: EvaluationInput):
        if bundle.job.input_mode == "CONTROLLED_APK":
            raise HTTPException(
                status_code=422,
                detail="Controlled facts require the hash-verified controlled CLI",
            )
        return evaluate(bundle)

    if config.mode == "remote":
        @app.post("/api/v1/jobs")
        async def create_job(request: Request):
            payload = {}
            try:
                body = await request.body()
                if body:
                    payload = json.loads(body)
            except Exception:
                payload = {}

            token, digest = generate_capability_token()
            job_id = str(uuid4())
            input_mode = payload.get("input_mode", "APK")
            sample_id = payload.get("sample_id", f"sample-{job_id[:8]}")
            ruleset_ver = taxonomy()["version"]

            if input_mode == "CONTROLLED_APK":
                origin = SourceOrigin.CONTROLLED
            elif input_mode == "SYNTHETIC":
                origin = SourceOrigin.SYNTHETIC
            else:
                origin = SourceOrigin.REAL_SCAN

            job = AnalysisJob(
                id=job_id,
                sample_id=sample_id,
                package_name=f"org.privacytrace.{sample_id}",
                version_code=1,
                input_mode=input_mode,
                source_origin=origin,
                state="QUEUED",
                ruleset_version=ruleset_ver,
                created_at=datetime.now(timezone.utc),
            )
            app.state.job_store.create_if_absent(job, token_digest=digest)
            return {
                "job_id": job.id,
                "id": job.id,
                "capability_token": token,
                "token": token,
                "secret_token": token,
                "status": "PENDING",
            }

    @app.get("/api/v1/jobs", response_model=JobsResponse)
    def list_jobs(request: Request):
        if config.mode == "remote":
            app.state.security_seam.authorize_jobs_listing(request)
        return operation(lambda: JobsResponse(jobs=app.state.job_store.list()))

    @app.get("/api/v1/jobs/{job_id}", response_model=AnalysisJob)
    def get_job(job_id: str, request: Request):
        if config.mode == "remote":
            app.state.security_seam.authorize_job_access(request, job_id, action="read")
        return operation(lambda: app.state.job_store.get(job_id))

    @app.get("/api/v1/jobs/{job_id}/report", response_model=Report)
    def get_report(job_id: str, request: Request):
        if config.mode == "remote":
            app.state.security_seam.authorize_job_access(request, job_id, action="read")
        return operation(lambda: app.state.job_store.report(job_id))

    @app.post("/api/v1/jobs/{job_id}/reviews", response_model=Report)
    def review(job_id: str, payload: ReviewRequest, request: Request):
        if config.mode == "remote":
            app.state.security_seam.authorize_job_access(request, job_id, action="write")
        else:
            local_write(request)
        return operation(lambda: app.state.job_store.review(job_id, payload))

    @app.post("/api/v1/jobs/{job_id}/cancel", response_model=AnalysisJob)
    def cancel(job_id: str, request: Request):
        if config.mode == "remote":
            app.state.security_seam.authorize_job_access(request, job_id, action="write")
        else:
            local_write(request)
        return operation(lambda: app.state.job_store.cancel(job_id))

    @app.delete("/api/v1/jobs/{job_id}")
    def delete_job(job_id: str, request: Request):
        if config.mode == "remote":
            app.state.security_seam.authorize_job_access(request, job_id, action="delete")
        else:
            local_write(request)
        operation(lambda: app.state.job_store.delete(job_id))
        return {"status": "deleted", "job_id": job_id}

    return app


app = create_app()
