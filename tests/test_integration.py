"""End-to-end integration tests for SolcastFusion.

Tests coordinator + sensor layer end-to-end using the same stub pattern as
test_scheduler.py / test_sensor.py: HA stubs are installed at module level,
then the real coordinator / sensor code is imported and exercised directly
without a full Home Assistant instance.
"""

import asyncio
import sys
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# HA stubs — must be installed before any ha_solcast_fusion imports
# ---------------------------------------------------------------------------


class _FakeDUC:
    """Minimal DataUpdateCoordinator stub."""

    def __init__(self, hass, logger, name, update_interval):
        self.hass = hass
        self.data = None

    def async_set_updated_data(self, data):
        self.data = data


class _CoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator


@dataclass(frozen=True, kw_only=True)
class _SensorEntityDescription:
    key: str
    translation_key: str | None = None
    device_class: Any = None
    entity_category: Any = None
    native_unit_of_measurement: str | None = None
    state_class: Any = None
    has_entity_name: bool = False
    name: Any = None
    icon: str | None = None
    unit_of_measurement: str | None = None
    force_update: bool = False
    placeholder: str | None = None
    translation_placeholders: dict | None = None


class _SensorDeviceClass:
    ENERGY = "energy"
    POWER = "power"
    TIMESTAMP = "timestamp"


class _SensorStateClass:
    MEASUREMENT = "measurement"
    TOTAL_INCREASING = "total_increasing"


class _SensorEntity:
    pass


class _EntityCategory:
    DIAGNOSTIC = "diagnostic"


class _UnitOfEnergy:
    KILO_WATT_HOUR = "kWh"


class _UnitOfPower:
    WATT = "W"


_duc_mod = MagicMock()
_duc_mod.DataUpdateCoordinator = _FakeDUC
_duc_mod.CoordinatorEntity = _CoordinatorEntity

_sensor_mod = MagicMock()
_sensor_mod.SensorEntityDescription = _SensorEntityDescription
_sensor_mod.SensorDeviceClass = _SensorDeviceClass
_sensor_mod.SensorStateClass = _SensorStateClass
_sensor_mod.SensorEntity = _SensorEntity

_const_mod = MagicMock()
_const_mod.EntityCategory = _EntityCategory
_const_mod.UnitOfEnergy = _UnitOfEnergy
_const_mod.UnitOfPower = _UnitOfPower

for _name, _mod in [
    ("homeassistant", MagicMock()),
    ("homeassistant.components", MagicMock()),
    ("homeassistant.components.sensor", _sensor_mod),
    ("homeassistant.const", _const_mod),
    ("homeassistant.helpers", MagicMock()),
    ("homeassistant.helpers.update_coordinator", _duc_mod),
    ("homeassistant.helpers.event", MagicMock()),
    ("homeassistant.helpers.storage", MagicMock()),
    ("homeassistant.helpers.aiohttp_client", MagicMock()),
    ("open_meteo_solar_forecast", MagicMock()),
    ("astral", MagicMock()),
    ("astral.sun", MagicMock()),
]:
    sys.modules.setdefault(_name, _mod)

from custom_components.ha_solcast_fusion.combiner import resample_30min
from custom_components.ha_solcast_fusion.coordinator import OpenMeteoCoordinator
from custom_components.ha_solcast_fusion.sensor import build_sensors
from custom_components.ha_solcast_fusion.store import SolcastFusionStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OM_PATCH = "open_meteo_solar_forecast.OpenMeteoSolarForecast"


def _buckets(value=1000.0):
    """30-min daytime buckets for today UTC, 06:00–17:30."""
    today = datetime.now(UTC).date()
    return {
        datetime(today.year, today.month, today.day, h, m, tzinfo=UTC): value for h in range(6, 18) for m in (0, 30)
    }


def _om_cls(watts=None, raises=False):
    """Return a mock OpenMeteoSolarForecast class."""
    if raises:
        inst = MagicMock()
        inst.estimate = AsyncMock(side_effect=RuntimeError("OM down"))
    else:
        est = MagicMock()
        est.watts = watts if watts is not None else _buckets()
        inst = MagicMock()
        inst.estimate = AsyncMock(return_value=est)
    return MagicMock(return_value=inst)


def _make_store(k_factors=None, last_solcast=None, quota_used=0):
    """SolcastFusionStore backed by a no-op AsyncMock."""
    ha_store = AsyncMock()
    ha_store.async_load = AsyncMock(return_value=None)
    ha_store.async_save = AsyncMock()
    ha_store.async_delay_save = MagicMock()

    store = SolcastFusionStore.__new__(SolcastFusionStore)
    store._init_state()
    store._store = ha_store
    store._lock = asyncio.Lock()

    if k_factors:
        store._data["k_factors"] = {t.isoformat(): v for t, v in k_factors.items()}
    if last_solcast:
        store._data["last_solcast"] = {t.isoformat(): v for t, v in last_solcast.items()}
    store._data["quota_used"] = quota_used
    return store


_BASE_CONFIG = {
    "latitude": 52.0,
    "longitude": 4.0,
    "dc_w": 5000,
    "solcast_key": "test-key",
    "solcast_site": "test-site",
    "om_interval_min": 20,
    "solcast_cap": 8,
    "solcast_reserve": 2,
}


def _make_coordinator(store):
    hass = MagicMock()
    return OpenMeteoCoordinator(hass, _BASE_CONFIG, store, None, UTC)


async def _refresh(coord, watts=None, om_raises=False):
    """Run _async_update_data with OM patched; set coord.data; return data."""
    with patch(_OM_PATCH, _om_cls(watts, om_raises)):
        data = await coord._async_update_data()
    coord.data = data
    return data


def _inject_kfactors(store, om_watts, sc_watts):
    k = {t: 1.2 for t in om_watts}
    store._data["k_factors"] = {t.isoformat(): v for t, v in k.items()}
    store._data["last_solcast"] = {t.isoformat(): v for t, v in sc_watts.items()}
    return k


# ---------------------------------------------------------------------------
# Scenario 1 — Normal flow: OM + prior Solcast k_factors → blended
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_normal_flow_blended():
    """After refresh with OM + k_factors in store: source=blended, watts non-empty."""
    om_watts = _buckets(1000.0)
    sc_watts = _buckets(1200.0)
    store = _make_store()
    _inject_kfactors(store, om_watts, sc_watts)
    coord = _make_coordinator(store)

    data = await _refresh(coord, watts=om_watts)

    assert data["source"] == "blended"
    assert isinstance(data["today_kwh"], float)
    assert data["today_kwh"] > 0
    assert data["watts"]

    coord.data = data
    sensors = build_sensors(coord, "e1")
    today = next(s for s in sensors if s.entity_description.key == "energy_production_today")
    assert today.available
    assert today.native_value == data["today_kwh"]
    assert today.extra_state_attributes["watts"]


# ---------------------------------------------------------------------------
# Scenario 2 — Solcast-down: no k_factors → om-only, states valid
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_solcast_down_om_only():
    """Empty store (Solcast never succeeded): source=om-only, values valid and non-zero."""
    om_watts = _buckets(1000.0)
    store = _make_store()
    coord = _make_coordinator(store)

    data = await _refresh(coord, watts=om_watts)

    assert data["source"] == "om-only"
    assert isinstance(data["today_kwh"], float)
    assert data["today_kwh"] > 0
    assert data["watts"]

    coord.data = data
    sensors = build_sensors(coord, "e2")
    today = next(s for s in sensors if s.entity_description.key == "energy_production_today")
    assert today.available
    assert today.native_value > 0


# ---------------------------------------------------------------------------
# Scenario 3 — OM-down after prior blend: held curve keeps sensors available
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_om_down_after_prior_blend_stays_available():
    """OM raises but held_curve set + k_factors in store: all sensors stay available."""
    om_watts = _buckets(1000.0)
    sc_watts = _buckets(1200.0)
    store = _make_store()
    _inject_kfactors(store, om_watts, sc_watts)
    coord = _make_coordinator(store)
    coord._held_curve = resample_30min(om_watts)

    data = await _refresh(coord, om_raises=True)

    assert data, "data must be non-empty (sensors available)"
    assert data["source"] == "blended"

    coord.data = data
    sensors = build_sensors(coord, "e3")
    for s in sensors:
        assert s.available, f"{s.entity_description.key} should stay available"


# ---------------------------------------------------------------------------
# Scenario 4 — Both-down from cold: sensors unavailable, never return 0
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_both_down_from_cold_unavailable():
    """Cold start + OM fails + no k_factors: data={}, sensors unavailable, native_value None."""
    store = _make_store()
    coord = _make_coordinator(store)

    data = await _refresh(coord, om_raises=True)

    assert data == {}

    coord.data = data
    sensors = build_sensors(coord, "e4")
    for s in sensors:
        assert not s.available, f"{s.entity_description.key} should be unavailable"
        assert s.native_value is None, f"{s.entity_description.key} must be None, not 0"


# ---------------------------------------------------------------------------
# Scenario 5 — Cold-start pre-sunrise: fresh install, OM works
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cold_start_pre_sunrise_om_only():
    """Fresh install, empty store, OM works: source=om-only, k_factors={}, cf=1.0, quota=0."""
    om_watts = _buckets(1000.0)
    store = _make_store()
    coord = _make_coordinator(store)

    data = await _refresh(coord, watts=om_watts)

    assert data["source"] == "om-only"
    assert store.k_factors == {}
    assert data["correction_factor"] == pytest.approx(1.0)
    assert store.quota_remaining(8) == 8
    assert data["watts"]
