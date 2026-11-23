"""Fail-fast local HTTP + WebSocket/RFB check for the noVNC bridge.

Uses only the stdlib. A prior aiohttp client probe could hang during WebSocket
shutdown on Windows even though its read timeouts had elapsed. This probe owns
one socket and relies on bounded recv timeouts plus the PowerShell process cap.
"""
from __future__ import annotations

import base64
import hashlib
import http.client
import os
import re
import socket
import sys
import time

HOST = "127.0.0.1"
PORT = 6081
MAGIC = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class ProbeFailure(RuntimeError):
    """Remote endpoint did not pass an end-to-end local smoke check."""


def probe_html(host=HOST, port=PORT, timeout=4):
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request("GET", "/vnc.html", headers={"Connection": "close"})
        response = connection.getresponse()
        if response.status != 200:
            raise ProbeFailure(f"noVNC HTML returned HTTP {response.status}")
        content = response.read(256)
        if not content or b"html" not in content.lower():
            raise ProbeFailure("noVNC HTML response was empty or invalid")
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        raise ProbeFailure(f"noVNC HTML request failed: {type(exc).__name__}") from exc
    finally:
        connection.close()


class BufferedSocket:
    def __init__(self, sock, initial=b"" ):
        self.sock = sock
        self.pending = bytearray(initial)

    def read_exact(self, n):
        while len(self.pending) < n:
            chunk = self.sock.recv(max(n-len(self.pending), 1))
            if not chunk:
                raise ProbeFailure("RFB WebSocket closed before sending expected data")
            self.pending.extend(chunk)
        result = bytes(self.pending[:n])
        del self.pending[:n]
        return result


def websocket_rfb_probe(host=HOST, port=PORT, timeout=4, keybytes=None):
    keybytes = os.urandom(16) if keybytes is None else keybytes
    if len(keybytes) != 16:
        raise ValueError("WebSocket key must have 16 random bytes")
    key = base64.b64encode(keybytes).decode("ascii")
    authority = f"{host}:{port}"
    request = (f"GET /websockify HTTP/1.1\r\n"
               f"Host: {authority}\r\n"
               "Upgrade: websocket\r\n"
               "Connection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\n"
               "Sec-WebSocket-Version: 13\r\n"
               "Sec-WebSocket-Protocol: binary\r\n"
               f"Origin: http://{authority}\r\n\r\n").encode("ascii")
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(request)
            response = bytearray()
            while b"\r\n\r\n" not in response:
                if len(response) > 16384:
                    raise ProbeFailure("WebSocket response headers too large")
                data = sock.recv(4096)
                if not data:
                    raise ProbeFailure("WebSocket server closed during upgrade")
                response.extend(data)
            head, payload = bytes(response).split(b"\r\n\r\n", 1)
            lines = head.split(b"\r\n")
            if not lines[0].startswith(b"HTTP/1.1 101 ") and lines[0] != b"HTTP/1.1 101":
                raise ProbeFailure(f"WebSocket upgrade rejected: {lines[0].decode('ascii','replace')}")
            headers = {}
            for line in lines[1:]:
                if b":" in line:
                    k, v = line.split(b":", 1)
                    headers[k.strip().lower()] = v.strip()
            expected = base64.b64encode(hashlib.sha1(key.encode("ascii") + MAGIC).digest())
            if headers.get(b"sec-websocket-accept") != expected:
                raise ProbeFailure("WebSocket Sec-WebSocket-Accept mismatch")
            if b"websocket" not in headers.get(b"upgrade", b"").lower():
                raise ProbeFailure("Upgrade response lacks websocket protocol")
            reader = BufferedSocket(sock, payload)
            h = reader.read_exact(2)
            op = h[0] & 0x0F
            if op != 2 or h[0] & 0x80 == 0:
                raise ProbeFailure(f"First WebSocket frame not complete binary payload (opcode {op})")
            masked = h[1] & 0x80
            size = h[1] & 0x7F
            if masked:
                raise ProbeFailure("Server-sent WebSocket frame must not be masked")
            if size == 126:
                size = int.from_bytes(reader.read_exact(2), "big")
            elif size == 127:
                size = int.from_bytes(reader.read_exact(8), "big")
            if not 12 <= size <= 8192:
                raise ProbeFailure(f"Unexpected RFB banner frame size: {size}")
            banner = reader.read_exact(size)
            if not re.match(rb"^RFB [0-9]{3}\.[0-9]{3}\n", banner):
                raise ProbeFailure("WebSocket connected but TightVNC RFB banner missing")
            return banner[:12]
    except (OSError, TimeoutError) as exc:
        raise ProbeFailure(f"WebSocket/RFB timed out or was unreachable: {type(exc).__name__}") from exc


def main():
    start = time.monotonic()
    print("[WFS/noVNC] Probe 1/2: HTTP frontend", flush=True)
    probe_html()
    print("[WFS/noVNC] Probe 2/2: WebSocket upgrade + RFB banner", flush=True)
    banner = websocket_rfb_probe()
    print(f"[WFS/noVNC] PASS: HTTP 200, WebSocket 101, TightVNC {banner.decode('ascii').strip()} in {time.monotonic()-start:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProbeFailure as exc:
        print(f"[WFS/noVNC] FAIL: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)