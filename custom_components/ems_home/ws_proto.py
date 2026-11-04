"""Protobuf decoding for the eMS Home GDR streams.

The device streams ``smartmeter.GDRs`` messages (see ``smart_meter.proto``)::

    message FlexValue { string type = 1; string value = 2; }
    message GDR {
      string id = 1;
      Status status = 2;
      google.protobuf.Timestamp timestamp = 3;
      map<uint64, uint64> values = 4;
      map<string, FlexValue> flexValues = 5;
    }
    message GDRs { map<string, GDR> GDRs = 1; string configUuid = 2; }

Every numeric value is a fixed-point integer in *milli* units of its base unit
(mW, mV, mA, mHz, mWh, ...), so it is divided by 1000 to get the base unit.

The ``values`` keys are packed OBIS identifiers: 8 bytes laid out as
``00 00 | media | channel | measurement | type | 00 | 0xFF``.  Only the
measurement byte and the type byte are needed to identify a register, which is
why the lookup table below is keyed by ``(measurement, type)``.  Anything that is
not in the table is still surfaced (``SmartMeterReading.extra``) instead of being
dropped silently – that makes new firmware registers visible in diagnostics.
"""
from __future__ import annotations

import logging
import struct
from dataclasses import dataclass, field
from typing import Optional, Union

_LOGGER = logging.getLogger(__name__)

WT_VARINT = 0
WT_64BIT = 1
WT_LENGTH = 2
WT_32BIT = 5

#: Types: 4 = instantaneous value, 8 = cumulative energy counter.
TYPE_INSTANT = 0x04
TYPE_ENERGY = 0x08


# ---------------------------------------------------------------------------
# Generic protobuf reader
# ---------------------------------------------------------------------------

def decode_varint(data: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if pos >= len(data):
            raise ValueError("truncated varint")
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7
        if shift > 70:
            raise ValueError("varint too long")


def decode_fields(data: bytes) -> list[tuple[int, int, Union[int, bytes]]]:
    """Decode one protobuf message into ``(field_number, wire_type, value)``."""
    fields: list[tuple[int, int, Union[int, bytes]]] = []
    pos = 0
    while pos < len(data):
        tag, pos = decode_varint(data, pos)
        field_no, wire_type = tag >> 3, tag & 0x07
        if field_no == 0:
            raise ValueError("invalid field number 0")
        if wire_type == WT_VARINT:
            value, pos = decode_varint(data, pos)
            fields.append((field_no, wire_type, value))
        elif wire_type == WT_LENGTH:
            length, pos = decode_varint(data, pos)
            if pos + length > len(data):
                raise ValueError("truncated length-delimited field")
            fields.append((field_no, wire_type, data[pos:pos + length]))
            pos += length
        elif wire_type == WT_32BIT:
            if pos + 4 > len(data):
                raise ValueError("truncated 32-bit field")
            fields.append((field_no, wire_type, struct.unpack_from("<I", data, pos)[0]))
            pos += 4
        elif wire_type == WT_64BIT:
            if pos + 8 > len(data):
                raise ValueError("truncated 64-bit field")
            fields.append((field_no, wire_type, struct.unpack_from("<Q", data, pos)[0]))
            pos += 8
        else:
            raise ValueError(f"unsupported wire type {wire_type}")
    return fields


def _first(fields, number, wire=None):
    for fn, wt, value in fields:
        if fn == number and (wire is None or wt == wire):
            return value
    return None


def _varint(fields, number: int) -> int | None:
    """First varint value of ``number``, if any."""
    value = _first(fields, number, WT_VARINT)
    return value if isinstance(value, int) else None


def _blob(fields, number: int) -> bytes | None:
    """First length-delimited value of ``number``, if any."""
    value = _first(fields, number, WT_LENGTH)
    return value if isinstance(value, (bytes, bytearray)) else None


def _text(value) -> str:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", "replace").strip("\x00").strip()
    return str(value)


def parse_timestamp(raw: bytes) -> float:
    """``google.protobuf.Timestamp`` -> unix seconds."""
    fields = decode_fields(raw)
    seconds = _varint(fields, 1) or 0
    nanos = _varint(fields, 2) or 0
    return float(seconds) + float(nanos) / 1e9


def obis_label(channel_id: int) -> str:
    """Render a packed channel id as OBIS string, e.g. ``1-0:21.4.0*255``."""
    raw = channel_id.to_bytes(8, "big")[-6:]
    media, channel, measurement, vtype, tariff, storage = raw
    unit = {TYPE_INSTANT: "W/V/A/var", TYPE_ENERGY: "Wh/varh"}.get(vtype, "?")
    return (
        f"{media}-{channel}:{measurement}.{vtype}.{tariff}*{storage} "
        f"({unit})"
    )


def unpack_channel(channel_id: int) -> tuple[int, int]:
    """Return ``(measurement, type)`` of a packed OBIS channel id."""
    raw = channel_id.to_bytes(8, "big")[-6:]
    return raw[2], raw[3]


# ---------------------------------------------------------------------------
# Channel table
# ---------------------------------------------------------------------------

#: ``(measurement, type) -> (attribute, divisor)``
CHANNELS: dict[tuple[int, int], tuple[str, float]] = {
    # instantaneous (type 4) – milli watts / volts / amps / hertz / var
    (1, TYPE_INSTANT): ("power_total", 1e3),          # 1-0:1.4  active power total
    (2, TYPE_INSTANT): ("power_export", 1e3),
    (3, TYPE_INSTANT): ("reactive_power", 1e3),
    (9, TYPE_INSTANT): ("power_apparent", 1e3),
    (13, TYPE_INSTANT): ("power_factor", 1e3),
    (14, TYPE_INSTANT): ("frequency", 1e3),
    (21, TYPE_INSTANT): ("power_l1", 1e3),
    (41, TYPE_INSTANT): ("power_l2", 1e3),
    (61, TYPE_INSTANT): ("power_l3", 1e3),
    (29, TYPE_INSTANT): ("apparent_l1", 1e3),
    (49, TYPE_INSTANT): ("apparent_l2", 1e3),
    (69, TYPE_INSTANT): ("apparent_l3", 1e3),
    (24, TYPE_INSTANT): ("reactive_l1", 1e3),
    (44, TYPE_INSTANT): ("reactive_l2", 1e3),
    (64, TYPE_INSTANT): ("reactive_l3", 1e3),
    (32, TYPE_INSTANT): ("voltage_l1", 1e3),
    (52, TYPE_INSTANT): ("voltage_l2", 1e3),
    (72, TYPE_INSTANT): ("voltage_l3", 1e3),
    (31, TYPE_INSTANT): ("current_l1", 1e3),
    (51, TYPE_INSTANT): ("current_l2", 1e3),
    (71, TYPE_INSTANT): ("current_l3", 1e3),
    (33, TYPE_INSTANT): ("power_factor_l1", 1e3),
    (53, TYPE_INSTANT): ("power_factor_l2", 1e3),
    (73, TYPE_INSTANT): ("power_factor_l3", 1e3),
    # cumulative (type 8) – milli watt hours
    (1, TYPE_ENERGY): ("energy_total", 1e6),          # kWh
    (2, TYPE_ENERGY): ("energy_export", 1e6),
    (3, TYPE_ENERGY): ("reactive_energy_import", 1e6),
    (4, TYPE_ENERGY): ("reactive_energy_export", 1e6),
}


# ---------------------------------------------------------------------------
# Readings
# ---------------------------------------------------------------------------

@dataclass
class SmartMeterReading:
    """Decoded smart meter snapshot from one frame."""

    power_total: float = 0.0
    power_l1: float = 0.0
    power_l2: float = 0.0
    power_l3: float = 0.0
    power_export: float = 0.0
    power_apparent: float = 0.0
    apparent_l1: float = 0.0
    apparent_l2: float = 0.0
    apparent_l3: float = 0.0
    voltage_l1: float = 0.0
    voltage_l2: float = 0.0
    voltage_l3: float = 0.0
    current_l1: float = 0.0
    current_l2: float = 0.0
    current_l3: float = 0.0
    frequency: float = 0.0
    energy_total: float = 0.0
    energy_export: float = 0.0
    reactive_power: float = 0.0
    reactive_l1: float = 0.0
    reactive_l2: float = 0.0
    reactive_l3: float = 0.0
    reactive_energy_import: float = 0.0
    reactive_energy_export: float = 0.0
    power_factor: float = 0.0
    power_factor_l1: float = 0.0
    power_factor_l2: float = 0.0
    power_factor_l3: float = 0.0
    timestamp: float = 0.0
    meter_id: str = ""
    #: Registers that are not in :data:`CHANNELS` – surfaced for diagnostics.
    extra: dict[int, int] = field(default_factory=dict)
    #: Registers seen for the first time in this frame.
    new_unknown: set[int] = field(default_factory=set)

    @property
    def power_total_kw(self) -> float:
        return round(self.power_total / 1000, 3)

    def as_dict(self) -> dict:
        return {
            key: getattr(self, key)
            for key in (
                "power_total", "power_l1", "power_l2", "power_l3", "power_export",
                "power_apparent", "voltage_l1", "voltage_l2", "voltage_l3",
                "current_l1", "current_l2", "current_l3", "frequency",
                "energy_total", "energy_export", "reactive_power",
                "power_factor", "timestamp",
            )
        }


#: Channels already reported as unknown, to keep the log readable.
_WARNED_CHANNELS: set[int] = set()


def decode_smart_meter_frame(raw: bytes) -> Optional[SmartMeterReading]:
    """Decode one ``GDRs`` frame into a :class:`SmartMeterReading`."""
    try:
        gdr, gdr_id = _unwrap_gdr(raw)
        if gdr is None:
            return None
    except Exception as exc:  # noqa: BLE001 - malformed frame
        _LOGGER.debug("Cannot parse smart meter frame: %s (%s)", exc, raw[:24].hex())
        return None

    reading = SmartMeterReading(meter_id=gdr_id)

    timestamp = _blob(gdr, 3)
    if timestamp is not None:
        try:
            reading.timestamp = parse_timestamp(timestamp)
        except Exception:  # noqa: BLE001
            pass

    for field_no, wire, value in gdr:
        if field_no != 4 or wire != WT_LENGTH or not isinstance(value, (bytes, bytearray)):
            continue
        entry = decode_fields(value)              # map entry {key, value}
        channel_id = _varint(entry, 1)
        raw_value = _varint(entry, 2)
        if channel_id is None or raw_value is None:
            continue

        measurement, vtype = unpack_channel(channel_id)
        target = CHANNELS.get((measurement, vtype))
        if target is None:
            reading.extra[channel_id] = raw_value
            if channel_id not in _WARNED_CHANNELS:
                _WARNED_CHANNELS.add(channel_id)
                reading.new_unknown.add(channel_id)
            continue

        attribute, divisor = target
        setattr(reading, attribute, raw_value / divisor)

    return reading


def _unwrap_gdr(raw: bytes) -> tuple[Optional[list], str]:
    """GDRs -> (GDR fields, id)."""
    outer = decode_fields(raw)
    entry_raw = _blob(outer, 1)
    if entry_raw is None:
        return None, ""
    entry = decode_fields(entry_raw)          # map entry {key: string, value: GDR}
    gdr_id = _text(_blob(entry, 1) or b"")
    gdr_raw = _blob(entry, 2)
    if gdr_raw is None:
        return None, gdr_id
    return decode_fields(gdr_raw), gdr_id


# ---------------------------------------------------------------------------
# EVSE
# ---------------------------------------------------------------------------

#: IEC 61851-ish wallbox states as reported by the eMS Home.
#: 12 was reported on an eMH1 in issue #2: the eMS Home pauses the running
#: charging session through its own load management (PV/hybrid mode, missing
#: surplus, grid limits) and the wallbox reports that as "12".
EVSE_STATUS_TEXT = {
    0: "unknown",
    1: "available",
    2: "occupied",
    3: "preparing",
    4: "charging",
    5: "finishing",
    6: "reserved",
    7: "unavailable",
    8: "faulted",
    9: "suspended_ev",
    10: "suspended_evse",
    12: "charging_paused",
}

#: States in which a vehicle is physically connected.
EVSE_PLUGGED_STATES = frozenset({2, 3, 4, 5, 9, 12})


@dataclass
class EVSEReading:
    """Decoded wallbox snapshot from one frame."""

    uuid: str = ""
    evse_status: int = 0
    evse_status_code: str = ""
    evse_error_code: str = ""
    evse_serial: str = ""
    evse_hw_imax: int = 0            # mA
    ev_imax_default: int = 0         # mA
    session_duration: int = 0        # s
    session_energy: float = 0.0      # Wh
    energy_total: float = 0.0        # Wh
    timestamp: float = 0.0
    #: Unknown flex values, kept for diagnostics.
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def hw_imax_amps(self) -> float:
        return round(self.evse_hw_imax / 1000, 1) if self.evse_hw_imax else 0.0

    @property
    def session_duration_min(self) -> float:
        return round(self.session_duration / 60, 1)

    @property
    def session_energy_kwh(self) -> float:
        return round(self.session_energy / 1000, 3)

    @property
    def energy_total_kwh(self) -> float:
        return round(self.energy_total / 1000, 3)

    @property
    def status_text(self) -> str:
        return EVSE_STATUS_TEXT.get(self.evse_status, f"status_{self.evse_status}")

    @property
    def is_plugged(self) -> bool:
        return self.evse_status in EVSE_PLUGGED_STATES

    @property
    def is_charging(self) -> bool:
        return self.evse_status == 4

    def as_dict(self) -> dict:
        return {
            "uuid": self.uuid,
            "status": self.status_text,
            "status_code": self.evse_status_code,
            "error_code": self.evse_error_code,
            "serial": self.evse_serial,
            "hw_max_current_a": self.hw_imax_amps,
            "session_duration_s": self.session_duration,
            "session_energy_wh": self.session_energy,
            "energy_total_wh": self.energy_total,
            "timestamp": self.timestamp,
        }


#: Numeric flex values seen in the wild, with their unit.
EVSE_NUMERIC_KEYS = {
    "evse_status",
    "evse_hw_imax",
    "ev_imax_default",
    "evse_session_duration",
    "evse_session_energy",
    "evse_energy_total",
}

EVSE_TEXT_KEYS = {"evse_status_code", "evse_error_code", "evse_serial"}

_WARNED_FLEX: set[str] = set()

#: Status codes already logged as unmapped, to keep the log readable.
_WARNED_STATUS: set[int] = set()


def decode_evse_frame(raw: bytes) -> Optional[EVSEReading]:
    """Decode one EVSE ``GDRs`` frame."""
    try:
        gdr, gdr_id = _unwrap_gdr(raw)
        if gdr is None:
            return None
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("Cannot parse EVSE frame: %s (%s)", exc, raw[:24].hex())
        return None

    reading = EVSEReading(uuid=gdr_id)

    timestamp = _blob(gdr, 3)
    if timestamp is not None:
        try:
            reading.timestamp = parse_timestamp(timestamp)
        except Exception:  # noqa: BLE001
            pass

    for field_no, wire, value in gdr:
        if field_no != 5 or wire != WT_LENGTH or not isinstance(value, (bytes, bytearray)):
            continue
        try:
            _apply_flex_value(reading, value)
        except Exception as exc:  # noqa: BLE001 - one bad key must not kill the frame
            _LOGGER.debug("Cannot parse EVSE flex value: %s", exc)

    if reading.evse_status not in EVSE_STATUS_TEXT and reading.evse_status not in _WARNED_STATUS:
        _WARNED_STATUS.add(reading.evse_status)
        _LOGGER.info(
            "Unknown wallbox status %s (status code %r, wallbox %r) – please report it "
            "together with a diagnostics download so it can be mapped",
            reading.evse_status,
            reading.evse_status_code or "?",
            reading.uuid or "?",
        )

    return reading


def _apply_flex_value(reading: EVSEReading, entry_raw: bytes) -> None:
    entry = decode_fields(entry_raw)                     # map entry {key, FlexValue}
    key = _text(_blob(entry, 1) or b"")
    flex_raw = _blob(entry, 2)
    if not key or flex_raw is None:
        return

    outer = decode_fields(flex_raw)                      # FlexValue {type, value}
    type_raw = _first(outer, 1)
    value_raw = _first(outer, 2)

    # The firmware encodes numbers as varints and strings as UTF-8.  Depending
    # on the firmware revision the *type* field is sometimes used for the number
    # and the *value* field for the text, so both orders are accepted.
    numeric = next((v for v in (value_raw, type_raw) if isinstance(v, int)), None)
    text = next((_text(v) for v in (value_raw, type_raw) if isinstance(v, (bytes, bytearray))), "")

    if key == "evse_status" and numeric is not None:
        reading.evse_status = int(numeric)
    elif key == "evse_hw_imax" and numeric is not None:
        reading.evse_hw_imax = int(numeric)
    elif key == "ev_imax_default" and numeric is not None:
        reading.ev_imax_default = int(numeric)
    elif key == "evse_session_duration" and numeric is not None:
        reading.session_duration = int(numeric)
    elif key == "evse_session_energy" and numeric is not None:
        reading.session_energy = float(numeric) / 1000  # mWh -> Wh
    elif key == "evse_energy_total" and numeric is not None:
        reading.energy_total = float(numeric) / 1000
    elif key == "evse_status_code":
        reading.evse_status_code = text
    elif key == "evse_error_code":
        reading.evse_error_code = text
    elif key == "evse_serial":
        reading.evse_serial = text
    elif text or numeric is not None:
        reading.extra[key] = text or str(numeric)
        if key not in _WARNED_FLEX:
            _WARNED_FLEX.add(key)
            _LOGGER.debug("Unknown EVSE flex value %r = %r", key, text or numeric)
    # else: the device sends the key with an empty FlexValue – nothing to store
