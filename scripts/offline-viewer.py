"""Dependency-free, read-only localhost viewer. Run from the exported package only."""

import argparse
import hashlib
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


def verify(root):
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    actual = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    if actual != set(manifest["files"]) | {"manifest.json"}:
        raise ValueError("Offline package file set differs from manifest")
    for name, hashed in manifest["files"].items():
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Unsafe package path")
        if hashlib.sha256(path.read_bytes()).hexdigest() != hashed:
            raise ValueError("Offline package hash mismatch")


def serve(root, port):
    verify(root)
    reports = json.loads((root / "reports.json").read_text(encoding="utf-8"))
    taxonomy = json.loads((root / "taxonomy.json").read_text(encoding="utf-8"))

    class Viewer(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root / "web"), **kwargs)

        def do_POST(self):
            self.send_error(405, "Offline replay is read-only")

        def do_GET(self):
            path = unquote(urlsplit(self.path).path)
            payload = None
            if path == "/api/v1/jobs":
                payload = {"jobs": [report["job"] for report in reports.values()]}
            elif path == "/api/v1/taxonomy":
                payload = taxonomy
            elif path == "/api/v1/health":
                payload = {"status": "ok", "mode": "OFFLINE_REPLAY"}
            elif path.startswith("/api/v1/jobs/"):
                parts = path.split("/")
                report = reports.get(parts[4]) if len(parts) in {5, 6} else None
                if report and (len(parts) == 5 or parts[5] == "report"):
                    payload = report["job"] if len(parts) == 5 else report
            if payload is not None:
                data = json.dumps(payload, ensure_ascii=True).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
            elif path.startswith("/api/"):
                self.send_error(404, "Replay has no such saved report")
            else:
                super().do_GET()

        def list_directory(self, path):
            self.send_error(404, "Directory listing disabled")

    server = ThreadingHTTPServer(("127.0.0.1", port), Viewer)
    print(f"OFFLINE REPLAY: http://127.0.0.1:{server.server_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    serve(Path(__file__).resolve().parent, args.port)
