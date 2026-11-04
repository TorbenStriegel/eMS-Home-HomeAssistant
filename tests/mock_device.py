"""A mock ABL eMS Home device for end-to-end testing.

Implements the subset of the local API the integration uses – including the two
protobuf WebSocket streams – so the whole integration can be exercised without
real hardware.

    python tests/mock_device.py --port 8099
"""
from __future__ import annotations

import argparse
import asyncio
import struct
import sys
import time
from pathlib import Path

from aiohttp import web

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "ems_home"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_protocol import channel, gdr_frame  # noqa: E402

PASSWORD = "geheim"
ACCESS_TOKEN = "mock-access-token"

STATE = {"mode": "pv", "min_pv": 60, "min_charge": 0, "ev_power_w": 3_466_000}


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------

async def token(request: web.Request) -> web.Response:
    form = await request.post()
    if form.get("password") != PASSWORD or form.get("grant_type") != "password":
        raise web.HTTPUnauthorized(text='{"error":"invalid_grant"}')
    return web.json_response({"access_token": ACCESS_TOKEN, "expires_in": 604800, "token_type": "bearer"})


async def device_status(request: web.Request) -> web.Response:
    return web.json_response(
        {
            "status": "idle",
            "CpuLoad": 17,
            "CpuTemp": 43,
            "RamFree": 41_000,
            "RamTotal": 65_536,
            "FlashAppFree": 1_000_000,
            "FlashAppTotal": 4_000_000,
            "FlashDataFree": 250_000,
            "FlashDataTotal": 500_000,
        }
    )


async def emobility_state(request: web.Request) -> web.Response:
    return web.json_response(
        {
            "EvChargingPower": {"total": STATE["ev_power_w"], "l1": 1_155_000, "l2": 1_155_000, "l3": 1_155_000},
            "CurtailmentSetpoint": {"total": 0, "l1": 0, "l2": 0, "l3": 0},
            "OverloadProtectionActive": False,
        }
    )


async def charge_mode(request: web.Request) -> web.Response:
    if request.method == "PUT":
        body = await request.json()
        STATE["mode"] = body.get("mode", STATE["mode"])
        if body.get("minpvpowerquota") is not None:
            STATE["min_pv"] = body["minpvpowerquota"]
        if body.get("mincharginpowerquota") is not None:
            STATE["min_charge"] = body["mincharginpowerquota"]
    return web.json_response(
        {
            "mode": STATE["mode"],
            "mincharginpowerquota": STATE["min_charge"],
            "minpvpowerquota": STATE["min_pv"],
            "lastminchargingpowerquota": STATE["min_charge"],
            "lastminpvpowerquota": STATE["min_pv"],
        }
    )


# ---------------------------------------------------------------------------
# WebSocket streams
# ---------------------------------------------------------------------------

async def _serve_stream(request: web.Request, frame_builder, interval: float) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)

    # the firmware expects "Bearer <token>" as the first text frame
    auth = await ws.receive(timeout=10)
    if auth.type != web.WSMsgType.TEXT or not auth.data.startswith("Bearer "):
        await ws.close(code=1008, message=b"auth expected")
        return ws

    push = asyncio.create_task(_push(ws, frame_builder, interval))
    try:
        async for _msg in ws:
            pass
    finally:
        push.cancel()
    return ws


async def _push(ws: web.WebSocketResponse, frame_builder, interval: float) -> None:
    started = time.time()
    while not ws.closed:
        try:
            await ws.send_bytes(frame_builder(started))
        except (ConnectionResetError, RuntimeError):
            return
        await asyncio.sleep(interval)


async def smart_meter_ws(request: web.Request) -> web.WebSocketResponse:
    def build(_started: float) -> bytes:
        elapsed = time.time() % 60
        return gdr_frame(
            {
                channel(1, 4): int((1200 + elapsed * 10) * 1000),   # grid import in mW
                channel(21, 4): int(400 * 1000),
                channel(32, 4): 230_400,
                channel(31, 4): 5_400,
                channel(14, 4): 50_010,
                channel(1, 8): 4_821_300_000,
                channel(2, 8): 2_914_800_000,
            }
        )

    return await _serve_stream(request, build, 1.0)


async def evse_ws(request: web.Request) -> web.WebSocketResponse:
    def build(started: float) -> bytes:
        duration = int(time.time() - started) + 2_850
        return gdr_frame(
            {},
            {
                "evse_status": ("int", 4),
                "evse_status_code": ("str", "C1"),
                "evse_error_code": ("str", "E0"),
                "evse_serial": ("str", "EMH1-MOCK"),
                "evse_hw_imax": ("int", 32_000),
                "ev_imax_default": ("int", 16_000),
                "evse_session_duration": ("int", duration),
                "evse_session_energy": ("int", 12_400_000),
            },
        )

    return await _serve_stream(request, build, 1.0)


# ---------------------------------------------------------------------------

def make_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/api/web-login/token", token)
    app.router.add_get("/api/device-settings/devicestatus", device_status)
    app.router.add_get("/api/e-mobility/state", emobility_state)
    app.router.add_get("/api/e-mobility/config/chargemode", charge_mode)
    app.router.add_put("/api/e-mobility/config/chargemode", charge_mode)
    app.router.add_get(
        "/api/data-transfer/ws/protobuf/gdr/local/values/smart-meter", smart_meter_ws
    )
    app.router.add_get("/api/data-transfer/ws/protobuf/gdr/local/values/{evse}/evse", evse_ws)
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8099)
    args = parser.parse_args()
    web.run_app(make_app(), host="127.0.0.1", port=args.port, print=None)
