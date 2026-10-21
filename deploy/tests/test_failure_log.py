"""Failure log: endpoint and status, never the request itself."""

import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

DEPLOY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEPLOY))
import serve  # noqa: E402

ROUTE = "/api/v1/web/drafts/{draft_id}/sources/discover"


async def conflict(request):
    return JSONResponse({"detail": "conflict"}, status_code=409)


async def healthy(request):
    return JSONResponse({"status": "ok"})


class FailureLogMiddlewareTests(unittest.TestCase):
    def test_entrypoint_composes_the_failure_log_over_the_surface(self):
        sentinel = object()
        with patch.object(serve, "create_app", return_value=sentinel):
            application = serve.build_application()
        self.assertIsInstance(application, serve.FailureLogMiddleware)
        self.assertIs(application.app, sentinel)

    def test_failed_request_logs_route_template_and_status_only(self):
        app = serve.FailureLogMiddleware(
            Starlette(routes=[Route(ROUTE, conflict, methods=["POST"])])
        )
        with self.assertLogs("uvicorn.error", level=logging.WARNING) as captured:
            with TestClient(app, base_url="https://privacytrace.test") as client:
                response = client.post(
                    "/api/v1/web/drafts/abc-123/sources/discover",
                    content=b"private-body",
                )
        self.assertEqual(response.status_code, 409)
        records = "\n".join(captured.output)
        self.assertIn("method=POST", records)
        self.assertIn(f"route={ROUTE}", records)
        self.assertIn("status=409", records)
        self.assertNotIn("abc-123", records)

    def test_unmatched_failure_is_logged_without_the_request_path(self):
        app = serve.FailureLogMiddleware(Starlette(routes=[Route("/api/v1/health", healthy)]))
        with self.assertLogs("uvicorn.error", level=logging.WARNING) as captured:
            with TestClient(app, base_url="https://privacytrace.test") as client:
                response = client.get("/api/v1/unknown/abc-123")
        self.assertEqual(response.status_code, 404)
        records = "\n".join(captured.output)
        self.assertIn("route=UNMATCHED", records)
        self.assertNotIn("abc-123", records)

    def test_successful_request_is_not_logged(self):
        app = serve.FailureLogMiddleware(Starlette(routes=[Route("/api/v1/health", healthy)]))
        with TestClient(app, base_url="https://privacytrace.test") as client:
            with self.assertNoLogs("uvicorn.error", level=logging.WARNING):
                response = client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
