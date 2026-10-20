"""Bounded TCP passthrough to one private Runner; TLS terminates at the Runner.

Run on the control host's internal Docker bridge address. Host firewall rules
must separately deny control containers access to other host services.
"""

import argparse
import ipaddress
import selectors
import socket
import socketserver
import threading
import time


def private_address(value):
    address = ipaddress.IPv4Address(value)
    if not address.is_private or address.is_unspecified or address.is_multicast:
        raise ValueError("a fixed private IPv4 address is required")
    return str(address)


class Relay(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, listen, allowed, target):
        self.allowed = ipaddress.IPv4Network(allowed)
        self.target = (private_address(target), 8444)
        self.slots = threading.BoundedSemaphore(8)
        super().__init__((private_address(listen), 8444), Connection)

    def verify_request(self, request, client_address):
        return ipaddress.IPv4Address(client_address[0]) in self.allowed

    def handle_error(self, request, client_address):
        # Addresses, request bytes and authentication material never enter logs.
        pass


class Connection(socketserver.BaseRequestHandler):
    def handle(self):
        if not self.server.slots.acquire(blocking=False):
            return
        try:
            with socket.create_connection(self.server.target, timeout=3) as upstream:
                upstream.settimeout(5)
                self.request.settimeout(5)
                with selectors.DefaultSelector() as selector:
                    selector.register(self.request, selectors.EVENT_READ, upstream)
                    selector.register(upstream, selectors.EVENT_READ, self.request)
                    deadline = time.monotonic() + 300
                    while time.monotonic() < deadline:
                        for key, _ in selector.select(timeout=1):
                            chunk = key.fileobj.recv(65536)
                            if not chunk:
                                return
                            key.data.sendall(chunk)
        except (OSError, TimeoutError):
            return
        finally:
            self.server.slots.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen", required=True)
    parser.add_argument("--allow", required=True, help="Docker control subnet CIDR")
    parser.add_argument("--target", required=True, help="Dedicated Runner private IPv4")
    args = parser.parse_args()
    with Relay(args.listen, args.allow, args.target) as server:
        server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()
