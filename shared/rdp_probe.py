"""Read a minimal X.224/RDP negotiation. This does not try to log in."""
import argparse
import socket
import struct

REQUEST = b"\x03\x00\x00\x13\x0e\xe0\x00\x00\x00\x00\x00\x01\x00\x08\x00\x03\x00\x00\x00"


def read_exact(sock, count):
    data = bytearray()
    while len(data) < count:
        block = sock.recv(count-len(data))
        if not block:
            raise OSError("Incomplete TPKT")
        data.extend(block)
    return bytes(data)


def probe(host, port, require_nla=False):
    with socket.create_connection((host, port), timeout=3) as s:
        s.sendall(REQUEST)
        head = read_exact(s, 4)
        version, reserved, length = struct.unpack("!BBH", head)
        if version != 3 or reserved or not 11 <= length <= 1024:
            raise ValueError("Invalid TPKT")
        body = read_exact(s, length-4)
        if body[1] != 0xd0:
            raise ValueError("X.224 connection confirmation expected")
        if len(body) >= 15:
            kind, _, size, protocol = struct.unpack("<BBHI", body[7:15])
            if kind != 2 or size != 8:
                raise ValueError("RDP protocol negotiation failed")
            if require_nla and protocol not in (2, 8):
                raise ValueError("NLA not negotiated")
            return protocol
        if require_nla:
            raise ValueError("NLA negotiation result missing")
        return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("host"); p.add_argument("port", type=int); p.add_argument("--nla", action="store_true")
    a = p.parse_args()
    print("X.224/RDP negotiation protocol:", probe(a.host, a.port, a.nla))
