from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone, UTC

from homeassistant.helpers.event import async_track_point_in_time, async_track_sunrise
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .combiner import (
    blend,
    compute_k,
    daily_scalar,
    is_clamped,
    resample_30min,
    rollups,
)
from .const import (
    CONF_AC_W,
    CONF_AZIMUTH,
    CONF_DAMP_AM,
    CONF_DAMP_PM,
    CONF_DC_W,
    CONF_DECAY_HALFLIFE_H,
    CONF_DECLINATION,
    CONF_DIFFUSE,
    CONF_EFFICIENCY,
    CONF_K_MAX,
    CONF_K_MIN,
    CONF_LAT,
    CONF_LON,
    CONF_OM_INTERVAL_MIN,
    CONF_SOLCAST_CAP,
    CONF_SOLCAST_KEY,
    CONF_SOLCAST_RESERVE,
    CONF_SOLCAST_SITE,
    DEFAULTS,
)
from .horizon import apply_mask
from .solcast import fetch_forecast

_LOGGER = logging.getLogger(__name__)


def solcast_interval(daylight_h: float, cap: int, reserve: int) -> timedelta | None:
    """Spread (cap - reserve) calls evenly across daylight hours."""
    if cap <= reserve:
        return None
    return timedelta(hours=daylight_h / (cap - reserve))


def next_due(
    now: datetime,
    sunrise: datetime,
    sunset: datetime,
    quota_remaining: int,
    reserve: int,
    last_poll_ts: datetime | None,
    interval: timedelta,
) -> datetime | None:
    """Return when the next Solcast poll should fire, or None if it should not."""
    if quota_remaining <= reserve:
        return None
    if now > sunset:
        return None
    # Earliest candidate: preserve cadence from the last poll, else fire now.
    if last_poll_ts is not None:
        candidate = last_poll_ts + interval
        if candidate <= now:
            candidate = now
    else:
        candidate = now
    # Never poll before sunrise; defer the day's first poll to sunrise.
    if candidate < sunrise:
        candidate = sunrise
    # Never poll after sunset; no more polls today.
    if candidate > sunset:
        return None
    return candidate


class OpenMeteoCoordinator(DataUpdateCoordinator):
    """Fetch OpenMeteo solar forecast; blend with Solcast k-factors from store."""

    def __init__(self, hass, config: dict, store, profile, tz) -> None:
        om_interval = timedelta(minutes=config.get(CONF_OM_INTERVAL_MIN, DEFAULTS[CONF_OM_INTERVAL_MIN]))
        super().__init__(hass, _LOGGER, name="ha_solcast_fusion_om", update_interval=om_interval)
        self._config = config
        self._store = store
        self._profile = profile
        self._tz = tz
        self._held_curve: dict | None = None
        self.pct_periods_clamped: float | None = None

    @property
    def held_curve(self) -> dict | None:
        return self._held_curve

    async def _async_update_data(self) -> dict:
        from open_meteo_solar_forecast import OpenMeteoSolarForecast

        _LOGGER.debug("Starting OpenMeteo data fetch")

        cfg = self._config
        lat = cfg[CONF_LAT]
        lon = cfg[CONF_LON]
        dc_w = cfg.get(CONF_DC_W, 0)
        ac_w = cfg.get(CONF_AC_W)

        _LOGGER.debug("Config: lat=%s, lon=%s, dc_w=%s, ac_w=%s", lat, lon, dc_w, ac_w)

        om_curve: dict | None = None
        try:
            # Convert compass azimuth (0=N, 90=E, 180=S, 270=W) to Open-Meteo (0=S, -90=E, 90=W)
            compass_az = cfg.get(CONF_AZIMUTH, 180)
            om_az = compass_az - 180
            if om_az > 180:
                om_az -= 360
            elif om_az < -180:
                om_az += 360

            est = await OpenMeteoSolarForecast(
                latitude=lat,
                longitude=lon,
                declination=cfg.get(CONF_DECLINATION, 0),
                azimuth=om_az,
                dc_kwp=dc_w / 1000,
                ac_kwp=(ac_w / 1000) if ac_w else None,
                damping_morning=cfg.get(CONF_DAMP_AM, DEFAULTS[CONF_DAMP_AM]),
                damping_evening=cfg.get(CONF_DAMP_PM, DEFAULTS[CONF_DAMP_PM]),
                efficiency_factor=cfg.get(CONF_EFFICIENCY, DEFAULTS[CONF_EFFICIENCY]),
            ).estimate()
            om_curve = resample_30min({t: float(w) for t, w in est.watts.items()})
            self._held_curve = om_curve
            _LOGGER.debug("OpenMeteo fetch success: %d data points", len(om_curve))
        except Exception as e:
            _LOGGER.warning("OpenMeteo fetch failed: %s; reusing held curve", e, exc_info=True)
            om_curve = self._held_curve

        store = self._store
        k_factors = store.k_factors

        # Neither OM nor Solcast has ever produced → sensors go unavailable
        if om_curve is None and not k_factors:
            _LOGGER.warning("No data available: om_curve=%s, k_factors=%s", om_curve, bool(k_factors))
            return {}

        if om_curve is None:
            om_curve = {}

        now = datetime.now(tz=UTC)
        return self._build_output_data(om_curve, now)

    def _build_output_data(self, om_curve: dict, now: datetime) -> dict:
        cfg = self._config
        lat = cfg[CONF_LAT]
        lon = cfg[CONF_LON]
        k_min = cfg.get(CONF_K_MIN, DEFAULTS[CONF_K_MIN])
        k_max = cfg.get(CONF_K_MAX, DEFAULTS[CONF_K_MAX])
        halflife_s = cfg.get(CONF_DECAY_HALFLIFE_H, DEFAULTS[CONF_DECAY_HALFLIFE_H]) * 3600
        cap = cfg.get(CONF_SOLCAST_CAP, DEFAULTS[CONF_SOLCAST_CAP])
        diffuse = cfg.get(CONF_DIFFUSE, DEFAULTS[CONF_DIFFUSE])

        store = self._store
        k_factors = store.k_factors
        last_solcast_ts = store.last_solcast_ts
        age_s = (now - last_solcast_ts).total_seconds() if last_solcast_ts else 0.0

        blended = blend(om_curve, k_factors, store.last_solcast, age_s, halflife_s)
        masked = apply_mask(blended, self._profile, lat, lon, diffuse)
        data = rollups(masked, now, self._tz)

        data["watts"] = {t.isoformat(): w for t, w in masked.items()}
        data["source"] = "blended" if k_factors else "om-only"
        data["correction_factor"] = daily_scalar(om_curve, store.last_solcast, k_min, k_max)
        data["solcast_calls_remaining"] = store.quota_remaining(cap)
        data["last_solcast_update"] = last_solcast_ts
        data["pct_periods_clamped"] = self.pct_periods_clamped

        return data


class SolcastPoller:
    """Adaptive sun-aware Solcast poller driven by async_track_point_in_time."""

    def __init__(
        self,
        hass,
        config: dict,
        store,
        om_coord: OpenMeteoCoordinator,
        session,
        tz,
    ) -> None:
        self._hass = hass
        self._config = config
        self._store = store
        self._om_coord = om_coord
        self._session = session
        self._tz = tz
        self._unsub: Callable[[], None] | None = None
        self._unsub_sunrise: Callable[[], None] | None = None
        self._poll_in_flight: bool = False
        self._retry_after: datetime | None = None

    def start(self) -> None:
        self._unsub_sunrise = async_track_sunrise(self._hass, self._on_sunrise)
        self._schedule_next()

    def stop(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        if self._unsub_sunrise is not None:
            self._unsub_sunrise()
            self._unsub_sunrise = None

    def _on_sunrise(self) -> None:
        self._schedule_next()

    def _schedule_next(self) -> None:
        if self._poll_in_flight:
            # A poll is currently running; it will reschedule itself when done.
            return

        if self._unsub is not None:
            self._unsub()
            self._unsub = None

        from astral import Observer
        from astral.sun import sunrise as _sunrise, sunset as _sunset

        cfg = self._config
        lat = cfg[CONF_LAT]
        lon = cfg[CONF_LON]
        cap = cfg.get(CONF_SOLCAST_CAP, DEFAULTS[CONF_SOLCAST_CAP])
        reserve = cfg.get(CONF_SOLCAST_RESERVE, DEFAULTS[CONF_SOLCAST_RESERVE])

        now = datetime.now(tz=UTC)
        self._store.reset_if_new_utc_day_sync(now)

        obs = Observer(latitude=lat, longitude=lon)
        today = now.astimezone(self._tz).date()
        sr = _sunrise(obs, date=today, tzinfo=self._tz)
        ss = _sunset(obs, date=today, tzinfo=self._tz)

        daylight_h = (ss - sr).total_seconds() / 3600
        interval = solcast_interval(daylight_h, cap, reserve)
        if interval is None:
            return

        when = next_due(
            now,
            sr,
            ss,
            self._store.quota_remaining(cap),
            reserve,
            self._store.last_poll_ts,
            interval,
        )

        # After a failed poll, back off one interval so we don't hammer Solcast
        # during an outage (last_poll_ts stays None on failure, so next_due would
        # otherwise return `now` and busy-loop).
        if when is not None and self._retry_after is not None:
            backoff = self._retry_after + interval
            if when < backoff:
                when = backoff if backoff <= ss else None

        if when is not None:
            self._unsub = async_track_point_in_time(self._hass, self._async_poll, when)

    async def _async_poll(self, now: datetime) -> None:
        if self._poll_in_flight:
            # Guard against overlapping polls (e.g. the sunrise tracker and a
            # point-in-time timer both firing at sunrise).
            return
        self._poll_in_flight = True
        try:
            cfg = self._config
            cap = cfg.get(CONF_SOLCAST_CAP, DEFAULTS[CONF_SOLCAST_CAP])
            reserve = cfg.get(CONF_SOLCAST_RESERVE, DEFAULTS[CONF_SOLCAST_RESERVE])
            k_min = cfg.get(CONF_K_MIN, DEFAULTS[CONF_K_MIN])
            k_max = cfg.get(CONF_K_MAX, DEFAULTS[CONF_K_MAX])

            await self._store.reset_if_new_utc_day(now)

            if self._store.quota_remaining(cap) <= reserve:
                return

            try:
                forecast = await fetch_forecast(
                    self._session,
                    cfg[CONF_SOLCAST_KEY],
                    cfg[CONF_SOLCAST_SITE],
                )
            except Exception:
                _LOGGER.error("Solcast fetch failed", exc_info=True)
                self._retry_after = now
                return

            om_curve = self._om_coord.held_curve or {}
            k_factors: dict[datetime, float] = {}
            clamped = 0
            valid = 0

            for t, sc_w in forecast.items():
                om_w = om_curve.get(t)
                if om_w is None:
                    continue
                k = compute_k(om_w, sc_w, k_min, k_max)
                if k is not None:
                    k_factors[t] = k
                    valid += 1
                    if is_clamped(om_w, sc_w, k_min, k_max):
                        clamped += 1

            self._om_coord.pct_periods_clamped = clamped / valid if valid else 0.0

            store = self._store
            await store.save_poll_result(k_factors, forecast, now)
            await store.bump_quota(now)
            await store.save_now()
            await store.save_debounced()

            self._retry_after = None

            data = self._om_coord._build_output_data(om_curve, now)
            self._om_coord.async_set_updated_data(data)
        finally:
            self._poll_in_flight = False
            self._schedule_next()
