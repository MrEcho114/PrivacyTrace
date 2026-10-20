"""Local, bounded probes for container liveness and readiness."""

import os
import sys
import urllib.error
import urllib.request


def probe(kind: str) -> int:
    if kind not in {"live", "ready"}:
        return 2
    try:
        port = int(os.environ.get("PT_API_PORT", "8000"))
        # Ignore proxy environment variables; probes never leave loopback.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{port}/_health/{kind}", timeout=3) as response:
            return 0 if response.status == 200 else 1
    except (OSError, urllib.error.URLError):
        return 1


def check_live() -> bool:
    return probe("live") == 0


def check_ready() -> bool:
    return probe("ready") == 0


if __name__ == "__main__":
    sys.exit(probe(sys.argv[1] if len(sys.argv) == 2 else ""))

