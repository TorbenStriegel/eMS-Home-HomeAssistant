#!/usr/bin/env python3
"""Probe an ABL eMS Home and dump everything the integration sees.

Run this on any machine that can reach the device (e.g. the Home Assistant
host itself). It uses the same code paths as the integration – the WebSocket
client and the protobuf decoder are imported from ``custom_components/ems_home``
– so the output is exactly what Home Assistant would receive.

    python tools/probe_device.py --host 192.168.178.86 --password '***'
    python tools/probe_device.py --host 192.168.178.86 --password '***' --json report.json

No dependencies besides ``requests``.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import importlib
import json
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COMPONENT = REPO / "custom_components" / "ems_home"

# Load the component as a synthetic package so its relative imports work
# without pulling in Home Assistant (ems_home/__init__.py imports HA).
_pkg = types.ModuleType("ems_probe")
_pkg.__path__ = [str(COMPONENT)]
sys.modules["ems_probe"] = _pkg

ws_client = importlib.import_module("ems_probe.ws_client")
ws_proto = importlib.import_module("ems_probe.ws_proto")
smart_meter_ws = importlib.import_module("ems_probe.smart_meter_ws")
evse_ws = importlib.import_module("ems_probe.evse_ws")
ems_home_api = importlib.import_module("ems_probe.ems_home_api")


def hr(title: str) -> None:
    print(f"\n\033[1m── {title} " + "─" * max(0, 60 - len(title)) + "\033[0m")


async def collect(host: str, port: int, token: str, seconds: float) -> dict:
    """Connect both streams and record raw frames plus decoded values."""
    result: dict = {"smart_meter": {"frames": [], "readings": []}, "evse": {"frames": [], "readings": []}}

    def make_sm(store):
        def handle(reading):
            store["readings"].append(reading.as_dict() | {"extra": {hex(k): v for k, v in reading.extra.items()}})
        return handle

    def make_ev(store):
        def handle(reading):
            store["readings"].append(reading.as_dict() | {"extra": reading.extra})
        return handle

    def make_state(store):
        store["states"] = []
        return store["states"].append

    sm = smart_meter_ws.SmartMeterWebSocket(
        host, token, make_sm(result["smart_meter"]), port, on_state_change=make_state(result["smart_meter"])
    )
    ev = evse_ws.EVSEWebSocket(
        host, token, make_ev(result["evse"]), port, on_state_change=make_state(result["evse"])
    )

    # Record the raw payloads too, so a decoding failure can be diagnosed.
    # The decoder is looked up as a module global at call time, so patching it
    # here captures every frame (rebinding the method would not: the bound
    # reference was already stored on the client).
    for name, module, func_name in (
        ("smart_meter", smart_meter_ws, "decode_smart_meter_frame"),
        ("evse", evse_ws, "decode_evse_frame"),
    ):
        original = getattr(module, func_name)

        def wrapped(payload, _orig=original, _name=name):
            if len(result[_name]["frames"]) < 5:
                result[_name]["frames"].append(payload[:160].hex())
            return _orig(payload)

        setattr(module, func_name, wrapped)

    await sm.start()
    await ev.start()
    await asyncio.sleep(seconds)
    await sm.stop()
    await ev.stop()

    for name, client in (("smart_meter", sm), ("evse", ev)):
        stats = client.stats.as_dict()
        stats["connected"] = any(result[name].get("states") or [])
        result[name]["stats"] = stats
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe an ABL eMS Home")
    parser.add_argument("--host", required=True, help="IP address or hostname of the eMS Home")
    parser.add_argument("--port", type=int, default=80, help="HTTP port (443 enables https/wss)")
    parser.add_argument("--password", help="password from the rating plate (asked if omitted)")
    parser.add_argument("--seconds", type=float, default=12.0, help="how long to listen to the streams")
    parser.add_argument("--json", help="write the full report to this file")
    args = parser.parse_args()

    password = args.password or getpass.getpass("eMS Home password: ")
    report: dict = {
        "host": args.host,
        "port": args.port,
        "https": args.port == 443,
        "version": None,
        "http": {},
        "streams": {},
    }

    hr("HTTP API")
    client = ems_home_api.EMSHomeHTTP(
        args.host, password, port=args.port, use_https=(args.port == 443), verify_ssl=False
    )
    try:
        token_data = client.login()
        print(f"  login            : OK (expires in {token_data.get('expires_in')} s)")
    except Exception as exc:
        print(f"  login            : FAILED – {type(exc).__name__}: {exc}")
        print("\n  Passwort falsch oder Gerät nicht erreichbar. Abbruch.")
        return 1

    report["token_ok"] = True

    for label, getter in (
        ("device status", client.get_device_status),
        ("e-mobility", client.get_emobility_state),
        ("charge mode", client.get_charge_mode),
    ):
        try:
            value = getter()
            payload = value.__dict__ if hasattr(value, "__dict__") else str(value)
            report["http"][label] = payload
            print(f"  {label:16s} : OK – {json.dumps(payload, default=str)[:110]}")
        except Exception as exc:
            report["http"][label] = f"FAILED: {type(exc).__name__}: {exc}"
            print(f"  {label:16s} : FAILED – {type(exc).__name__}: {exc}")

    hr(f"Live streams ({args.seconds:.0f}s)")
    streams = asyncio.run(collect(args.host, args.port, client.token, args.seconds))
    report["streams"] = streams

    for name in ("smart_meter", "evse"):
        data = streams[name]
        stats = data["stats"]
        state = "connected" if stats["connected"] else "NEVER CONNECTED"
        print(
            f"  {name:12s} : {state}, {stats['frames_received']} frames, "
            f"{stats['undecodable_frames']} undecodable, {stats['reconnects']} reconnects"
        )
        if stats["last_error"]:
            print(f"  {'':12s}   last error: {stats['last_error']}")
        if data["frames"]:
            print(f"  {'':12s}   first frame: {data['frames'][0]}")
        if data["readings"]:
            print(f"  {'':12s}   decoded    : {json.dumps(data['readings'][0], default=str)[:300]}")
        elif stats["frames_received"]:
            print(f"  {'':12s}   !! frames arrived but none decoded – send this report")

    hr("Verdict")
    sm_ok = streams["smart_meter"]["stats"]["frames_received"] > 0
    sm_dec = bool(streams["smart_meter"]["readings"])
    ev_ok = bool(streams["evse"]["readings"])
    print(f"  smart meter stream delivers frames : {'YES' if sm_ok else 'NO'}")
    print(f"  smart meter frames decode          : {'YES' if sm_dec else 'NO'}")
    print(f"  wallbox stream decodes             : {'YES' if ev_ok else 'NO'}")
    if sm_ok and sm_dec:
        reading = streams["smart_meter"]["readings"][0]
        print(
            f"  → grid power {reading['power_total'] / 1000:.3f} kW, "
            f"L1 {reading['voltage_l1']:.1f} V / {reading['current_l1']:.2f} A, "
            f"import {reading['energy_total']:.1f} kWh"
        )

    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\n  report written to {args.json}")

    client.logout()
    return 0 if (sm_dec or ev_ok) else 2


if __name__ == "__main__":
    sys.exit(main())
