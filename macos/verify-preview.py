from base64 import b64encode
from http.client import HTTPConnection
import os

def status(headers):
    c = HTTPConnection('127.0.0.1', 6081, timeout=3)
    try:
        c.request('GET', '/health', headers=headers)
        return c.getresponse().status
    finally:
        c.close()

u, p = os.environ['WFS_PREVIEW_USER'], os.environ['WFS_PREVIEW_PASSWORD']
auth = b64encode(f'{u}:{p}'.encode()).decode()
if status({}) != 401 or status({'Authorization': 'Basic ' + auth}) != 200:
    raise SystemExit('Preview authentication probe rejected')
