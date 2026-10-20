"""Public, non-secret transport negotiation for the Android thin client."""

from uuid import UUID

from fastapi.responses import JSONResponse

from .isolated_scan import MAX_INPUT
from .package_set import MAX_FILE_SIZE, MAX_PACKAGE_SET_SIZE


def install_mobile_capabilities(app, *, durable: bool):
    @app.get("/api/v1/mobile-capabilities")
    def capabilities():
        store = app.state.job_store
        supported = (
            app.state.config.mode == "remote"
            and durable
            and getattr(store, "uses_postgres", False)
            and callable(getattr(app.state.web_intake, "delete_draft", None))
        )
        try:
            instance = str(UUID(str(getattr(store, "instance_id", ""))))
        except ValueError:
            supported = False
            instance = None
        # Byte limits describe hard bounds, never current capacity or readiness.
        payload = {"protocol": "privacytrace-mobile/1", "supported": bool(supported)}
        if supported:
            payload.update(
                instance_id=instance,
                upload_format="apk-or-zip",
                max_upload_bytes=min(MAX_INPUT, app.state.config.max_apk_body_bytes),
                max_file_bytes=MAX_FILE_SIZE,
                max_total_bytes=MAX_PACKAGE_SET_SIZE,
                max_files=101,
                retention="UNTIL_EXPLICIT_DELETE",
                delete_draft=True,
            )
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})
