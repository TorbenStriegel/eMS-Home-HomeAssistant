"""
eMS Home HTTP API client.

Adapted from the ABL eMS Home working solution.
Handles OAuth2 authentication and all HTTP endpoints.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import requests
from requests import Session


# ===========================================================================
# Data classes
# ===========================================================================

@dataclass
class PhaseValues:
    """A measurement broken down across three phases plus a total."""
    total: float
    l1: float
    l2: float
    l3: float

    @classmethod
    def from_dict(cls, d: dict) -> "PhaseValues":
        return cls(
            total=d.get("total", 0),
            l1=d.get("l1", 0),
            l2=d.get("l2", 0),
            l3=d.get("l3", 0),
        )


@dataclass
class DeviceStatus:
    """System health snapshot from /api/device-settings/devicestatus."""
    status: str
    cpu_load: int
    cpu_temp: int
    ram_free: int
    ram_total: int
    flash_app_free: int
    flash_app_total: int
    flash_data_free: int
    flash_data_total: int

    @property
    def ram_used_pct(self) -> float:
        return round((1 - self.ram_free / self.ram_total) * 100, 1)

    @property
    def flash_app_used_pct(self) -> float:
        return round((1 - self.flash_app_free / self.flash_app_total) * 100, 1)

    @property
    def flash_data_used_pct(self) -> float:
        return round((1 - self.flash_data_free / self.flash_data_total) * 100, 1)

    @classmethod
    def from_dict(cls, d: dict) -> "DeviceStatus":
        return cls(
            status=d.get("status", "unknown"),
            cpu_load=d.get("CpuLoad", 0),
            cpu_temp=d.get("CpuTemp", 0),
            ram_free=d.get("RamFree", 0),
            ram_total=d.get("RamTotal", 1),
            flash_app_free=d.get("FlashAppFree", 0),
            flash_app_total=d.get("FlashAppTotal", 1),
            flash_data_free=d.get("FlashDataFree", 0),
            flash_data_total=d.get("FlashDataTotal", 1),
        )


@dataclass
class EMobilityState:
    """Live e-mobility charging state from /api/e-mobility/state."""
    ev_charging_power: PhaseValues
    curtailment_setpoint: PhaseValues
    overload_protection_active: bool

    @property
    def is_charging(self) -> bool:
        return self.ev_charging_power.total > 0

    @property
    def total_power_kw(self) -> float:
        return round(self.ev_charging_power.total / 1_000_000, 3)

    @classmethod
    def from_dict(cls, d: dict) -> "EMobilityState":
        return cls(
            ev_charging_power=PhaseValues.from_dict(d.get("EvChargingPower", {})),
            curtailment_setpoint=PhaseValues.from_dict(d.get("CurtailmentSetpoint", {})),
            overload_protection_active=d.get("OverloadProtectionActive", False),
        )


class ChargeMode(str):
    """Known charge-mode strings used by the eMS Home firmware."""
    GRID   = "grid"
    LOCK   = "lock"
    PV     = "pv"
    HYBRID = "hybrid"


@dataclass
class ChargeModeConfig:
    """Charge-mode configuration from /api/e-mobility/config/chargemode."""
    mode: str
    min_charging_power_quota: int
    min_pv_power_quota: int
    last_min_charging_power_quota: int
    last_min_pv_power_quota: int

    @property
    def is_locked(self) -> bool:
        return self.mode == ChargeMode.LOCK

    @classmethod
    def from_dict(cls, d: dict) -> "ChargeModeConfig":
        return cls(
            mode=d.get("mode", "unknown"),
            min_charging_power_quota=d.get("mincharginpowerquota") or 0,
            min_pv_power_quota=d.get("minpvpowerquota") or 0,
            last_min_charging_power_quota=d.get("lastminchargingpowerquota") or 0,
            last_min_pv_power_quota=d.get("lastminpvpowerquota") or 0,
        )

    def to_payload(self) -> dict:
        return {
            "mode": self.mode,
            "mincharginpowerquota": self.min_charging_power_quota or None,
            "minpvpowerquota": self.min_pv_power_quota,
        }


# ===========================================================================
# HTTP client
# ===========================================================================

class EMSHomeHTTP:
    """HTTP client for the eMS Home web interface with OAuth2 auth."""

    _CLIENT_ID     = "emos"
    _CLIENT_SECRET = "56951025"
    _USERNAME      = "admin"
    _TOKEN_PATH    = "/api/web-login/token"

    def __init__(self, host: str, password: str, port: int = 80,
                 use_https: bool = False, verify_ssl: bool = False,
                 timeout: float = 8.0):
        scheme = "https" if use_https or port == 443 else "http"
        self._base    = f"{scheme}://{host}:{port}"
        self._host    = host
        self._password = password
        self._timeout  = timeout

        self._session: Session = requests.Session()
        self._session.verify = verify_ssl
        # Exactly match browser headers for compatibility with eMS Home firmware
        self._session.headers.update({
            "Accept": "application/json, text/plain, */*",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{scheme}://{host}:{port}/e-mobility/app",
            "User-Agent": "Mozilla/5.0 (HomeAssistant) AppleWebKit/537.36",
            "Origin": f"{scheme}://{host}:{port}",
        })

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    def _is_token_valid(self) -> bool:
        return (self._access_token is not None and
                time.time() < self._token_expires_at - 60)

    def _apply_auth(self) -> None:
        if not self._is_token_valid():
            self.login()

    def _request(self, method: str, path: str, **kwargs) -> "requests.Response":
        self._apply_auth()
        resp = getattr(self._session, method)(
            f"{self._base}{path}", timeout=self._timeout, **kwargs
        )
        if resp.status_code == 401:
            self.login()
            resp = getattr(self._session, method)(
                f"{self._base}{path}", timeout=self._timeout, **kwargs
            )
        resp.raise_for_status()
        return resp

    def _get(self, path: str, **kwargs) -> "requests.Response":
        return self._request("get", path, **kwargs)

    def _put(self, path: str, **kwargs) -> "requests.Response":
        return self._request("put", path, **kwargs)

    def login(self) -> dict:
        """Obtain a JWT Bearer token via OAuth2 password grant."""
        url = f"{self._base}{self._TOKEN_PATH}"
        data = {
            "grant_type":    "password",
            "client_id":     self._CLIENT_ID,
            "client_secret": self._CLIENT_SECRET,
            "username":      self._USERNAME,
            "password":      self._password,
        }
        resp = self._session.post(url, data=data, timeout=self._timeout)
        resp.raise_for_status()

        token_data = resp.json()
        self._access_token    = token_data["access_token"]
        expires_in            = int(token_data.get("expires_in", 604800))
        self._token_expires_at = time.time() + expires_in

        self._session.headers.update(
            {"Authorization": f"Bearer {self._access_token}"}
        )
        return token_data

    def logout(self) -> None:
        self._access_token     = None
        self._token_expires_at = 0.0
        self._session.headers.pop("Authorization", None)

    @property
    def token(self) -> Optional[str]:
        return self._access_token

    # ------------------------------------------------------------------
    # API endpoints
    # ------------------------------------------------------------------

    def get_device_status(self) -> DeviceStatus:
        raw = self._get("/api/device-settings/devicestatus").json()
        return DeviceStatus.from_dict(raw)

    def get_emobility_state(self) -> EMobilityState:
        raw = self._get("/api/e-mobility/state").json()
        return EMobilityState.from_dict(raw)

    def get_charge_mode(self) -> ChargeModeConfig:
        raw = self._get("/api/e-mobility/config/chargemode").json()
        return ChargeModeConfig.from_dict(raw)

    def set_charge_mode(self, mode: str,
                        min_charging_power_quota: Optional[int] = None,
                        min_pv_power_quota: int = 0) -> ChargeModeConfig:
        payload = {
            "mode": mode,
            "mincharginpowerquota": min_charging_power_quota,
            "minpvpowerquota": min_pv_power_quota,
        }
        self._put("/api/e-mobility/config/chargemode", json=payload)
        return self.get_charge_mode()

    def __enter__(self):
        self.login()
        return self

    def __exit__(self, *_):
        self.logout()

