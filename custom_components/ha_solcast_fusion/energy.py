"""Energy platform for solar forecast integration with HA Energy dashboard."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant

from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import OpenMeteoCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_get_solar_forecast(
    hass: HomeAssistant, config_entry_id: str
) -> dict[str, dict[str, float | int]] | None:
    """Return solar forecast for the Energy dashboard.

    Returns {"wh_hours": {iso_string: Wh}} for each hour.
    """
    _LOGGER.debug("async_get_solar_forecast called for %s", config_entry_id)

    data = hass.data.get(DOMAIN, {}).get(config_entry_id)
    if not data:
        _LOGGER.warning("No data found for config_entry_id %s", config_entry_id)
        return None

    coordinator: OpenMeteoCoordinator = data.get("coordinator")
    if not coordinator or not coordinator.data:
        _LOGGER.warning("No coordinator or coordinator.data for %s", config_entry_id)
        return None

    watts_raw = coordinator.data.get("watts")
    if not watts_raw:
        _LOGGER.warning("No watts data in coordinator for %s", config_entry_id)
        return None

    _LOGGER.debug("Found %d watts entries", len(watts_raw))

    # watts_raw is {ISO string: W} at 30-min intervals on the UTC :00/:30 grid.
    # Energy dashboard wants {iso_string: Wh} bucketed by *local* hour, so slots
    # line up with local whole hours (e.g. 13:00–14:00) rather than UTC whole
    # hours — which render at :30 in half-hour-offset zones like Asia/Kolkata.
    tz = ZoneInfo(hass.config.time_zone)
    watts: dict[datetime, float] = {}
    for ts_str, w in watts_raw.items():
        dt = datetime.fromisoformat(ts_str)
        watts[dt] = w

    # Aggregate 30-min watts to hourly Wh, floored to the local hour.
    hourly_wh: dict[str, float] = {}
    for dt, w in sorted(watts.items()):
        hour_start = dt.astimezone(tz).replace(minute=0, second=0, microsecond=0)
        hour_key = hour_start.isoformat()
        # 30-min interval at W → 0.5h × W = Wh contribution
        wh_contribution = w * 0.5
        hourly_wh[hour_key] = hourly_wh.get(hour_key, 0.0) + wh_contribution

    _LOGGER.debug("Returning %d hourly entries for energy dashboard", len(hourly_wh))
    return {"wh_hours": hourly_wh}
