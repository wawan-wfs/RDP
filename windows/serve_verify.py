"""Verify an owned, private Tailscale Serve route before advertising noVNC.

The noVNC browser backend listens ONLY on 127.0.0.1:6081. A successful
`tailscale serve --bg` exit code does not prove the route is configured.
This helper validates the active Serve mapping, including absence of Funnel.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit


class ServeVerifyError(ValueError):
    pass


def _loopback_target(target: str, scheme: str) -> bool:
    try:
        parsed = urlsplit(target)
    except ValueError:
        return False
    return (parsed.scheme == scheme and parsed.hostname in ('127.0.0.1', 'localhost')
            and parsed.port == 6081 and parsed.path in ('', '/') and not parsed.username
            and not parsed.password and not parsed.query and not parsed.fragment)


def verify_serve(config: dict, mode: str, port: int, target: str, dns: str = '') -> str:
    if not isinstance(config, dict):
        raise ServeVerifyError('Tailscale Serve response is not a JSON object')
    if mode not in ('tcp', 'https') or port not in (6082, 443):
        raise ServeVerifyError('Unsupported private Serve mode or port')
    if (mode, port) not in (('tcp', 6082), ('https', 443)):
        raise ServeVerifyError('Mode and port do not match the configured noVNC transport')
    scheme = 'tcp' if mode == 'tcp' else 'http'
    if not _loopback_target(target, scheme):
        raise ServeVerifyError('Requested proxy target is not the local noVNC bridge')
    for value in (config.get('AllowFunnel') or {}).values():
        if value is True:
            raise ServeVerifyError('Public Tailscale Funnel must not be enabled')
    tcp = config.get('TCP') or {}
    if not isinstance(tcp, dict):
        raise ServeVerifyError('Invalid TCP map')
    record = tcp.get(str(port))
    if not isinstance(record, dict):
        raise ServeVerifyError(f'Tailscale Serve has no TCP listener on port {port}')
    if mode == 'tcp':
        # Serve emits TCPForward without its scheme on some client versions.
        forward = record.get('TCPForward')
        if not isinstance(forward, str):
            raise ServeVerifyError('Missing TCPForward mapping')
        proxy = forward if '://' in forward else 'tcp://' + forward
        if not _loopback_target(proxy, 'tcp'):
            raise ServeVerifyError('TCP forwarding does not target the private noVNC bridge')
        if record.get('HTTPS') or record.get('HTTP') or record.get('TerminateTLS'):
            raise ServeVerifyError('TCP forwarder has an unexpected HTTP/TLS mode')
        return 'Private TCP Serve 6082 -> loopback 6081 confirmed'
    if not re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)*\.ts\.net', dns):
        raise ServeVerifyError('Invalid or missing Tailscale MagicDNS hostname')
    if record.get('HTTPS') is not True:
        raise ServeVerifyError('Expected HTTPS Serve listener on port 443')
    web = config.get('Web') or {}
    if not isinstance(web, dict):
        raise ServeVerifyError('Invalid HTTPS Web map')
    host = web.get(f'{dns}:443')
    if not isinstance(host, dict):
        raise ServeVerifyError('MagicDNS hostname is not present in Serve Web map')
    handlers = host.get('Handlers') or {}
    if not isinstance(handlers, dict):
        raise ServeVerifyError('Invalid HTTPS handler map')
    root = handlers.get('/')
    if not isinstance(root, dict):
        raise ServeVerifyError('Missing HTTPS root proxy handler')
    proxy = root.get('Proxy', '')
    if not isinstance(proxy, str) or not _loopback_target(proxy, 'http'):
        raise ServeVerifyError('HTTPS proxy does not target the private noVNC bridge')
    return 'Private HTTPS Serve 443 -> loopback 6081 confirmed'


def check_cli(mode: str, port: int, target: str, dns: str, attempts: int = 4,
              interval: float = 1.0) -> str:
    last_error = 'No Serve config received'
    for attempt in range(1, attempts + 1):
        try:
            result = subprocess.run(['tailscale', 'serve', 'status', '--json'],
                                    capture_output=True, text=True, timeout=6, check=False)
            if result.returncode:
                raise ServeVerifyError(f'Tailscale Serve status exited {result.returncode}')
            config = json.loads(result.stdout)
            return verify_serve(config, mode, port, target, dns)
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, ServeVerifyError) as exc:
            last_error = str(exc) or type(exc).__name__
            print(f'[WFS/SERVE] Verification attempt {attempt}/{attempts}: {last_error}',
                  file=sys.stderr, flush=True)
            if attempt < attempts:
                time.sleep(interval)
    raise ServeVerifyError(f'Serve route not confirmed: {last_error}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('tcp', 'https'))
    parser.add_argument('port', type=int, choices=(443, 6082))
    parser.add_argument('target')
    parser.add_argument('dns', nargs='?', default='')
    args = parser.parse_args()
    message = check_cli(args.mode, args.port, args.target, args.dns)
    print(f'[WFS/SERVE] PASS: {message}', flush=True)


if __name__ == '__main__':
    try:
        main()
    except ServeVerifyError as error:
        print(f'[WFS/SERVE] FAIL: {error}', file=sys.stderr, flush=True)
        raise SystemExit(1)