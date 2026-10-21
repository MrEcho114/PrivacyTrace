#!/usr/bin/env python3
"""Controlled OpenAI-compatible extractor used by the PT129 acceptance lab.

It is deliberately deterministic: it returns only claims whose excerpt is a
verbatim substring of the untrusted policy text in the request. This exercises
the product's existing server-side extraction path without claiming any
external model quality.
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OPEN = "<untrusted_policy_text>"
CLOSE = "</untrusted_policy_text>"
LOG = "/tmp/pt129-llm-requests.jsonl"

CLAIMS = [
    {
        "excerpt": "会在您授权后访问位置信息",
        "data_type": "LOCATION",
        "polarity": "AFFIRMATIVE",
        "condition": "用户授权",
        "subject": "HOST_APP",
        "action": "ACCESS",
        "declared_purpose": "提供本地测试服务",
        "declared_recipient": None,
    },
    {
        "excerpt": "会读取通讯录",
        "data_type": "CONTACTS",
        "polarity": "AFFIRMATIVE",
        "condition": None,
        "subject": "HOST_APP",
        "action": "ACCESS",
        "declared_purpose": "联系人权限验证",
        "declared_recipient": None,
    },
]


def policy_text(user_prompt):
    if OPEN in user_prompt:
        body = user_prompt.split(OPEN, 1)[1]
        return body.split(CLOSE, 1)[0]
    return user_prompt


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""
        try:
            request = json.loads(raw.decode("utf-8"))
        except Exception:
            request = {}
        messages = request.get("messages") or []
        user = messages[-1].get("content", "") if messages else ""
        text = policy_text(user)
        items = [dict(claim) for claim in CLAIMS if claim["excerpt"] in text]
        with open(LOG, "a", encoding="utf-8") as stream:
            stream.write(json.dumps({
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "model": request.get("model"),
                "text_chars": len(text),
                "claims": len(items),
            }, ensure_ascii=False) + "\n")
        content = json.dumps(items, ensure_ascii=False)
        body = json.dumps({
            "id": "chatcmpl-pt129-controlled",
            "object": "chat.completion",
            "created": 0,
            "model": request.get("model", "controlled-extractor"),
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 16, "completion_tokens": 8, "total_tokens": 24},
        }, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 19545), Handler).serve_forever()
