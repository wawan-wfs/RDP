"""Read protocol version and advertised security types without authenticating."""
import argparse
import re
import socket


def exact(s, size):
    out = b""
    while len(out) < size:
        chunk = s.recv(size-len(out))
        if not chunk:
            raise OSError("Connection closed before completing RFB handshake")
        out += chunk
    return out


def probe(host, port, apple=False):
    with socket.create_connection((host, port), timeout=3) as s:
        banner = exact(s, 12)
        if not re.fullmatch(rb"RFB [0-9]{3}\.[0-9]{3}\n", banner):
            raise ValueError("Not an RFB server")
        if apple:
            # Only report the server banner for ARD; this is not permission verification.
            return banner.decode().strip(), []
        s.sendall(b"RFB 003.008\n")
        return banner.decode().strip(), list(exact(s, exact(s, 1)[0]))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("host"); p.add_argument("port", type=int); p.add_argument("--apple", action="store_true")
    a = p.parse_args()
    version, types = probe(a.host, a.port, a.apple)
    if not a.apple and (2 not in types or 1 in types):
        raise SystemExit("VNC must advertise password authentication without unauthenticated mode")
    print(f"{version}; security types={types}" if not a.apple else version)
