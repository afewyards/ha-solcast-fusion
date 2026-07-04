"""Tests for ha_solcast_fusion sensor platform."""

from datetime import datetime, UTC
from unittest.mock import MagicMock

import pytest
from homeassistant.const import EntityCategory

from custom_components.ha_solcast_fusion.const import DOMAIN
from custom_components.ha_solcast_fusion.sensor import (
    EnergyProductionTodaySensor,
    SolcastFusionSensor,
    async_setup_entry,
    build_sensors,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)

SAMPLE_DATA = {
    "today_kwh": 5.2,
    "today_remaining_kwh": 3.1,
    "tomorrow_kwh": 6.0,
    "power_now": 1500.0,
    "peak_time_today": datetime(2026, 6, 30, 11, 30, tzinfo=UTC),
    "peak_time_tomorrow": datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
    "current_hour_kwh": 0.75,
    "next_hour_kwh": 0.80,
    "watts": {
        "2026-06-30T10:00:00+00:00": 1200.0,
        "2026-06-30T10:30:00+00:00": 1500.0,
        "2026-06-30T11:00:00+00:00": 1800.0,
    },
    "source": "blended",
    "correction_factor": 0.95,
    "solcast_calls_remaining": 6,
    "last_solcast_update": datetime(2026, 6, 30, 9, 0, tzinfo=UTC),
    "pct_solcast_covered": 0.8,
}


def _coord(data):
    c = MagicMock()
    c.data = data
    return c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_energy_production_today_sensor_exists():
    sensors = build_sensors(_coord(SAMPLE_DATA), "test_entry")
    matched = [s for s in sensors if s.entity_description.translation_key == "energy_production_today"]
    assert len(matched) == 1
    assert isinstance(matched[0], EnergyProductionTodaySensor)


def test_energy_production_today_has_nonempty_watts_with_utc_keys():
    sensors = build_sensors(_coord(SAMPLE_DATA), "test_entry")
    today = next(s for s in sensors if s.entity_description.translation_key == "energy_production_today")
    attrs = today.extra_state_attributes
    assert attrs is not None
    watts = attrs["watts"]
    assert len(watts) > 0
    for iso_key, val in watts.items():
        dt = datetime.fromisoformat(iso_key)
        assert dt.tzinfo is not None, f"key {iso_key!r} has no tzinfo"
        assert dt.utcoffset().total_seconds() == 0, f"key {iso_key!r} is not UTC"
        assert isinstance(val, float)


def test_energy_production_today_watts_in_unrecorded_attributes():
    sensors = build_sensors(_coord(SAMPLE_DATA), "test_entry")
    today = next(s for s in sensors if s.entity_description.translation_key == "energy_production_today")
    assert "watts" in today._unrecorded_attributes


def test_other_sensors_do_not_have_watts_unrecorded():
    sensors = build_sensors(_coord(SAMPLE_DATA), "test_entry")
    others = [s for s in sensors if s.entity_description.translation_key != "energy_production_today"]
    for s in others:
        assert "watts" not in s._unrecorded_attributes


def test_available_false_when_coordinator_returns_empty():
    sensors = build_sensors(_coord({}), "test_entry")
    for s in sensors:
        assert s.available is False, f"{s.entity_description.key} should be unavailable"


def test_available_true_when_data_present():
    sensors = build_sensors(_coord(SAMPLE_DATA), "test_entry")
    for s in sensors:
        assert s.available is True


def test_native_value_none_when_no_data():
    sensors = build_sensors(_coord({}), "test_entry")
    for s in sensors:
        assert s.native_value is None


def test_diagnostic_source_sensor_value():
    sensors = build_sensors(_coord(SAMPLE_DATA), "test_entry")
    source = next(s for s in sensors if s.entity_description.translation_key == "source")
    assert source.native_value == "blended"


def test_diagnostic_source_sensor_om_only():
    data = {**SAMPLE_DATA, "source": "om-only"}
    sensors = build_sensors(_coord(data), "test_entry")
    source = next(s for s in sensors if s.entity_description.translation_key == "source")
    assert source.native_value == "om-only"


def test_diagnostic_sensors_have_entity_category():
    diag_keys = {
        "solcast_calls_remaining",
        "last_solcast_update",
        "correction_factor",
        "source",
        "pct_solcast_covered",
    }
    sensors = build_sensors(_coord(SAMPLE_DATA), "test_entry")
    for s in sensors:
        if s.entity_description.key in diag_keys:
            assert s.entity_description.entity_category == EntityCategory.DIAGNOSTIC


def test_pct_solcast_covered_sensor_reads_data_key():
    sensors = build_sensors(_coord(SAMPLE_DATA), "test_entry")
    cov = next(s for s in sensors if s.entity_description.translation_key == "pct_solcast_covered")
    assert cov.native_value == 0.8


def test_energy_production_today_kwh_value():
    sensors = build_sensors(_coord(SAMPLE_DATA), "test_entry")
    today = next(s for s in sensors if s.entity_description.translation_key == "energy_production_today")
    assert today.native_value == 5.2


def test_power_production_now_value():
    sensors = build_sensors(_coord(SAMPLE_DATA), "test_entry")
    power = next(s for s in sensors if s.entity_description.translation_key == "power_production_now")
    assert power.native_value == 1500.0


def test_thirteen_sensors_created():
    sensors = build_sensors(_coord(SAMPLE_DATA), "test_entry")
    assert len(sensors) == 13


def test_unique_ids_per_sensor():
    sensors = build_sensors(_coord(SAMPLE_DATA), "entry_abc")
    uids = [s._attr_unique_id for s in sensors]
    assert len(uids) == len(set(uids))
    assert all(uid.startswith("entry_abc_") for uid in uids)


def test_watts_extra_attrs_none_when_no_data():
    sensors = build_sensors(_coord({}), "test_entry")
    today = next(s for s in sensors if s.entity_description.translation_key == "energy_production_today")
    assert today.extra_state_attributes is None


def test_sensors_share_named_device():
    sensors = build_sensors(_coord(SAMPLE_DATA), "entry_abc", "Roof East")
    assert sensors
    for s in sensors:
        assert s._attr_has_entity_name is True
        di = s._attr_device_info
        assert di is not None
        assert di["identifiers"] == {(DOMAIN, "entry_abc")}
        assert di["name"] == "Roof East"
        assert di["manufacturer"] == "SolcastFusion"
        assert "model" not in di


@pytest.mark.asyncio
async def test_async_setup_entry_names_device_from_entry_title():
    coordinator = _coord(SAMPLE_DATA)
    hass = MagicMock()
    hass.data = {DOMAIN: {"entry1": {"coordinator": coordinator}}}
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.title = "Roof East"
    captured: list = []
    await async_setup_entry(hass, entry, lambda entities: captured.extend(entities))
    assert captured
    assert all(s._attr_device_info["name"] == "Roof East" for s in captured)
    assert all(s._attr_device_info["identifiers"] == {(DOMAIN, "entry1")} for s in captured)
