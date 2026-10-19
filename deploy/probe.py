"""Local, bounded probes. Readiness deliberately fails until #80 integration."""

import sys
import urllib.error
import urllib.request


def probe(kind):
    if kind not in {"live", "ready"}:
        return 2
    try:
        # Ignore proxy environment variables; probes never leave loopback.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:8000/_health/{kind}", timeout=3) as response:
            return 0 if response.status == 200 else 1
    except (OSError, urllib.error.URLError):
        return 1


if __name__ == "__main__":
    sys.exit(probe(sys.argv[1] if len(sys.argv) == 2 else ""))
