"""Private, authenticated, read-only, user-initiated macOS screenshot preview."""
from base64 import b64encode
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time

PNG_HEADER = b"\x89PNG\r\n\x1a\n"
MAX_SIZE = 16 * 1024 * 1024
PAGE = b"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport"
content="width=device-width,initial-scale=1"><title>WFS macOS Preview</title>
<style>body{font:16px system-ui,sans-serif;background:#11172a;color:#e8edf8;
margin:auto;padding:2rem;max-width:1100px}img{max-width:100%;margin-top:1rem}
button{border:0;border-radius:7px;padding:.7rem 1rem;color:white;background:#5a48db}</style>
<h1>WFS macOS Preview</h1><p>Read-only screenshot. This page cannot send mouse or keyboard input.
Capture requires an authorized macOS GUI session and Screen Recording permission.</p>
<button id="take">Capture one frame</button><p aria-live="polite" id="status"></p><img id="frame" alt="Captured macOS desktop" hidden>
<script src="/app.js"></script></html>"""
JS = b"""const button=document.querySelector('#take'), image=document.querySelector('#frame'), status=document.querySelector('#status');
let prior; button.addEventListener('click',async()=>{
button.disabled=true; status.textContent='Requesting one frame...';
try { const r=await fetch('/frame',{cache:'no-store'});
if(!r.ok){throw Error(await r.text());} const obj=URL.createObjectURL(await r.blob());
if(prior) URL.revokeObjectURL(prior); prior=obj; image.src=obj; image.hidden=false;
status.textContent=r.headers.get('X-WFS-Frame')==='cached'?'Cached frame (60 second cooldown)':'Captured one frame';
}catch(e){status.textContent=e.message;}finally{button.disabled=false;}
});"""


class Preview:
    def __init__(self, grab, cooldown=60, clock=time.monotonic):
        self.grab = grab
        self.cooldown = cooldown
        self.clock = clock
        self.lock = threading.Lock()
        self.attempt = None
        self.data = None

    def frame(self):
        if not self.lock.acquire(blocking=False):
            return 429, b"Capture is already running", False
        try:
            now = self.clock()
            if self.attempt is not None and now - self.attempt < self.cooldown:
                return (200, self.data, True) if self.data else (429, b"Capture cooldown. Retry after 60 seconds.", False)
            self.attempt, self.data = now, None
            try:
                data = self.grab()
                if not data.startswith(PNG_HEADER) or len(data) > MAX_SIZE:
                    raise ValueError("Invalid screenshot")
            except (OSError, ValueError, subprocess.SubprocessError):
                return 503, b"No authorized GUI capture. Check console session and Screen Recording approval.", False
            self.data = data
            return 200, data, False
        finally:
            self.lock.release()


def capture():
    uid = os.getuid()
    if uid < 501 or os.stat("/dev/console").st_uid != uid:
        raise OSError("No current authorized console user")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp, "frame.png")
        subprocess.run(["/usr/sbin/screencapture", "-x", "-t", "png", str(path)],
                       timeout=12, check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if path.stat().st_size > MAX_SIZE:
            raise ValueError("Frame too large")
        return path.read_bytes()


class Server(ThreadingHTTPServer):
    daemon_threads = True
    def get_request(self):
        con, addr = super().get_request()
        con.settimeout(15)
        return con, addr


def create_server(username, password, grab=capture, port=6081):
    token = b"Basic " + b64encode(f"{username}:{password}".encode("utf-8"))
    preview = Preview(grab)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, code, body, content="text/plain", headers=()):
            self.send_response(code)
            self.send_header("Content-Type", content)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'self'; connect-src 'self'; img-src blob:; frame-ancestors 'none'")
            for a, b in headers:
                self.send_header(a, b)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_GET(self):
            supplied = self.headers.get("Authorization", "").encode("utf-8")
            if not hmac.compare_digest(supplied, token):
                return self.reply(401, b"Authentication required", headers=(("WWW-Authenticate", 'Basic realm="WFS macOS Preview", charset="UTF-8"'),))
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                return self.reply(403, b"Cross-site request denied")
            if self.path == "/":
                return self.reply(200, PAGE, "text/html; charset=utf-8")
            if self.path == "/health":
                return self.reply(200, b"ready")
            if self.path == "/app.js":
                return self.reply(200, JS, "text/javascript")
            if self.path == "/frame":
                code, data, cached = preview.frame()
                return self.reply(code, data, "image/png" if code == 200 else "text/plain",
                                  (("X-WFS-Frame", "cached" if cached else "new"),))
            return self.reply(404, b"Not found")

        def do_POST(self):
            return self.reply(405, b"This preview is read-only")
        do_PUT = do_PATCH = do_DELETE = do_POST

    return Server(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    with create_server(os.environ.pop("WFS_PREVIEW_USER"), os.environ.pop("WFS_PREVIEW_PASSWORD")) as server:
        server.serve_forever()
