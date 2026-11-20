"""Fail closed if Webtop is reachable without authentication."""
import base64
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

uri, user = sys.argv[1:]
if uri != "https://127.0.0.1:13001/":
    raise SystemExit("Expected local Webtop probe address")
ctx = ssl._create_unverified_context()  # Only the pinned loopback IP; Webtop ships a self-signed cert.
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx))
for _ in range(30):
    try:
        with opener.open(uri, timeout=2) as resp:
            if resp.status < 400:
                raise SystemExit("Webtop refused: unauthenticated request succeeded")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            auth = base64.b64encode((user+":"+os.environ["PASSWORD"]).encode()).decode()
            try:
                req = urllib.request.Request(uri, headers={"Authorization": "Basic "+auth})
                with opener.open(req, timeout=3) as resp:
                    if resp.status == 200:
                        print("Webtop: unauthenticated 401, authenticated 200")
                        sys.exit(0)
            except (OSError, urllib.error.URLError):
                pass
    except (OSError, urllib.error.URLError):
        pass
    time.sleep(2)
raise SystemExit("Webtop did not pass local HTTPS/auth readiness")
