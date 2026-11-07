"""The per-cycle session energy the coordinator integrates itself.

The firmware reports session energy only on some versions (on the tested device
it stays at 0), so the coordinator integrates the reported charging power and
starts over when a new cycle begins.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.ems_home.coordinator import EMSHomeCoordinator  # noqa: E402
from custom_components.ems_home.ws_proto import EVSEReading  # noqa: E402


def coordinator() -> EMSHomeCoordinator:
    obj = object.__new__(EMSHomeCoordinator)
    obj._session_energy_wh = 0.0
    obj._session_grid_wh = 0.0
    obj._session_seconds = 0.0
    obj._session_prev = None
    obj._energy_last_ts = None
    obj._latest_smart_meter = None
    obj.grid_price = 0.0
    obj.pv_price = 0.0
    obj._last_session = {}
    obj._session_ended = False
    obj._charge_since = None
    obj.notify_enabled = False
    obj.notify_on_start = False
    obj.notify_on_finish = True
    obj.notify_service = None
    obj.notify_vehicle_entity = None
    obj._gate_energy_wh = 0.0
    obj._gate_grid_wh = 0.0
    obj._gate_seconds = 0.0
    obj._integrated_state_id = None
    return obj


def end_cycle(c):
    """The end is debounced: three samples in a row must say "car gone, no flow"."""
    for _ in range(c.UNPLUG_CONFIRM_SAMPLES):
        c._accumulate_session_energy(state(0.0))


def meter(power_kw: float):
    return SimpleNamespace(power_total=int(power_kw * 1000))


def reading(duration: int, status: int) -> EVSEReading:
    return EVSEReading(uuid="wb-1", evse_status=status, session_duration=duration)


def state(power_kw: float):
    return SimpleNamespace(ev_charging_power=SimpleNamespace(total=int(power_kw * 1_000_000)))


CHARGING = 4
SUSPENDED = 12
AVAILABLE = 1


def test_accumulates_while_charging():
    c = coordinator()
    c._energy_last_ts = time.monotonic() - 10  # ten seconds ago
    c._accumulate_session_energy(state(3.6))
    # 3.6 kW for 10 s = 10 Wh
    assert 9.5 < c._session_energy_wh < 10.5


def test_no_accumulation_without_power():
    c = coordinator()
    c._session_energy_wh = 1234.0
    c._energy_last_ts = time.monotonic() - 10
    c._accumulate_session_energy(state(0))
    assert c._session_energy_wh == 1234.0


def test_long_gap_is_not_counted():
    """After a restart the gap is huge – counting it would invent energy."""
    c = coordinator()
    c._energy_last_ts = time.monotonic() - 3600
    c._accumulate_session_energy(state(11))
    assert c._session_energy_wh == 0.0


def test_counter_jump_is_not_a_new_cycle():
    """A reconnect delivers a reset counter – wiping the figures would be wrong."""
    c = coordinator()
    c._session_energy_wh = 8421.0
    c._track_session_cycle(reading(3000, CHARGING))
    c._track_session_cycle(reading(5, CHARGING))     # counter restarted after a drop
    assert c._session_energy_wh == 8421.0


def test_unplugging_keeps_the_figures_until_the_next_charge():
    """People read the values after the car is gone – they must not vanish."""
    c = coordinator()
    c._session_energy_wh = 500.0
    c._session_grid_wh = 200.0
    c._track_session_cycle(reading(600, CHARGING))
    c._track_session_cycle(reading(600, AVAILABLE))   # car removed …
    c._energy_last_ts = time.monotonic() - 5
    end_cycle(c)                                      # … and nothing flows

    assert c._session_energy_wh == 500.0, "the finished cycle stays visible"
    assert c._session_ended is True
    assert c._last_session["energy_kwh"] == 0.5

    # plugging in alone does not reset anything
    c._track_session_cycle(reading(610, CHARGING))
    assert c._session_energy_wh == 500.0


def test_charging_again_starts_a_fresh_cycle():
    c = coordinator()
    c._session_energy_wh = 500.0
    c._session_ended = True
    c._charge_since = time.monotonic() - 300   # already above the gate for 5 min
    c._accumulate_session_energy(state(3.6))
    assert c._session_energy_wh == 0.0, "a new charge starts from zero"


def test_a_short_blip_is_ignored():
    """The wallbox reports 0,11–0,27 kW now and then – that is not a charge."""
    c = coordinator()
    c._session_energy_wh = 500.0
    c._session_ended = True
    c._accumulate_session_energy(state(0.11))
    assert c._session_energy_wh == 500.0, "the finished session stays"
    assert c._session_ended is True
    assert c._charge_since is None


def test_a_charge_below_the_power_gate_does_not_start_a_cycle():
    c = coordinator()
    c._session_energy_wh = 500.0
    c._session_ended = True
    for _ in range(10):
        c._accumulate_session_energy(state(0.9))   # below MIN_CYCLE_POWER_KW
    assert c._session_energy_wh == 500.0


def test_a_charge_that_is_too_short_does_not_start_a_cycle():
    c = coordinator()
    c._session_energy_wh = 500.0
    c._session_ended = True
    c._charge_since = time.monotonic() - 30    # only 30 s above the gate
    c._accumulate_session_energy(state(1.2))
    assert c._session_energy_wh == 500.0, "not long enough to count"
    assert c._session_ended is True


def test_paused_session_keeps_the_counter():
    """Status 12 (paused) must not look like a new cycle."""
    c = coordinator()
    c._session_energy_wh = 700.0
    c._track_session_cycle(reading(600, CHARGING))
    c._track_session_cycle(reading(700, SUSPENDED))
    assert c._session_energy_wh == 700.0


def test_all_energy_counts_as_grid_when_the_meter_imports_that_much():
    c = coordinator()
    c._latest_smart_meter = meter(5.0)          # house + car import 5 kW
    c._energy_last_ts = time.monotonic() - 10
    c._accumulate_session_energy(state(3.6))
    assert abs(c._session_energy_wh - c._session_grid_wh) < 0.1


def test_pv_share_when_the_meter_imports_less_than_the_car_draws():
    c = coordinator()
    c._latest_smart_meter = meter(1.8)          # 1.8 kW from the grid
    c._energy_last_ts = time.monotonic() - 10
    c._accumulate_session_energy(state(3.6))
    assert 9.5 < c._session_energy_wh < 10.5
    assert 4.7 < c._session_grid_wh < 5.3       # 1.8 kW * 10 s
    assert c._session_energy_wh - c._session_grid_wh > 4.5   # the rest is PV


def test_export_never_counts_as_grid_energy():
    c = coordinator()
    c._latest_smart_meter = meter(-4.0)         # feeding in, so nothing from the grid
    c._energy_last_ts = time.monotonic() - 10
    c._accumulate_session_energy(state(3.6))
    assert c._session_grid_wh == 0.0


def test_grid_share_resets_with_the_cycle():
    c = coordinator()
    c._session_energy_wh = 8000.0
    c._session_grid_wh = 4000.0
    c._session_ended = True
    c._charge_since = time.monotonic() - 300
    c._accumulate_session_energy(state(3.5))
    assert c._session_grid_wh == 0.0 and c._session_energy_wh == 0.0


def test_cost_and_saving_from_the_tariffs():
    from custom_components.ems_home.coordinator import EMSHomeData

    data = EMSHomeData(
        device_status=None,
        emobility_state=None,
        charge_mode=None,
        tracked_session_energy_wh=12400,
        tracked_session_grid_wh=5100,
        grid_price=0.32,
        pv_price=0.0,
    )
    assert data.session_energy_kwh == 12.4
    assert data.session_grid_kwh == 5.1
    assert data.session_pv_kwh == 7.3
    assert data.session_cost == 1.632           # 5.1 kWh * 0.32
    assert data.session_saved == 2.336          # 7.3 kWh * 0.32


def test_no_cost_without_a_tariff():
    from custom_components.ems_home.coordinator import EMSHomeData

    data = EMSHomeData(device_status=None, emobility_state=None, charge_mode=None,
                       tracked_session_energy_wh=12400, tracked_session_grid_wh=5100)
    assert data.session_cost is None
    assert data.session_saved is None


def test_finished_cycle_is_remembered():
    c = coordinator()
    c.grid_price = 0.30
    c._session_energy_wh = 10000.0
    c._session_grid_wh = 4000.0
    c._session_seconds = 3000.0     # 50 min actually charging

    c._track_session_cycle(reading(3000, CHARGING))
    c._track_session_cycle(reading(3100, AVAILABLE))   # car unplugged
    c._energy_last_ts = time.monotonic() - 5
    end_cycle(c)                                       # and idle → cycle ends

    last = c._last_session
    assert last["energy_kwh"] == 10.0
    assert last["energy_grid_kwh"] == 4.0
    assert last["energy_pv_kwh"] == 6.0
    assert last["duration_min"] == 50.0, "our charging time, not the plugged time"
    assert last["cost"] == 1.2                      # 4 kWh * 0.30
    assert last["ended_at"]


def test_default_tariff_keeps_the_cost_sensor_numeric():
    """Without a configured tariff the sensor showed 'unknown' – it must not."""
    from custom_components.ems_home.const import DEFAULT_GRID_PRICE
    from custom_components.ems_home.coordinator import EMSHomeData

    assert DEFAULT_GRID_PRICE > 0
    data = EMSHomeData(device_status=None, emobility_state=None, charge_mode=None,
                       tracked_session_energy_wh=10000, tracked_session_grid_wh=4000,
                       grid_price=DEFAULT_GRID_PRICE)
    assert data.session_cost == round(4.0 * DEFAULT_GRID_PRICE, 3)
    assert data.session_saved == round(6.0 * DEFAULT_GRID_PRICE, 3)


class FakeStore:
    """Minimal stand-in for homeassistant.helpers.storage.Store."""

    def __init__(self, data=None):
        self._data = data
        self.saved = None

    async def async_load(self):
        return self._data

    def async_delay_save(self, data_func, delay):  # noqa: ARG002
        self.saved = data_func()


def test_cycle_survives_a_restart():
    import asyncio

    c = object.__new__(EMSHomeCoordinator)
    c._store = FakeStore({"energy_wh": 12400.0, "grid_wh": 5100.0,
                          "prev": {"duration": 600, "plugged": True},
                          "last_session": {"energy_kwh": 9.0}})
    asyncio.run(c.async_load_session())
    assert c._session_energy_wh == 12400.0
    assert c._session_grid_wh == 5100.0
    assert c._session_prev["duration"] == 600
    assert c._last_session["energy_kwh"] == 9.0


def test_cycle_is_written_to_the_store():
    c = coordinator()
    c._store = FakeStore()
    c._session_energy_wh = 500.0
    c._session_grid_wh = 200.0
    c._persist_session()
    assert c._store.saved["energy_wh"] == 500.0
    assert c._store.saved["grid_wh"] == 200.0


def test_unset_option_falls_back_to_the_default_tariff():
    """An unsaved option must not leave the cost sensors at 'unknown'."""
    from custom_components.ems_home import _price_option
    from custom_components.ems_home.const import DEFAULT_GRID_PRICE

    assert _price_option({}, "grid_price", DEFAULT_GRID_PRICE) == DEFAULT_GRID_PRICE
    assert _price_option({"grid_price": 0.42}, "grid_price", DEFAULT_GRID_PRICE) == 0.42
    assert _price_option({"grid_price": 0}, "grid_price", DEFAULT_GRID_PRICE) == 0.0
    assert _price_option({"grid_price": "abc"}, "grid_price", DEFAULT_GRID_PRICE) == DEFAULT_GRID_PRICE


class _State:
    def __init__(self, value, unit):
        self.state = str(value)
        self.attributes = {"unit_of_measurement": unit}


class _States:
    def __init__(self, mapping):
        self._mapping = mapping

    def get(self, entity_id):
        return self._mapping.get(entity_id)


class _Hass:
    def __init__(self, mapping):
        self.states = _States(mapping)


def with_sensors(pv=None, battery=None):
    mapping = {}
    if pv is not None:
        mapping["sensor.pv"] = _State(pv, "kW")
    if battery is not None:
        mapping["sensor.battery"] = _State(battery, "kW")
    c = coordinator()
    c.hass = _Hass(mapping)
    c.pv_power_entity = "sensor.pv" if pv is not None else None
    c.battery_power_entity = "sensor.battery" if battery is not None else None
    return c


def test_pv_sensor_reduces_the_grid_share():
    c = with_sensors(pv=2.0)
    assert c._grid_share_kw(3.5) == 1.5


def test_battery_discharge_counts_as_own_generation():
    c = with_sensors(pv=1.0, battery=1.5)
    assert c._self_supply_kw() == 2.5
    assert c._grid_share_kw(3.5) == 1.0


def test_charging_battery_does_not_count():
    c = with_sensors(pv=1.0, battery=-2.0)   # battery is being charged
    assert c._self_supply_kw() == 1.0
    assert c._grid_share_kw(3.5) == 2.5


def test_enough_pv_means_no_grid_share():
    c = with_sensors(pv=9.0)
    assert c._grid_share_kw(3.5) == 0.0


def test_watt_sensors_are_normalised():
    c = coordinator()
    c.hass = _Hass({"sensor.pv_w": _State(4200, "W"), "sensor.pv_kw": _State(4.2, "kW")})
    c.pv_power_entity = "sensor.pv_w"
    c.battery_power_entity = None
    assert c._self_supply_kw() == 4.2
    c.pv_power_entity = "sensor.pv_kw"
    assert c._self_supply_kw() == 4.2
    c.pv_power_entity = "sensor.missing"
    assert c._self_supply_kw() is None


def test_meter_caps_the_computed_share():
    c = with_sensors(pv=0.5)
    c._latest_smart_meter = meter(1.0)   # only 1 kW import
    assert c._grid_share_kw(3.5) == 1.0


def test_without_sensors_the_meter_is_used():
    c = coordinator()
    c._latest_smart_meter = meter(1.8)
    assert c._grid_share_kw(3.5) == 1.8


def test_duration_counts_charging_time_only():
    """Plugged time is not charging time – a 3 h plug-in with 10 min of charge is 10."""
    c = coordinator()
    c._session_ended = False
    c._energy_last_ts = time.monotonic() - 10
    c._accumulate_session_energy(state(3.5))
    assert 9.5 < c._session_seconds < 10.5

    # a pause adds nothing to the duration
    c._energy_last_ts = time.monotonic() - 10
    c._accumulate_session_energy(state(0.0))
    assert 9.5 < c._session_seconds < 10.5


def test_a_single_failed_poll_keeps_the_entities_available():
    """The device stalls now and then – one missed poll must not blank everything."""
    import asyncio

    c = object.__new__(EMSHomeCoordinator)
    c._failed_polls = 0
    c._poll_count = 0
    c.update_interval = __import__("datetime").timedelta(seconds=10)
    previous = object()
    c.data = previous
    c.hass = None

    def boom():
        raise RuntimeError("read timed out")

    c._fetch_all = boom
    c.hass = __import__("types").SimpleNamespace(async_add_executor_job=lambda fn: _await(fn))
    assert asyncio.run(c._async_update_data()) is previous
    assert c._failed_polls == 1


async def _await(fn):
    return fn()


def test_a_control_command_retries_once_after_a_connect_timeout():
    """The device stalls now and then – the second attempt usually gets through."""
    import requests
    from custom_components.ems_home.ems_home_api import EMSHomeHTTP

    client = EMSHomeHTTP("127.0.0.1", "pw", port=80)
    calls = {"n": 0}

    class Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {}

    class Sess:
        headers: dict = {}

        def put(self, url, timeout=None, **kwargs):  # noqa: ARG002
            calls["n"] += 1
            if calls["n"] == 1:
                raise requests.exceptions.ConnectTimeout("connect timeout")
            return Resp()

        def close(self):
            return None

    client._session = Sess()
    client._is_token_valid = lambda: True
    assert client._put("/api/x").status_code == 200
    assert calls["n"] == 2, "the first attempt failed, the retry succeeded"


def test_a_status_flap_during_a_charge_does_not_end_the_cycle():
    """The wallbox sometimes reports 'available' for one frame – keep charging."""
    c = coordinator()
    c._session_energy_wh = 4000.0
    c._session_ended = False
    c._plugged = False          # one frame says the car is gone …
    c._energy_last_ts = time.monotonic() - 10
    c._accumulate_session_energy(state(3.5))   # … but it is drawing 3,5 kW

    assert c._session_ended is False
    assert c._session_energy_wh > 4000.0, "the charge keeps counting"


def test_the_cycle_ends_when_the_car_is_gone_and_nothing_flows():
    c = coordinator()
    c._session_energy_wh = 4000.0
    c._session_seconds = 1800.0
    c._session_ended = False
    c._plugged = False
    c._energy_last_ts = time.monotonic() - 10
    end_cycle(c)

    assert c._session_ended is True
    assert c._last_session["energy_kwh"] == 4.0
    assert c._session_energy_wh == 4000.0, "the figures stay visible"


def test_sensors_show_the_last_session_when_the_cycle_is_empty():
    """'Ladekosten letzter Ladevorgang' must not read 0,00 € after a restart."""
    from custom_components.ems_home.coordinator import EMSHomeData

    data = EMSHomeData(
        device_status=None, emobility_state=None, charge_mode=None,
        grid_price=0.35,
        last_session={
            "energy_kwh": 12.4, "energy_grid_kwh": 5.1, "energy_pv_kwh": 7.3,
            "duration_min": 48.0, "cost": 1.785,
        },
    )
    assert data.session_energy_kwh == 12.4
    assert data.session_grid_kwh == 5.1
    assert data.session_pv_kwh == 7.3
    assert data.session_charge_minutes == 48.0
    assert data.session_cost == 1.785


def test_the_running_cycle_wins_over_the_last_one():
    from custom_components.ems_home.coordinator import EMSHomeData

    data = EMSHomeData(
        device_status=None, emobility_state=None, charge_mode=None,
        grid_price=0.35,
        tracked_session_energy_wh=2000.0, tracked_session_grid_wh=2000.0,
        tracked_session_seconds=600.0,
        last_session={"energy_kwh": 12.4, "energy_grid_kwh": 5.1, "cost": 1.785},
    )
    assert data.session_energy_kwh == 2.0
    assert data.session_cost == round(2.0 * 0.35, 3)
