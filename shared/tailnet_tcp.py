"""Linux-only fallback for private TCP ports when Tailscale Serve is unavailable."""
import asyncio
import contextlib
import ipaddress
import socket
import sys
from pathlib import Path

NET = ipaddress.ip_network("100.64.0.0/10")


def check_params(ip, port, backend):
    addr = ipaddress.ip_address(ip)
    if addr not in NET or (port, backend) not in {(3389, 13389), (6082, 13001)}:
        raise ValueError("Only known WFS endpoints bound to tailnet IPv4 are accepted")


async def main(ip, port, backend, pidfile):
    check_params(ip, port, backend)
    ls = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ls.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, b"tailscale0\x00")
    ls.bind((ip, port))
    ls.listen(32)
    ls.setblocking(False)
    cap = asyncio.Semaphore(12)

    async def forward(up, uw):
        dw = None
        control = []
        try:
            peer = ipaddress.ip_address(uw.get_extra_info("peername")[0])
            if peer not in NET or cap.locked():
                return
            async with cap:
                down, dw = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", backend), 3)
                async def copy(r, w):
                    while data := await r.read(65536):
                        w.write(data)
                        await w.drain()
                    with contextlib.suppress(OSError, RuntimeError, AttributeError):
                        w.write_eof()
                control = [asyncio.create_task(copy(up, dw)), asyncio.create_task(copy(down, uw))]
                await asyncio.gather(*control)
        except (OSError, TimeoutError):
            pass
        finally:
            for t in control:
                t.cancel()
            if control:
                await asyncio.gather(*control, return_exceptions=True)
            uw.close()
            if dw:
                dw.close()

    server = await asyncio.start_server(forward, sock=ls)
    async with server:
        import os
        Path(pidfile).write_text(str(os.getpid()))
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]))
