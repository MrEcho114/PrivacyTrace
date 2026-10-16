"""Filming-only authored policy HTTP fixtures. Never loaded by production.

The private .test hostname resolves to this owned local HTTP server. The model
request and Docker scan are real; these policies are authored film inputs, not
public third-party policies and not the frozen Spec30 benchmark inputs.
"""

import os
import socket
from urllib.parse import urlsplit

from fastapi.responses import HTMLResponse
from privacytrace import policy_fetch
from privacytrace.main import create_app

HOST_TEXT = "当您使用位置查询时，我们会访问精确位置，用于显示当前位置。我们不会读取联系人。"
SDK_TEXT = "第三方位置服务可能处理位置信息，具体范围和条件未说明。"
app = create_app()
original_target = policy_fetch.public_target


def filming_target(url, timeout=15):
    if urlsplit(url).hostname == "policy.privacytrace.test":
        port = int(os.environ["PRIVACYTRACE_FILM_API_PORT"])
        return (
            urlsplit(url)._replace(netloc=f"127.0.0.1:{port}"),
            port,
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port)),
        )
    return original_target(url, timeout=timeout)


policy_fetch.public_target = filming_target


@app.get("/policy/host", response_class=HTMLResponse)
def host():
    return "<html><body><h1>受控宿主政策</h1><p>" + HOST_TEXT + "</p></body></html>"


@app.get("/policy/sdk", response_class=HTMLResponse)
def sdk():
    return "<html><body><h1>受控第三方政策</h1><p>" + SDK_TEXT + "</p></body></html>"
