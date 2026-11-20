"""Fake RFB fixture for CI or a live local bridge smoke check on Windows."""
import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
import aiohttp
from aiohttp.test_utils import TestClient, TestServer
from novnc_bridge import make_app


async def live():
    url = "http://127.0.0.1:6081"
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as cli:
        async with cli.get(url + "/vnc.html") as resp:
            resp.raise_for_status()
        async with cli.ws_connect(url + "/websockify", origin=url, protocols=("binary",)) as ws:
            payload = bytearray()
            while len(payload) < 12:
                payload.extend(await asyncio.wait_for(ws.receive_bytes(), 4))
            assert payload.startswith(b"RFB ")


class TestBridge(unittest.IsolatedAsyncioTestCase):
    async def test_http_origin_and_transport(self):
        async def fake(reader, writer):
            writer.write(b"RFB 003.008\n")
            await writer.drain()
            assert await reader.readexactly(12) == b"RFB 003.008\n"
            writer.write(b"\x01\x02")
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        with tempfile.TemporaryDirectory() as t:
            Path(t, "vnc.html").write_text("fixture")
            async with await asyncio.start_server(fake, "127.0.0.1", 5900):
                async with TestClient(TestServer(make_app(t))) as client:
                    async with client.get("/vnc.html") as resp:
                        self.assertEqual(await resp.text(), "fixture")
                    with self.assertRaises(aiohttp.WSServerHandshakeError) as fail:
                        await client.ws_connect("/websockify", origin="https://foreign.example")
                    self.assertEqual(fail.exception.status, 403)
                    u = client.make_url("/")
                    async with client.ws_connect("/websockify", origin=f"{u.scheme}://{u.authority}", protocols=("binary",)) as ws:
                        self.assertEqual(await asyncio.wait_for(ws.receive_bytes(), 4), b"RFB 003.008\n")
                        await ws.send_bytes(b"RFB 003.008\n")
                        self.assertEqual(await asyncio.wait_for(ws.receive_bytes(), 4), b"\x01\x02")


if __name__ == "__main__":
    if "--live" in sys.argv:
        asyncio.run(live())
    else:
        unittest.main()
