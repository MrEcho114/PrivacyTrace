"""Acceptance-only HTTP fixtures; never imported by the production API.

The fetch/LLM HTTP seam is real, but the DNS target and model answers are test
fixtures. Scan execution still uses the unchanged restricted Docker worker.
"""

import json
import os
import socket
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from privacytrace import policy_fetch
from privacytrace.main import create_app

app = create_app()
HOST_TEXT = "当您拍照时，我们会访问相机。我们不会读取联系人。"
SDK_TEXT = "第三方统计服务会处理设备标识，用于统计应用使用情况。"
original_target = policy_fetch.public_target


def fixture_target(url):
    if urlsplit(url).hostname == "policy.privacytrace.test":
        port = int(os.environ["PRIVACYTRACE_LIVE_API_PORT"])
        return (
            urlsplit(url)._replace(netloc=f"127.0.0.1:{port}"),
            port,
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port)),
        )
    return original_target(url)


policy_fetch.public_target = fixture_target


@app.get("/policy/host", response_class=HTMLResponse)
def host():
    return (
        "<html><body><h1>验收用人工政策 A</h1><p>"
        + HOST_TEXT
        + "</p><script>ignored()</script></body></html>"
    )


@app.get("/policy/sdk", response_class=HTMLResponse)
def sdk():
    return "<html><body><h1>验收用人工政策 B</h1><p>" + SDK_TEXT + "</p></body></html>"


@app.post("/v1/chat/completions")
async def model(request: Request):
    body = await request.json()
    user_text = body["messages"][-1]["content"]
    if body.get("model") == "malformed-fixture":
        value = "invalid JSON"
    elif HOST_TEXT in user_text:
        value = json.dumps(
            [
                {
                    "excerpt": "当您拍照时，我们会访问相机。",
                    "data_type": "CAMERA",
                    "polarity": "AFFIRMATIVE",
                    "subject": "HOST_APP",
                    "action": "ACCESS",
                    "condition": "当您拍照时",
                },
                {
                    "excerpt": "我们不会读取联系人。",
                    "data_type": "CONTACTS",
                    "polarity": "NEGATIVE",
                    "subject": "HOST_APP",
                    "action": "ACCESS",
                },
            ],
            ensure_ascii=False,
        )
    else:
        value = json.dumps(
            [
                {
                    "excerpt": SDK_TEXT,
                    "data_type": "DEVICE_IDENTIFIER",
                    "polarity": "AFFIRMATIVE",
                    "subject": "THIRD_PARTY",
                    "action": "ACCESS",
                    "declared_purpose": "统计应用使用情况",
                }
            ],
            ensure_ascii=False,
        )
    return JSONResponse(
        {
            "choices": [{"message": {"content": value}}],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            },
        }
    )
