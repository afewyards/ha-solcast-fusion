from __future__ import annotations

import logging
from datetime import datetime, timezone

from .const import (
    CONF_AC_W,
    CONF_AZIMUTH,
    CONF_DC_W,
    CONF_DECLINATION,
    CONF_LAT,
    CONF_LON,
    CONF_SOLCAST_KEY,
    CONF_SOLCAST_SITE,
)
from .solcast import (
    SolcastError,
    SolcastSiteError,
    fetch_sites,
    site_to_config,
)

_LOGGER = logging.getLogger(__name__)

_MIRROR_KEYS = (
    CONF_LAT,
    CONF_LON,
    CONF_DECLINATION,
    CONF_AZIMUTH,
    CONF_DC_W,
    CONF_AC_W,
)
_LATLON = (CONF_LAT, CONF_LON)


def _utc_today(now: datetime) -> str:
    return now.astimezone(timezone.utc).date().isoformat()


def geometry_differs(current: dict, new: dict) -> bool:
    """True if any mirrored field differs (lat/lon with float tolerance)."""
    for k in _MIRROR_KEYS:
        cur = current.get(k)
        nxt = new.get(k)
        if k in _LATLON and cur is not None and nxt is not None:
            if abs(float(cur) - float(nxt)) > 1e-5:
                return True
        elif cur != nxt:
            return True
    return False


async def async_mirror_check(hass, entry, config, store, session, coordinator) -> None:
    """Once/day: pull the Solcast site record and mirror geometry into config."""
    now = datetime.now(tz=timezone.utc)
    await store.reset_if_new_utc_day(now)
    if store.mirror_sync_date == _utc_today(now):
        return

    try:
        sites = await fetch_sites(session, entry.data[CONF_SOLCAST_KEY])
    except SolcastError:
        _LOGGER.debug("Mirror: Solcast sites fetch failed; will retry", exc_info=True)
        return

    await store.mark_mirror_synced(now)

    rid = entry.data.get(CONF_SOLCAST_SITE)
    site = next((s for s in sites if s.get("resource_id") == rid), None)
    if site is None:
        _LOGGER.warning("Mirror: resource_id %s not found in Solcast sites; skipping", rid)
        return

    try:
        new = site_to_config(site)
    except SolcastSiteError:
        _LOGGER.warning("Mirror: Solcast site %s has no usable capacity; skipping", rid)
        return

    if geometry_differs(entry.data, new):
        _LOGGER.info("Mirror: Solcast geometry changed; updating config in place")
        merged = {**entry.data}
        for k in _MIRROR_KEYS:
            if k in new:
                merged[k] = new[k]
                config[k] = new[k]
            else:
                merged.pop(k, None)
                config.pop(k, None)
        hass.config_entries.async_update_entry(entry, data=merged)
        await coordinator.async_request_refresh()
