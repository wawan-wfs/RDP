"""No-network regression tests for the fail-fast noVNC/RFB probe."""
import base64
import hashlib
import unittest
from unittest import mock

import novnc_probe as mod

KEY = b'abcdefghijklmnop'
KEYENC = base64.b64encode(KEY)
ACCEPT = base64.b64encode(hashlib.sha1(KEYENC + mod.MAGIC).digest())

class FakeSocket:
    def __init__(self, data):
        self.data = bytearray(data)
        self.sent = b''
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def settimeout(self, *_): pass
    def sendall(self, data): self.sent = data
    def recv(self, size):
        if not self.data: return b''
        # Small chunks verify fragmented upgrade headers & WS frame handling.
        n = min(size, 7)
        out, self.data = self.data[:n], self.data[n:]
        return bytes(out)

class TestNoVncProbe(unittest.TestCase):
    @staticmethod
    def response(frame=b'\x82\x0cRFB 003.008\n', accept=ACCEPT, status=b'HTTP/1.1 101 Switching Protocols'):
        return status + b'\r\nUpgrade: websocket\r\nSec-WebSocket-Accept: ' + accept + b'\r\n\r\n' + frame

    def test_valid_websocket_and_rfb(self):
        conn = FakeSocket(self.response())
        with mock.patch.object(mod.socket, 'create_connection', return_value=conn):
            self.assertEqual(mod.websocket_rfb_probe(keybytes=KEY), b'RFB 003.008\n')
        self.assertIn(b'GET /websockify HTTP/1.1', conn.sent)
        self.assertIn(b'Origin: http://127.0.0.1:6081', conn.sent)

    def test_non_101_rejected(self):
        with mock.patch.object(mod.socket, 'create_connection', return_value=FakeSocket(self.response(status=b'HTTP/1.1 403 Forbidden'))):
            with self.assertRaisesRegex(mod.ProbeFailure, 'rejected'):
                mod.websocket_rfb_probe(keybytes=KEY)

    def test_invalid_accept_rejected(self):
        with mock.patch.object(mod.socket, 'create_connection', return_value=FakeSocket(self.response(accept=b'wrong'))):
            with self.assertRaisesRegex(mod.ProbeFailure, 'Accept mismatch'):
                mod.websocket_rfb_probe(keybytes=KEY)

    def test_missing_rfb_banner_rejected(self):
        with mock.patch.object(mod.socket, 'create_connection', return_value=FakeSocket(self.response(frame=b'\x82\x0cnonsensexxxx'))):
            with self.assertRaisesRegex(mod.ProbeFailure, 'RFB banner missing'):
                mod.websocket_rfb_probe(keybytes=KEY)

    def test_truncated_frame_rejected(self):
        with mock.patch.object(mod.socket, 'create_connection', return_value=FakeSocket(self.response(frame=b'\x82\x0cRFB'))):
            with self.assertRaisesRegex(mod.ProbeFailure, 'closed'):
                mod.websocket_rfb_probe(keybytes=KEY)

    def test_missing_server_response_rejected(self):
        with mock.patch.object(mod.socket, 'create_connection', return_value=FakeSocket(b'')):
            with self.assertRaisesRegex(mod.ProbeFailure, 'closed during upgrade'):
                mod.websocket_rfb_probe(keybytes=KEY)

if __name__ == '__main__':
    unittest.main(verbosity=2)