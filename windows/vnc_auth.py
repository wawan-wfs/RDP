"""Configure and verify the newly owned TightVNC service's session credential.

No password or registry credential is printed or passed on a process command line.
Use only for the workflow's newly installed, loopback-only service.
"""
from __future__ import annotations
import argparse
import os
import re
import socket
import sys
from pathlib import Path
from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
from cryptography.hazmat.primitives.ciphers import Cipher, modes


class AuthFailure(RuntimeError):
    pass


def reverse_bits(value):
    return int(f'{value:08b}'[::-1], 2)


def des_vnc(key, payload):
    # VNC's DES implementation uses reversed key bit order. Repeating the
    # same DES key three times is equivalent to single DES in ECB mode.
    des_key = bytes(map(reverse_bits, key))
    encryptor = Cipher(TripleDES(des_key * 3), modes.ECB()).encryptor()
    return encryptor.update(payload) + encryptor.finalize()


def password_bytes(password):
    if not re.fullmatch(r'[A-Za-z0-9_-]{8}', password):
        raise AuthFailure('Expected exactly eight compatible VNC characters')
    return password.encode('ascii')


def registry_value(password):
    return des_vnc(bytes((23,82,107,6,35,78,88,7)), password_bytes(password))


def configure_owned_service(password, state):
    import winreg
    if not (Path(state) / 'vnc-owned').is_file():
        raise AuthFailure('Refusing to configure a service not owned by this run')
    # Open only the existing service key; never inspect or recover other
    # credentials. The service must be stopped by the caller before writing.
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\TightVNC\Server', 0,
                        winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as key:
        winreg.SetValueEx(key, 'Password', 0, winreg.REG_BINARY, registry_value(password))
        for name in ('UseVncAuthentication', 'AllowLoopback', 'LoopbackOnly'):
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 1)


def exact(sock, count):
    result = bytearray()
    while len(result) < count:
        part = sock.recv(count - len(result))
        if not part:
            raise AuthFailure('VNC closed before authentication completed')
        result.extend(part)
    return bytes(result)


def authenticate(password, port=5900):
    key = password_bytes(password)
    with socket.create_connection(('127.0.0.1', port), timeout=4) as sock:
        sock.settimeout(4)
        banner = exact(sock, 12)
        if banner not in (b'RFB 003.008\n', b'RFB 003.007\n'):
            raise AuthFailure('Unsupported RFB version for authentication probe')
        sock.sendall(banner)
        count = exact(sock, 1)[0]
        methods = exact(sock, count)
        if 2 not in methods or 1 in methods:
            raise AuthFailure('VNC must require password authentication')
        sock.sendall(b'\x02')
        challenge = exact(sock, 16)
        sock.sendall(des_vnc(key, challenge))
        if exact(sock, 4) != b'\0\0\0\0':
            raise AuthFailure('TightVNC rejected the configured session password')
        # Authentication succeeded. Do not enter a desktop session.


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('configure', 'verify'))
    args = parser.parse_args()
    from shared.workspace import read_config, derive
    password = derive(read_config(), 'web', os.environ.get('VNC_PASSWORD', ''))
    if args.action == 'configure':
        configure_owned_service(password, os.environ['WFS_STATE'])
        print('[WFS/noVNC] Owned TightVNC service password configured (hidden)', flush=True)
    else:
        authenticate(password)
        print('[WFS/noVNC] PASS: actual session password accepted by TightVNC', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (AuthFailure, OSError, ValueError, KeyError) as exc:
        # Do not include raw registry/process exceptions or secret values.
        print('[WFS/noVNC] FAIL: ' + (str(exc) if isinstance(exc, AuthFailure) else type(exc).__name__), file=sys.stderr)
        raise SystemExit(1)