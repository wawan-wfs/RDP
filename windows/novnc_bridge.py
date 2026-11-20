"""Local-only noVNC HTTP/WebSocket bridge using aiohttp, no process server."""
import argparse
import asyncio
import contextlib
from pathlib import Path
from urllib.parse import urlsplit
from aiohttp import web

SLOTS = web.AppKey("slots", asyncio.Semaphore)


async def tunnel(req):
    # Reject cross-origin browser requests and missing Origin.
    try:
        origin = urlsplit(req.headers.get("Origin", ""))
    except ValueError:
        raise web.HTTPForbidden() from None
    if origin.scheme not in ("http", "https") or origin.netloc.lower() != req.host.lower():
        raise web.HTTPForbidden()
    slots = req.app[SLOTS]
    if slots.locked():
        raise web.HTTPServiceUnavailable()
    async with slots:
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", 5900), 3)
        except (TimeoutError, OSError):
            raise web.HTTPBadGateway() from None
        ws = web.WebSocketResponse(protocols=("binary",), heartbeat=20, max_msg_size=2**20)
        try:
            await ws.prepare(req)

            async def vnc_to_browser():
                while data := await reader.read(65536):
                    await ws.send_bytes(data)

            async def browser_to_vnc():
                async for msg in ws:
                    if msg.type == web.WSMsgType.BINARY:
                        writer.write(msg.data)
                        await writer.drain()
                    else:
                        break

            tasks = [asyncio.create_task(vnc_to_browser()), asyncio.create_task(browser_to_vnc())]
            try:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
        return ws


def make_app(directory):
    app = web.Application(client_max_size=2**20)
    app[SLOTS] = asyncio.Semaphore(4)
    app.router.add_get("/websockify", tunnel)
    app.router.add_static("/", directory, show_index=False, follow_symlinks=False)
    return app


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("webroot", type=Path)
    args = cli.parse_args()
    web.run_app(make_app(args.webroot), host="127.0.0.1", port=6081, access_log=None, print=None)
