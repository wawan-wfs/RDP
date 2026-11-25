"""Fixture tests; no real machine credentials or remote servers used."""
import socket
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import vnc_auth as auth


class AuthTests(unittest.TestCase):
    def test_known_registry_vector(self):
        # Published conventional VNC password-file test vector (synthetic).
        self.assertEqual(auth.registry_value('password').hex(), 'dbd83cfd727a1458')

    def test_bad_length_or_characters(self):
        for value in ('short', '123456789', 'abc!defg', 'abcdefgh\n'):
            with self.subTest(value=value), self.assertRaises(auth.AuthFailure):
                auth.password_bytes(value)

    def test_unowned_service_refused(self):
        # Supply a fake winreg import for platform-independent guard testing.
        with TemporaryDirectory() as directory, mock.patch.dict('sys.modules', {'winreg': mock.Mock()}):
            with self.assertRaisesRegex(auth.AuthFailure, 'not owned'):
                auth.configure_owned_service('password', directory)

    def fixture(self, password, methods=b'\x02'):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            listener.settimeout(5)
            errors = []
            def server():
                try:
                    with listener.accept()[0] as s:
                        s.settimeout(5)
                        s.sendall(b'RFB 003.008\n')
                        auth.exact(s,12)
                        s.sendall(bytes([len(methods)]) + methods)
                        if methods != b'\x02': return
                        self.assertEqual(auth.exact(s,1), b'\x02')
                        challenge = bytes(range(16))
                        s.sendall(challenge)
                        expected = auth.des_vnc(b'password', challenge)
                        s.sendall(b'\0\0\0\0' if auth.exact(s,16) == expected else b'\0\0\0\1')
                except Exception as exc:
                    errors.append(exc)
            worker = threading.Thread(target=server, daemon=True)
            worker.start()
            try:
                auth.authenticate(password, listener.getsockname()[1])
            finally:
                worker.join(6)
                self.assertFalse(worker.is_alive())
                self.assertFalse(errors, errors)

    def test_authentication_success(self):
        self.fixture('password')

    def test_wrong_password_rejected(self):
        with self.assertRaisesRegex(auth.AuthFailure, 'rejected'):
            self.fixture('wrongpwd')

    def test_unauthenticated_mode_rejected(self):
        with self.assertRaisesRegex(auth.AuthFailure, 'require password'):
            self.fixture('password', b'\x01\x02')


if __name__ == '__main__':
    unittest.main(verbosity=2)