"""Check review claims and keep documentation tied to the shipped behavior."""
from __future__ import annotations

import asyncio
import json
import re
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.ems_home.coordinator import EMSHomeCoordinator, EMSHomeData
from custom_components.ems_home.diagnostics import async_get_config_entry_diagnostics
from custom_components.ems_home.ws_client import METER_READ_TIMEOUT, StreamStats
from test_protocol import channel, decode_smart_meter_frame, gdr_frame

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components/ems_home"


def test_shipped_versions_match_manifest():
    version = json.loads((COMPONENT / "manifest.json").read_text())["version"]
    card = (COMPONENT / "frontend/ems-home-card.js").read_text()
    readme = (ROOT / "README.md").read_text()
    assert re.search(r'const VERSION = "([^"]+)"', card).group(1) == version
    assert f"version-{version}-blue.svg" in readme


def test_readme_matches_meter_timeout():
    readme = (ROOT / "README.md").read_text()
    assert f"silent for {METER_READ_TIMEOUT:g} s" in readme


@pytest.mark.parametrize("claim", ["cadence", "finish", "pv_cost"])
def test_readme_debug_cadence_and_finish_conditions(claim):
    readme = (ROOT / "README.md").read_text()
    if claim == "cadence":
        assert "on every third poll that succeeds" in readme
    elif claim == "finish":
        event_row = next(line for line in readme.splitlines() if line.startswith("| `ems_home_charging_finished`"))
        assert "still plugged in" in event_row
    else:
        assert "prices grid energy and, when configured, the PV share" in readme


@pytest.mark.parametrize("language", ["strings", "de", "en"])
def test_translated_debug_cadence_matches_poll_counter(language):
    path = COMPONENT / ("strings.json" if language == "strings" else f"translations/{language}.json")
    description = json.loads(path.read_text())["options"]["step"]["init"]["data_description"]["debug_logging"]
    assert ("jeder dritten Abfrage" if language == "de" else "on every third poll that succeeds") in description


def test_readme_entity_examples_use_translated_names():
    readme = (ROOT / "README.md").read_text()
    for language in ("en", "de"):
        strings = json.loads((COMPONENT / f"translations/{language}.json").read_text())
        for key in ("evse_session_energy", "evse_session_energy_grid", "evse_session_energy_pv", "evse_session_cost", "evse_session_saved"):
            name = strings["entity"]["sensor"][key]["name"]
            slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
            assert f"sensor.<device>_{slug}" in readme


@pytest.mark.parametrize("language", ["strings", "de", "en"])
def test_connection_options_have_descriptions(language):
    path = COMPONENT / ("strings.json" if language == "strings" else f"translations/{language}.json")
    descriptions = json.loads(path.read_text())["options"]["step"]["init"]["data_description"]
    for key in ("scan_interval", "timeout", "enable_smart_meter_stream", "enable_evse_stream"):
        assert descriptions.get(key), key


@pytest.mark.parametrize("enabled", [False, True])
def test_diagnostics_preserve_documented_stream_details(enabled):
    c = object.__new__(EMSHomeCoordinator)
    c.client = SimpleNamespace(host="local-test", port=80, uses_https=False)
    c.update_interval = timedelta(seconds=20)
    c._poll_count = 7
    c.data = None
    stats = StreamStats("smart_meter", frames=12, bytes_received=100, undecodable_frames=3,
                        reconnects=2, last_error="test error")
    c.smart_meter_ws = SimpleNamespace(stats=stats) if enabled else None
    c.evse_ws = None
    entry = SimpleNamespace(entry_id="test", title="Test", version=1,
                            data={"password": "dummy-test-secret"}, options={})
    hass = SimpleNamespace(data={"ems_home": {"test": {"coordinator": c}}})
    output = asyncio.run(async_get_config_entry_diagnostics(hass, entry))
    assert "dummy-test-secret" not in json.dumps(output)
    streams = output["connection"]["streams"]
    if not enabled:
        assert streams == {}
        return
    assert streams["smart_meter"]["frames"] == 12  # existing public alias is preserved
    assert streams["smart_meter"]["age"] is None
    assert streams["smart_meter"]["undecodable_frames"] == 3
    assert streams["smart_meter"]["last_error"] == "test error"
    assert streams["smart_meter"]["bytes_received"] == 100


def test_m4_register_three_is_not_always_zero_and_four_is_unknown():
    reading = decode_smart_meter_frame(gdr_frame({channel(3, 4): 123000, channel(4, 4): 708000}))
    assert reading.reactive_power == 123
    assert reading.extra[channel(4, 4)] == 708000
    print("M4 synthetic frame: reactive_power=123.0; register 4 retained as extra=708000")


def test_m5_net_savings_match_documented_formula():
    data = object.__new__(EMSHomeData)
    data.evse = None
    data.tracked_session_energy_wh = 10000
    data.tracked_session_grid_wh = 4000
    data.tracked_session_seconds = 60
    data.grid_price = 0.35
    data.pv_price = 0.10
    assert data.session_cost == 2.0
    assert data.session_saved == 1.5
    print("M5: 10 kWh, 4 grid + 6 PV, tariffs 0.35/0.10: cost=2.0; net saved=1.5 (gross=2.1)")
