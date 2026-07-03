import pytest
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock

from custom_components.ha_solcast_fusion.solcast import fetch_forecast, SolcastAuthError, SolcastError

SITE = "abc-123"
KEY = "my-api-key"
FORECAST_JSON = {"forecasts": [{"period_end": "2026-06-30T10:30:00Z", "pv_estimate": 2.0}]}
# period_end - 30min = 10:00 UTC; pv_estimate * 1000 = 2000.0
EXPECTED_DT = datetime(2026, 6, 30, 10, 0, tzinfo=UTC)


def _make_session(status, json_body):
    response = AsyncMock()
    response.status = status
    response.json = AsyncMock(return_value=json_body)
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.get = MagicMock(return_value=cm)
    return session, response


@pytest.mark.asyncio
async def test_200_returns_normalized_dict():
    session, _ = _make_session(200, FORECAST_JSON)
    result = await fetch_forecast(session, KEY, SITE)
    assert result[EXPECTED_DT] == pytest.approx(2000.0)


@pytest.mark.asyncio
async def test_bearer_header_sent():
    session, _ = _make_session(200, FORECAST_JSON)
    await fetch_forecast(session, KEY, SITE)
    call_kwargs = session.get.call_args
    headers = call_kwargs.kwargs.get("headers") or call_kwargs.args[1] if len(call_kwargs.args) > 1 else {}
    if not headers:
        headers = call_kwargs.kwargs.get("headers", {})
    assert headers.get("Authorization") == f"Bearer {KEY}"


@pytest.mark.asyncio
async def test_url_contains_site_id():
    session, _ = _make_session(200, FORECAST_JSON)
    await fetch_forecast(session, KEY, SITE)
    url_called = session.get.call_args.args[0]
    assert f"/rooftop_sites/{SITE}/forecasts" in url_called


@pytest.mark.asyncio
async def test_401_raises_solcast_auth_error():
    session, _ = _make_session(401, {})
    with pytest.raises(SolcastAuthError):
        await fetch_forecast(session, KEY, SITE)


@pytest.mark.asyncio
async def test_403_raises_solcast_auth_error():
    session, _ = _make_session(403, {})
    with pytest.raises(SolcastAuthError):
        await fetch_forecast(session, KEY, SITE)


@pytest.mark.asyncio
async def test_500_raises_solcast_error():
    session, _ = _make_session(500, {})
    with pytest.raises(SolcastError):
        await fetch_forecast(session, KEY, SITE)


from custom_components.ha_solcast_fusion.solcast import (
    fetch_sites,
    site_to_config,
    SolcastBusyError,
    SolcastSiteError,
)
from custom_components.ha_solcast_fusion.const import (
    CONF_LAT,
    CONF_LON,
    CONF_DECLINATION,
    CONF_AZIMUTH,
    CONF_DC_W,
    CONF_AC_W,
    CONF_SOLCAST_SITE,
)

SITES_JSON = {
    "sites": [
        {
            "resource_id": "abc-123",
            "name": "My Home",
            "latitude": -33.856784,
            "longitude": 151.215297,
            "capacity": 5.0,
            "capacity_dc": 6.2,
            "azimuth": 0,
            "tilt": 30,
            "loss_factor": 0.9,
        }
    ]
}


@pytest.mark.asyncio
async def test_fetch_sites_returns_sites_list():
    session, _ = _make_session(200, SITES_JSON)
    result = await fetch_sites(session, KEY)
    assert isinstance(result, list)
    assert result[0]["resource_id"] == "abc-123"


@pytest.mark.asyncio
async def test_fetch_sites_url_and_bearer():
    session, _ = _make_session(200, SITES_JSON)
    await fetch_sites(session, KEY)
    url_called = session.get.call_args.args[0]
    headers = session.get.call_args.kwargs.get("headers", {})
    assert url_called.endswith("/rooftop_sites")
    assert headers.get("Authorization") == f"Bearer {KEY}"


@pytest.mark.asyncio
async def test_fetch_sites_401_raises_auth():
    session, _ = _make_session(401, {})
    with pytest.raises(SolcastAuthError):
        await fetch_sites(session, KEY)


@pytest.mark.asyncio
async def test_fetch_sites_429_raises_busy():
    session, _ = _make_session(429, {})
    with pytest.raises(SolcastBusyError):
        await fetch_sites(session, KEY)


@pytest.mark.asyncio
async def test_fetch_sites_500_raises_error():
    session, _ = _make_session(500, {})
    with pytest.raises(SolcastError):
        await fetch_sites(session, KEY)


def test_site_to_config_maps_fields():
    cfg = site_to_config(SITES_JSON["sites"][0])
    assert cfg[CONF_LAT] == pytest.approx(-33.856784)
    assert cfg[CONF_LON] == pytest.approx(151.215297)
    assert cfg[CONF_DECLINATION] == 30
    assert cfg[CONF_DC_W] == 6200  # capacity_dc * 1000
    assert cfg[CONF_AC_W] == 5000  # capacity * 1000
    assert cfg[CONF_SOLCAST_SITE] == "abc-123"


def test_site_to_config_azimuth_north_is_zero():
    cfg = site_to_config({**SITES_JSON["sites"][0], "azimuth": 0})
    assert cfg[CONF_AZIMUTH] == 0


def test_site_to_config_azimuth_east_becomes_90():
    cfg = site_to_config({**SITES_JSON["sites"][0], "azimuth": -90})
    assert cfg[CONF_AZIMUTH] == 90


def test_site_to_config_azimuth_west_becomes_270():
    cfg = site_to_config({**SITES_JSON["sites"][0], "azimuth": 90})
    assert cfg[CONF_AZIMUTH] == 270


def test_site_to_config_azimuth_south_becomes_180():
    cfg = site_to_config({**SITES_JSON["sites"][0], "azimuth": 180})
    assert cfg[CONF_AZIMUTH] == 180


def test_site_to_config_azimuth_wrap_edge_stays_below_360():
    # slightly west of north: (-0.4)%360 = 359.6 -> round 360 -> %360 = 0
    cfg = site_to_config({**SITES_JSON["sites"][0], "azimuth": 0.4})
    assert 0 <= cfg[CONF_AZIMUTH] <= 359
    assert cfg[CONF_AZIMUTH] == 0


def test_site_to_config_capacity_dc_missing_falls_back_to_ac():
    site = {**SITES_JSON["sites"][0]}
    del site["capacity_dc"]
    cfg = site_to_config(site)
    assert cfg[CONF_DC_W] == 5000  # falls back to capacity (AC) * 1000


def test_site_to_config_no_capacity_raises():
    site = {**SITES_JSON["sites"][0], "capacity": None, "capacity_dc": None}
    with pytest.raises(SolcastSiteError):
        site_to_config(site)


def test_site_to_config_missing_tilt_raises_site_error():
    site = {**SITES_JSON["sites"][0]}
    del site["tilt"]
    with pytest.raises(SolcastSiteError):
        site_to_config(site)
