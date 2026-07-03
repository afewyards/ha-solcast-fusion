import aiohttp
from datetime import datetime

from .combiner import normalize_solcast
from .const import (
    CONF_AC_W,
    CONF_AZIMUTH,
    CONF_DC_W,
    CONF_DECLINATION,
    CONF_LAT,
    CONF_LON,
    CONF_SOLCAST_SITE,
)

_BASE = "https://api.solcast.com.au/rooftop_sites/{site}/forecasts"
_SITES_BASE = "https://api.solcast.com.au/rooftop_sites"


class SolcastError(Exception):
    pass


class SolcastAuthError(SolcastError):
    pass


class SolcastBusyError(SolcastError):
    """Solcast returned 429 (server busy / rate-limited) — transient."""


class SolcastSiteError(SolcastError):
    """Solcast site record is missing required data (e.g. capacity)."""


async def fetch_forecast(session, key: str, site: str, hours: int = 168) -> dict[datetime, float]:
    url = _BASE.format(site=site)
    headers = {"Authorization": f"Bearer {key}"}
    params = {"format": "json", "hours": hours}

    timeout = aiohttp.ClientTimeout(total=30)
    async with session.get(url, headers=headers, params=params, timeout=timeout) as resp:
        if resp.status in (401, 403):
            raise SolcastAuthError(f"Auth failed: HTTP {resp.status}")
        if resp.status != 200:
            raise SolcastError(f"Unexpected status: HTTP {resp.status}")
        data = await resp.json()

    return normalize_solcast(data["forecasts"])


async def fetch_sites(session, key: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {key}"}
    params = {"format": "json"}
    timeout = aiohttp.ClientTimeout(total=30)
    async with session.get(_SITES_BASE, headers=headers, params=params, timeout=timeout) as resp:
        if resp.status in (401, 403):
            raise SolcastAuthError(f"Auth failed: HTTP {resp.status}")
        if resp.status == 429:
            raise SolcastBusyError("Solcast busy: HTTP 429")
        if resp.status != 200:
            raise SolcastError(f"Unexpected status: HTTP {resp.status}")
        data = await resp.json()
    return data.get("sites", [])


def site_to_config(site: dict) -> dict:
    """Map a Solcast rooftop-site record to SolcastFusion config keys."""
    cap_ac = site.get("capacity")
    cap_dc = site.get("capacity_dc")
    dc_kw = cap_dc if (cap_dc is not None and cap_dc > 0) else cap_ac
    if dc_kw is None or dc_kw <= 0:
        raise SolcastSiteError("Solcast site has no usable capacity")

    try:
        lat = float(site["latitude"])
        lon = float(site["longitude"])
        tilt = round(float(site["tilt"]))
        # Solcast N=0/E=-90/W=+90 -> compass N=0/E=90/S=180/W=270; outer %360 avoids 360.
        az = round((-float(site["azimuth"])) % 360) % 360
        resource_id = site["resource_id"]
    except (KeyError, TypeError, ValueError) as err:
        raise SolcastSiteError(f"Solcast site record missing/invalid geometry: {err}") from err

    out = {
        CONF_LAT: lat,
        CONF_LON: lon,
        CONF_DECLINATION: tilt,
        CONF_AZIMUTH: az,
        CONF_DC_W: round(dc_kw * 1000),
        CONF_SOLCAST_SITE: resource_id,
    }
    if cap_ac is not None and cap_ac > 0:
        out[CONF_AC_W] = round(cap_ac * 1000)
    return out
