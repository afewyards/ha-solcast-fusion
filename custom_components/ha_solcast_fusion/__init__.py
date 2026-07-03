"""SolcastFusion Home Assistant integration."""

from __future__ import annotations

import logging
from datetime import datetime, timezone, UTC
from pathlib import Path
from zoneinfo import ZoneInfo

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change

from .const import CONF_SETUP_QUOTA_CALLS, DOMAIN
from .coordinator import OpenMeteoCoordinator, SolcastPoller
from .horizon import load_horizon
from .mirror import async_mirror_check
from .store import SolcastFusionStore

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass, config_entry) -> bool:
    """Set up SolcastFusion from a config entry."""
    config = {**config_entry.data, **config_entry.options}
    tz = ZoneInfo(hass.config.time_zone)

    profile = None
    if horizon_file := config.get("horizon_file"):
        try:
            profile = load_horizon(Path(horizon_file).read_text())
        except Exception:
            _LOGGER.warning("Failed to load horizon file %r", horizon_file, exc_info=True)

    store = SolcastFusionStore(hass, config_entry.entry_id)
    await store.load()

    pending_calls = config_entry.data.get(CONF_SETUP_QUOTA_CALLS, 0)
    if pending_calls:
        now = datetime.now(tz=UTC)
        await store.reset_if_new_utc_day(now)
        await store.bump_quota(now, pending_calls)
        await store.save_now()
        cleared = {k: v for k, v in config_entry.data.items() if k != CONF_SETUP_QUOTA_CALLS}
        hass.config_entries.async_update_entry(config_entry, data=cleared)

    coordinator = OpenMeteoCoordinator(hass, config, store, profile, tz)
    session = async_get_clientsession(hass)
    poller = SolcastPoller(hass, config, store, coordinator, session, tz)
    poller.start()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][config_entry.entry_id] = {
        "coordinator": coordinator,
        "store": store,
        "poller": poller,
    }

    await coordinator.async_refresh()

    async def _run_mirror(now=None):
        await async_mirror_check(hass, config_entry, config, store, session, coordinator)

    config_entry.async_on_unload(async_track_time_change(hass, _run_mirror, hour=0, minute=5, second=0))
    config_entry.async_create_background_task(hass, _run_mirror(), "ha_solcast_fusion_mirror_startup")

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    return True


async def async_unload_entry(hass, config_entry) -> bool:
    """Unload SolcastFusion config entry."""
    if unloaded := await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS):
        entry_data = hass.data[DOMAIN].pop(config_entry.entry_id)
        poller: SolcastPoller = entry_data["poller"]
        poller.stop()
    return unloaded
