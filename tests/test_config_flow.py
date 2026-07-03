"""Tests for SolcastFusion config flow (key -> pick -> confirm)."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_solcast_fusion.const import (
    CONF_AC_W,
    CONF_AZIMUTH,
    CONF_DC_W,
    CONF_DECAY_HALFLIFE_H,
    CONF_DECLINATION,
    CONF_DIFFUSE,
    CONF_LAT,
    CONF_LON,
    CONF_SOLCAST_KEY,
    CONF_SOLCAST_SITE,
    DEFAULTS,
    DOMAIN,
)
from custom_components.ha_solcast_fusion.solcast import (
    SolcastAuthError,
    SolcastBusyError,
)

_PATCH = "custom_components.ha_solcast_fusion.config_flow.fetch_sites"

SITE_A = {
    "resource_id": "site-a",
    "name": "Home",
    "latitude": 51.5,
    "longitude": -0.1,
    "capacity": 4.6,
    "capacity_dc": 5.0,
    "azimuth": 180,  # south -> compass 180
    "tilt": 30,
}
SITE_B = {
    "resource_id": "site-b",
    "name": "Shed",
    "latitude": 52.0,
    "longitude": 4.0,
    "capacity": 3.0,
    "capacity_dc": 3.3,
    "azimuth": -90,  # east -> compass 90
    "tilt": 20,
}
SITE_NO_AC = {
    "resource_id": "site-c",
    "name": "Garage",
    "latitude": 50.0,
    "longitude": 3.0,
    "capacity": None,
    "capacity_dc": 4.4,
    "azimuth": 0,
    "tilt": 15,
}


async def _init(hass):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


@pytest.mark.asyncio
async def test_multi_site_flow_creates_entry(hass):
    with (
        patch(_PATCH, new=AsyncMock(return_value=[SITE_A, SITE_B])),
        patch("custom_components.ha_solcast_fusion.mirror.fetch_sites", new=AsyncMock(return_value=[])),
    ):
        r = await _init(hass)
        assert r["step_id"] == "user"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_SOLCAST_KEY: "k"})
        assert r["step_id"] == "site"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_SOLCAST_SITE: "site-b"})
        assert r["step_id"] == "confirm"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
        # CREATE_ENTRY auto-sets-up the entry, which kicks off the mirror's
        # startup background task — flush it here while fetch_sites is still
        # mocked, so it doesn't fire a real network call during teardown.
        await hass.async_block_till_done(wait_background_tasks=True)

    assert r["type"] == FlowResultType.CREATE_ENTRY
    assert r["data"][CONF_SOLCAST_SITE] == "site-b"
    assert r["data"][CONF_SOLCAST_KEY] == "k"
    assert r["data"][CONF_AZIMUTH] == 90  # Solcast -90 -> compass 90
    assert r["data"][CONF_DECLINATION] == 20
    assert r["data"][CONF_DC_W] == 3300


@pytest.mark.asyncio
async def test_single_site_skips_picker(hass):
    with (
        patch(_PATCH, new=AsyncMock(return_value=[SITE_A])),
        patch("custom_components.ha_solcast_fusion.mirror.fetch_sites", new=AsyncMock(return_value=[])),
    ):
        r = await _init(hass)
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_SOLCAST_KEY: "k"})
        # No picker form — jumps straight to confirm.
        assert r["step_id"] == "confirm"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
        await hass.async_block_till_done(wait_background_tasks=True)

    assert r["type"] == FlowResultType.CREATE_ENTRY
    assert r["data"][CONF_SOLCAST_SITE] == "site-a"


@pytest.mark.asyncio
async def test_confirm_shows_mapped_geometry(hass):
    with patch(_PATCH, new=AsyncMock(return_value=[SITE_A])):
        r = await _init(hass)
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_SOLCAST_KEY: "k"})
    assert r["step_id"] == "confirm"
    ph = r["description_placeholders"]
    assert ph[CONF_AZIMUTH] == "180"
    assert ph[CONF_LAT] == "51.5"


@pytest.mark.asyncio
async def test_no_sites_error(hass):
    with patch(_PATCH, new=AsyncMock(return_value=[])):
        r = await _init(hass)
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_SOLCAST_KEY: "k"})
    assert r["step_id"] == "user"
    assert r["errors"]["base"] == "no_sites"


@pytest.mark.asyncio
async def test_invalid_auth_error(hass):
    with patch(_PATCH, new=AsyncMock(side_effect=SolcastAuthError("401"))):
        r = await _init(hass)
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_SOLCAST_KEY: "bad"})
    assert r["step_id"] == "user"
    assert r["errors"]["base"] == "invalid_auth"


@pytest.mark.asyncio
async def test_busy_error(hass):
    with patch(_PATCH, new=AsyncMock(side_effect=SolcastBusyError("429"))):
        r = await _init(hass)
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_SOLCAST_KEY: "k"})
    assert r["step_id"] == "user"
    assert r["errors"]["base"] == "solcast_busy"


@pytest.mark.asyncio
async def test_invalid_site_error(hass):
    bad = {**SITE_A, "capacity": None, "capacity_dc": None}
    with patch(_PATCH, new=AsyncMock(return_value=[bad])):
        r = await _init(hass)
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_SOLCAST_KEY: "k"})
    # Single-site auto-select maps immediately -> invalid_site on the picker step.
    assert r["step_id"] == "site"
    assert r["errors"]["base"] == "invalid_site"


@pytest.mark.asyncio
async def test_reconfigure_updates_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_LAT: 51.5,
            CONF_LON: -0.1,
            CONF_DECLINATION: 30,
            CONF_AZIMUTH: 180,
            CONF_DC_W: 5000,
            CONF_SOLCAST_KEY: "k",
            CONF_SOLCAST_SITE: "site-a",
        },
        options={},
    )
    entry.add_to_hass(hass)
    with (
        patch(_PATCH, new=AsyncMock(return_value=[SITE_B])),
        patch("custom_components.ha_solcast_fusion.mirror.fetch_sites", new=AsyncMock(return_value=[])),
    ):
        r = await entry.start_reconfigure_flow(hass)
        assert r["step_id"] == "user"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_SOLCAST_KEY: "k"})
        # single site -> confirm
        assert r["step_id"] == "confirm"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
        # reconfigure_successful reloads the entry, re-triggering the mirror
        # startup task — flush it while still mocked.
        await hass.async_block_till_done(wait_background_tasks=True)

    assert r["type"] == FlowResultType.ABORT
    assert r["reason"] == "reconfigure_successful"
    assert entry.data[CONF_SOLCAST_SITE] == "site-b"
    assert entry.data[CONF_AZIMUTH] == 90


@pytest.mark.asyncio
async def test_reconfigure_drops_stale_ac_w_when_new_site_has_none(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_LAT: 51.5,
            CONF_LON: -0.1,
            CONF_DECLINATION: 30,
            CONF_AZIMUTH: 180,
            CONF_DC_W: 5000,
            CONF_AC_W: 4600,
            CONF_SOLCAST_KEY: "k",
            CONF_SOLCAST_SITE: "site-a",
        },
        options={},
    )
    entry.add_to_hass(hass)
    with (
        patch(_PATCH, new=AsyncMock(return_value=[SITE_NO_AC])),
        patch("custom_components.ha_solcast_fusion.mirror.fetch_sites", new=AsyncMock(return_value=[])),
    ):
        r = await entry.start_reconfigure_flow(hass)
        assert r["step_id"] == "user"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_SOLCAST_KEY: "k"})
        # single site -> confirm
        assert r["step_id"] == "confirm"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
        await hass.async_block_till_done(wait_background_tasks=True)

    assert r["type"] == FlowResultType.ABORT
    assert r["reason"] == "reconfigure_successful"
    assert entry.data[CONF_SOLCAST_SITE] == "site-c"
    assert CONF_AC_W not in entry.data


@pytest.mark.asyncio
async def test_options_flow_round_trips_diffuse_and_decay(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_LAT: 51.5,
            CONF_LON: -0.1,
            CONF_DECLINATION: 30,
            CONF_AZIMUTH: 180,
            CONF_DC_W: 5000,
            CONF_SOLCAST_KEY: "k",
            CONF_SOLCAST_SITE: "site-a",
        },
        options={},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.ha_solcast_fusion.mirror.fetch_sites", new=AsyncMock(return_value=[])):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)

    r = await hass.config_entries.options.async_init(entry.entry_id)
    assert r["step_id"] == "init"
    new_opts = {k: v for k, v in DEFAULTS.items()}
    new_opts[CONF_DIFFUSE] = 0.2
    new_opts[CONF_DECAY_HALFLIFE_H] = 0
    new_opts["horizon_file"] = ""
    r = await hass.config_entries.options.async_configure(r["flow_id"], new_opts)
    assert r["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_DIFFUSE] == pytest.approx(0.2)


@pytest.mark.asyncio
async def test_confirm_defaults_name_to_site_name(hass):
    with (
        patch(_PATCH, new=AsyncMock(return_value=[SITE_A])),
        patch("custom_components.ha_solcast_fusion.mirror.fetch_sites", new=AsyncMock(return_value=[])),
    ):
        r = await _init(hass)
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_SOLCAST_KEY: "k"})
        assert r["step_id"] == "confirm"
        # Submit with no name -> form schema default fills in the site name.
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
        await hass.async_block_till_done(wait_background_tasks=True)

    assert r["type"] == FlowResultType.CREATE_ENTRY
    assert r["title"] == "Home"  # SITE_A["name"]


@pytest.mark.asyncio
async def test_custom_name_used_as_title(hass):
    with (
        patch(_PATCH, new=AsyncMock(return_value=[SITE_A])),
        patch("custom_components.ha_solcast_fusion.mirror.fetch_sites", new=AsyncMock(return_value=[])),
    ):
        r = await _init(hass)
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_SOLCAST_KEY: "k"})
        assert r["step_id"] == "confirm"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_NAME: "Roof East"})
        await hass.async_block_till_done(wait_background_tasks=True)

    assert r["type"] == FlowResultType.CREATE_ENTRY
    assert r["title"] == "Roof East"
    assert r["data"][CONF_SOLCAST_SITE] == "site-a"


@pytest.mark.asyncio
async def test_reconfigure_updates_title(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Old Name",
        data={
            CONF_LAT: 51.5,
            CONF_LON: -0.1,
            CONF_DECLINATION: 30,
            CONF_AZIMUTH: 180,
            CONF_DC_W: 5000,
            CONF_SOLCAST_KEY: "k",
            CONF_SOLCAST_SITE: "site-a",
        },
        options={},
    )
    entry.add_to_hass(hass)
    with (
        patch(_PATCH, new=AsyncMock(return_value=[SITE_A])),
        patch("custom_components.ha_solcast_fusion.mirror.fetch_sites", new=AsyncMock(return_value=[])),
    ):
        r = await entry.start_reconfigure_flow(hass)
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_SOLCAST_KEY: "k"})
        assert r["step_id"] == "confirm"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_NAME: "New Name"})
        await hass.async_block_till_done(wait_background_tasks=True)

    assert r["type"] == FlowResultType.ABORT
    assert r["reason"] == "reconfigure_successful"
    assert entry.title == "New Name"


@pytest.mark.asyncio
async def test_blank_name_falls_back_to_site_name(hass):
    with (
        patch(_PATCH, new=AsyncMock(return_value=[SITE_A])),
        patch("custom_components.ha_solcast_fusion.mirror.fetch_sites", new=AsyncMock(return_value=[])),
    ):
        r = await _init(hass)
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_SOLCAST_KEY: "k"})
        assert r["step_id"] == "confirm"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_NAME: "   "})
        await hass.async_block_till_done(wait_background_tasks=True)

    assert r["type"] == FlowResultType.CREATE_ENTRY
    assert r["title"] == "Home"
