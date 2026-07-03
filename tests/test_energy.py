"""Tests for the HA Energy dashboard solar forecast platform."""

from datetime import datetime, UTC
from types import SimpleNamespace

import pytest

from custom_components.ha_solcast_fusion.const import DOMAIN
from custom_components.ha_solcast_fusion.energy import async_get_solar_forecast


def _make_hass(time_zone, watts):
    """Minimal hass stub exposing config.time_zone and the coordinator watts."""
    coordinator = SimpleNamespace(data={"watts": watts})
    return SimpleNamespace(
        config=SimpleNamespace(time_zone=time_zone),
        data={DOMAIN: {"e1": {"coordinator": coordinator}}},
    )


@pytest.mark.asyncio
async def test_hourly_slots_align_to_local_whole_hours_half_hour_offset():
    """In a +05:30 zone, 30-min UTC buckets must aggregate to local whole hours."""
    # UTC 07:30 -> 13:00 IST, UTC 08:00 -> 13:30 IST: both in local hour 13:00.
    watts = {
        datetime(2026, 7, 3, 7, 30, tzinfo=UTC).isoformat(): 1000.0,
        datetime(2026, 7, 3, 8, 0, tzinfo=UTC).isoformat(): 2000.0,
    }
    hass = _make_hass("Asia/Kolkata", watts)

    result = await async_get_solar_forecast(hass, "e1")
    assert result is not None

    wh_hours = result["wh_hours"]
    # Single local-hour bucket at 13:00+05:30, summing both 30-min contributions.
    assert list(wh_hours) == ["2026-07-03T13:00:00+05:30"]
    assert wh_hours["2026-07-03T13:00:00+05:30"] == pytest.approx((1000.0 + 2000.0) * 0.5)

    # Every emitted key must be a local whole hour (minute == 0 in local tz).
    for key in wh_hours:
        assert datetime.fromisoformat(key).minute == 0


@pytest.mark.asyncio
async def test_hourly_slots_align_to_local_whole_hours_whole_hour_offset():
    """Whole-hour-offset zones keep whole-hour slots (regression guard)."""
    # UTC 11:00 -> 13:00 CEST, UTC 11:30 -> 13:30 CEST: both in local hour 13:00.
    watts = {
        datetime(2026, 7, 3, 11, 0, tzinfo=UTC).isoformat(): 1000.0,
        datetime(2026, 7, 3, 11, 30, tzinfo=UTC).isoformat(): 2000.0,
    }
    hass = _make_hass("Europe/Amsterdam", watts)

    result = await async_get_solar_forecast(hass, "e1")
    assert result is not None

    wh_hours = result["wh_hours"]
    assert list(wh_hours) == ["2026-07-03T13:00:00+02:00"]
    assert wh_hours["2026-07-03T13:00:00+02:00"] == pytest.approx((1000.0 + 2000.0) * 0.5)
