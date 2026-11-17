#!/usr/bin/env python3
"""TLS byte forwarding for Android's shell UID; no file or HTTP access."""
import ipaddress
import select
import socket
import socketserver
import sys
import threading

ALLOWED = ipaddress.ip_network(sys.argv[2])
SLOTS = threading.BoundedSemaphore(16)


class Proxy(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            if ipaddress.ip_address(self.client_address[0]) not in ALLOWED:
                return
            self.request.settimeout(30)
            with socket.create_connection(('127.0.0.1', 8443), timeout=5) as upstream:
                upstream.settimeout(30)
                while True:
                    ready, _, _ = select.select([self.request, upstream], [], [], 120)
                    if not ready:
                        return
                    for reader in ready:
                        data = reader.recv(65536)
                        if not data:
                            return
                        (upstream if reader is self.request else self.request).sendall(data)
        except (OSError, ValueError):
            pass


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def process_request(self, request, address):
        if not SLOTS.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except Exception:
            SLOTS.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            SLOTS.release()


if __name__ == '__main__':
    with Server((sys.argv[1], 8443), Proxy) as server:
        server.serve_forever()
