import pytest
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.ha_solcast_fusion.mirror import async_mirror_check, geometry_differs
from custom_components.ha_solcast_fusion.solcast import SolcastBusyError
from custom_components.ha_solcast_fusion.const import (
    CONF_LAT,
    CONF_LON,
    CONF_DECLINATION,
    CONF_AZIMUTH,
    CONF_DC_W,
    CONF_AC_W,
    CONF_SOLCAST_KEY,
    CONF_SOLCAST_SITE,
)

# Solcast site whose mapping == BASE_DATA geometry (azimuth -180 -> compass 180).
SITE_SAME = {
    "resource_id": "rid",
    "name": "Home",
    "latitude": 52.0,
    "longitude": 4.0,
    "capacity": 5.0,
    "capacity_dc": 5.0,
    "azimuth": -180,
    "tilt": 30,
}
SITE_CHANGED = {**SITE_SAME, "tilt": 45}  # declination 30 -> 45

BASE_DATA = {
    CONF_SOLCAST_KEY: "k",
    CONF_SOLCAST_SITE: "rid",
    CONF_LAT: 52.0,
    CONF_LON: 4.0,
    CONF_DECLINATION: 30,
    CONF_AZIMUTH: 180,
    CONF_DC_W: 5000,
    CONF_AC_W: 5000,
}


def _fake_store(mirror_sync_date=None):
    store = MagicMock()
    store.reset_if_new_utc_day = AsyncMock()
    store.mirror_sync_date = mirror_sync_date
    store.mark_mirror_synced = AsyncMock()
    return store


def _fake_env(data=None):
    entry = MagicMock()
    entry.data = dict(data or BASE_DATA)
    entry.entry_id = "e1"
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    coord = MagicMock()
    coord.async_request_refresh = AsyncMock()
    return hass, entry, coord


# --- geometry_differs unit ---


def test_geometry_differs_detects_tilt_change():
    assert geometry_differs(BASE_DATA, {**BASE_DATA, CONF_DECLINATION: 45})


def test_geometry_differs_ignores_tiny_latlon_jitter():
    assert not geometry_differs(BASE_DATA, {**BASE_DATA, CONF_LAT: 52.0 + 1e-7})


def test_geometry_differs_detects_latlon_move():
    assert geometry_differs(BASE_DATA, {**BASE_DATA, CONF_LAT: 52.01})


# --- async_mirror_check ---


@pytest.mark.asyncio
async def test_changed_geometry_updates_and_refreshes():
    hass, entry, coord = _fake_env()
    store = _fake_store()
    config = dict(BASE_DATA)
    with patch("custom_components.ha_solcast_fusion.mirror.fetch_sites", new=AsyncMock(return_value=[SITE_CHANGED])):
        await async_mirror_check(hass, entry, config, store, MagicMock(), coord)
    hass.config_entries.async_update_entry.assert_called_once()
    assert config[CONF_DECLINATION] == 45
    coord.async_request_refresh.assert_awaited_once()
    store.mark_mirror_synced.assert_awaited_once()


@pytest.mark.asyncio
async def test_unchanged_geometry_no_update():
    hass, entry, coord = _fake_env()
    store = _fake_store()
    config = dict(BASE_DATA)
    with patch("custom_components.ha_solcast_fusion.mirror.fetch_sites", new=AsyncMock(return_value=[SITE_SAME])):
        await async_mirror_check(hass, entry, config, store, MagicMock(), coord)
    hass.config_entries.async_update_entry.assert_not_called()
    coord.async_request_refresh.assert_not_awaited()
    store.mark_mirror_synced.assert_awaited_once()


@pytest.mark.asyncio
async def test_already_synced_today_skips_fetch():
    hass, entry, coord = _fake_env()
    store = _fake_store(mirror_sync_date="2026-07-01")
    fetch = AsyncMock()
    with (
        patch("custom_components.ha_solcast_fusion.mirror._utc_today", return_value="2026-07-01"),
        patch("custom_components.ha_solcast_fusion.mirror.fetch_sites", fetch),
    ):
        await async_mirror_check(hass, entry, dict(BASE_DATA), store, MagicMock(), coord)
    fetch.assert_not_called()
    store.mark_mirror_synced.assert_not_awaited()


@pytest.mark.asyncio
async def test_busy_error_does_not_mark_synced():
    hass, entry, coord = _fake_env()
    store = _fake_store()
    with patch(
        "custom_components.ha_solcast_fusion.mirror.fetch_sites", new=AsyncMock(side_effect=SolcastBusyError("429"))
    ):
        await async_mirror_check(hass, entry, dict(BASE_DATA), store, MagicMock(), coord)
    store.mark_mirror_synced.assert_not_awaited()
    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_missing_resource_id_marks_synced_no_update():
    hass, entry, coord = _fake_env()
    store = _fake_store()
    other = {**SITE_SAME, "resource_id": "different"}
    with patch("custom_components.ha_solcast_fusion.mirror.fetch_sites", new=AsyncMock(return_value=[other])):
        await async_mirror_check(hass, entry, dict(BASE_DATA), store, MagicMock(), coord)
    store.mark_mirror_synced.assert_awaited_once()
    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_dropped_capacity_removes_key_and_converges():
    hass, entry, coord = _fake_env()  # entry.data includes CONF_AC_W: 5000
    store = _fake_store()
    config = dict(entry.data)
    site_no_ac = {**SITE_SAME, "capacity": None}  # capacity_dc stays 5.0 -> DC ok, no AC_W mapped
    with patch("custom_components.ha_solcast_fusion.mirror.fetch_sites", new=AsyncMock(return_value=[site_no_ac])):
        await async_mirror_check(hass, entry, config, store, MagicMock(), coord)
    updated = hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert CONF_AC_W not in updated  # removed from persisted data
    assert CONF_AC_W not in config  # removed from shared dict
    # convergence: with AC_W now gone from both sides, no further diff
    from custom_components.ha_solcast_fusion.solcast import site_to_config

    assert geometry_differs(updated, site_to_config(site_no_ac)) is False
