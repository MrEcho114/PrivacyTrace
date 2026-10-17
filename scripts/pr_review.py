#!/usr/bin/env python3
"""Post an advisory review comment on a pull request using a chat-completions model.

The model sees only the PR diff plus this repository's review rubric
(docs/agents/review-rubric.md); it never sees policy text, APK contents or any
other artifact the repository forbids shipping. Its output is a *comment*, never
a blocking review: the merge decision stays with a human reviewer (AGENTS.md).

Environment
  GITHUB_TOKEN        token with pull-requests:write (the workflow's default token)
  PR_NUMBER           pull request number
  REVIEW_API_KEY      model API key; when absent the step is a documented no-op
  REVIEW_API_BASE     OpenAI-compatible base URL (default https://api.openai.com/v1)
  REVIEW_MODEL        model name (default gpt-4o-mini)
  REVIEW_MAX_CHARS    diff budget in characters (default 60000)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"
MARKER = "<!-- privacytrace-model-review: {sha} -->"
MAX_FILES = 300


def github(path: str, method: str = "GET", payload: dict | None = None) -> object:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "privacytrace-model-review",
            **({"Content-Type": "application/json"} if data else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read()
    return json.loads(body) if body else None


def collect_diff(repo: str, number: str, budget: int) -> tuple[str, int]:
    chunks: list[str] = []
    used = 0
    page = 1
    files = 0
    while page <= 3:
        batch = github(f"/repos/{repo}/pulls/{number}/files?per_page=100&page={page}")
        if not isinstance(batch, list) or not batch:
            break
        for item in batch:
            files += 1
            if files > MAX_FILES:
                break
            patch = item.get("patch")
            if not patch:
                chunks.append(f"=== {item['filename']} ({item['status']}, {item['changes']} changes, content not shown) ===")
                continue
            block = f"=== {item['filename']} ({item['status']}, {item['changes']} changes) ===\n{patch}\n"
            if used + len(block) > budget:
                chunks.append(f"=== diff truncated at {used} characters; {MAX_FILES} file budget reached ===")
                return "\n".join(chunks), files
            chunks.append(block)
            used += len(block)
        if len(batch) < 100:
            break
        page += 1
    return "\n".join(chunks), files


def call_model(rubric: str, diff: str) -> str:
    base = os.environ.get("REVIEW_API_BASE", "https://api.openai.com/v1").rstrip("/")
    payload = {
        "model": os.environ.get("REVIEW_MODEL", "gpt-4o-mini"),
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": rubric},
            {
                "role": "user",
                "content": (
                    "Review this pull request diff. Follow the rubric exactly: group findings by "
                    "severity, cite file and line, quote the diff line that proves each finding, "
                    "and state plainly what you could not verify. Do not restate the diff.\n\n"
                    f"{diff}"
                ),
            },
        ],
    }
    request = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {os.environ['REVIEW_API_KEY']}",
            "Content-Type": "application/json",
            "User-Agent": "privacytrace-model-review",
        },
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        body = json.loads(response.read())
    return body["choices"][0]["message"]["content"].strip()


def already_reviewed(repo: str, number: str, marker: str) -> bool:
    comments = github(f"/repos/{repo}/issues/{number}/comments?per_page=100")
    return isinstance(comments, list) and any(marker in (c.get("body") or "") for c in comments)


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN")
    number = os.environ.get("PR_NUMBER")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not (token and number and repo):
        print("model review: GITHUB_TOKEN, PR_NUMBER and GITHUB_REPOSITORY are required", file=sys.stderr)
        return 2

    if not os.environ.get("REVIEW_API_KEY"):
        print("model review: skipped - set the REVIEW_API_KEY repository secret to enable it")
        return 0

    rubric_path = Path("docs/agents/review-rubric.md")
    if not rubric_path.is_file():
        print(f"model review: rubric missing at {rubric_path}", file=sys.stderr)
        return 2

    head = github(f"/repos/{repo}/pulls/{number}")
    sha = str(head["head"]["sha"])[:12]
    marker = MARKER.format(sha=sha)
    if already_reviewed(repo, number, marker):
        print(f"model review: already commented on {sha}; nothing to do")
        return 0

    budget = int(os.environ.get("REVIEW_MAX_CHARS", "60000"))
    diff, files = collect_diff(repo, number, budget)
    if not diff.strip():
        print("model review: empty diff; nothing to review")
        return 0

    try:
        text = call_model(rubric_path.read_text(encoding="utf-8"), diff)
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:400].decode("utf-8", "replace")
        print(f"model review: model endpoint returned {exc.code}: {detail}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, KeyError, json.JSONDecodeError) as exc:
        print(f"model review: model call failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    body = (
        f"{marker}\n"
        f"### 模型辅助审查（{files} 个文件，advisory）\n\n"
        f"{text}\n\n"
        "---\n"
        "这是自动化建议，不是决定：请人工复核每条发现，确认后再采信或忽略。"
        "确定性检查见 `scripts/review_gates.py`，判断类问题才交给本步骤。\n"
    )
    github(f"/repos/{repo}/issues/{number}/comments", "POST", {"body": body})
    print(f"model review: posted comment on {sha} ({len(body)} chars, {files} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
