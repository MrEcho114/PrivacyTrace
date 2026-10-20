"""Separate private mTLS material listener; never installed on the public API router."""

import os
from pathlib import Path

from .runtime_materials import RuntimeMaterials
from .runtime_tls import PrivateHandler, PrivateServer, RuntimeTLS


class MaterialHandler(PrivateHandler):
    def do_GET(self):
        try:
            if not self.authorized():
                self.reply(403, {"error": "RUNTIME_PEER_REJECTED"})
                return
            if self.path == "/v1/health":
                self.reply(200, {"version": 1, "status": "ready"})
                return
            if self.path not in {"/v1/material", "/v1/permit"}:
                self.reply(404, {"error": "UNKNOWN_RUNTIME_OPERATION"})
                return
            auth = self.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                raise PermissionError
            ticket = auth[7:]
            materials = self.server.materials
            row = materials.verify(ticket)
            if self.path == "/v1/permit":
                self.reply(200, {"version": 1, "permitted": True})
                return
            path = materials.path(row["path_key"], row["draft_id"])
            digest, size = materials.digest(path)
            if digest != row["sha256"] or size != row["byte_count"]:
                raise PermissionError
            with path.open("rb") as source:
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(size))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                chunks = 0
                while chunk := source.read(1024 * 1024):
                    if chunks % 8 == 0:
                        materials.verify(ticket)
                    self.wfile.write(chunk)
                    chunks += 1
            self.close_connection = True
        except PermissionError:
            if self.response_started:
                self.close_connection = True
            else:
                self.reply(410, {"error": "MATERIAL_UNAVAILABLE"})
        except (ValueError, OSError):
            if self.response_started:
                self.close_connection = True
            else:
                self.reply(503, {"error": "MATERIAL_GATEWAY_UNAVAILABLE"})


def create_gateway(store, address, tls, peers, materials=None):
    materials = materials or RuntimeMaterials.from_env(store)
    server = PrivateServer(address, MaterialHandler, tls, peers)
    server.materials = materials
    return server


def main():
    from .storage_factory import create_store

    store = server = None
    try:
        if os.environ.get("PRIVACYTRACE_STORAGE") != "postgres":
            raise ValueError
        store = create_store(Path(os.environ["PRIVACYTRACE_STORE_ROOT"]))
        server = create_gateway(
            store,
            (os.environ["PRIVACYTRACE_GATEWAY_BIND"], int(os.environ["PRIVACYTRACE_GATEWAY_PORT"])),
            RuntimeTLS.from_env("PRIVACYTRACE_GATEWAY_TLS"),
            os.environ["PRIVACYTRACE_GATEWAY_PEERS"].split(","),
        )
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        return 0
    except (KeyError, ValueError, OSError):
        print('{"error":"MATERIAL_GATEWAY_UNAVAILABLE"}')
        return 1
    finally:
        if server:
            server.server_close()
        if store:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
