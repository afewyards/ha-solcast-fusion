from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, UTC

_RETENTION = timedelta(hours=48)


class SolcastFusionStore:
    def __init__(self, hass, entry_id: str):
        from homeassistant.helpers.storage import Store

        self._store = Store(hass, 1, f"ha_solcast_fusion.{entry_id}")
        self._init_state()
        self._lock = asyncio.Lock()

    def _init_state(self):
        self._data: dict = {
            "solcast_retained": {},
            "last_solcast": {},
            "k_factors": {},
            "last_solcast_ts": None,
            "quota_date": None,
            "quota_used": 0,
            "last_poll_ts": None,
            "mirror_sync_date": None,
            "schema_version": 2,
        }

    async def load(self) -> None:
        stored = await self._store.async_load()
        if stored:
            self._data.update(self._migrate(stored))

    def _migrate(self, stored: dict) -> dict:
        """Idempotent v1->v2 upgrade: flat last_solcast -> stamped solcast_retained."""
        if "solcast_retained" in stored:
            return stored
        ts = stored.get("last_solcast_ts")
        old = stored.get("last_solcast") or {}
        retained = {iso: {"w": float(w), "fetched": ts} for iso, w in old.items()} if ts else {}
        return {**stored, "solcast_retained": retained, "schema_version": 2}

    async def save_now(self) -> None:
        async with self._lock:
            await self._store.async_save(self._data)

    async def save_debounced(self) -> None:
        async with self._lock:
            self._store.async_delay_save(lambda: self._data, 30)

    @property
    def last_solcast(self) -> dict:
        raw = self._data.get("last_solcast", {})
        return {datetime.fromisoformat(k): v for k, v in raw.items()}

    @property
    def k_factors(self) -> dict:
        raw = self._data.get("k_factors", {})
        return {datetime.fromisoformat(k): v for k, v in raw.items()}

    @property
    def last_solcast_ts(self) -> datetime | None:
        ts = self._data.get("last_solcast_ts")
        return datetime.fromisoformat(ts) if ts else None

    @property
    def solcast_retained(self) -> dict[datetime, dict[str, float | datetime]]:
        raw = self._data.get("solcast_retained", {})
        return {
            datetime.fromisoformat(iso): {"w": float(e["w"]), "fetched": datetime.fromisoformat(e["fetched"])}
            for iso, e in raw.items()
        }

    @property
    def last_poll_ts(self) -> datetime | None:
        ts = self._data.get("last_poll_ts")
        return datetime.fromisoformat(ts) if ts else None

    @property
    def mirror_sync_date(self) -> str | None:
        return self._data.get("mirror_sync_date")

    def quota_remaining(self, cap: int) -> int:
        return cap - self._data["quota_used"]

    def reset_if_new_utc_day_sync(self, now: datetime) -> None:
        """In-memory UTC-day quota reset for the synchronous scheduling path.

        Persistence happens on the next poll's save; if HA restarts before
        then, scheduling self-heals because this runs again on start/sunrise.
        """
        today = now.astimezone(UTC).date().isoformat()
        if self._data.get("quota_date") != today:
            self._data["quota_used"] = 0
            self._data["quota_date"] = today

    async def reset_if_new_utc_day(self, now: datetime) -> None:
        async with self._lock:
            self.reset_if_new_utc_day_sync(now)

    async def save_poll_result(self, k_factors: dict, forecast: dict, ts: datetime) -> None:
        async with self._lock:
            self._data["k_factors"] = {t.isoformat(): k for t, k in k_factors.items()}
            self._data["last_solcast"] = {t.isoformat(): w for t, w in forecast.items()}
            self._data["last_solcast_ts"] = ts.isoformat()
            self._data["last_poll_ts"] = ts.isoformat()

    async def merge_poll(self, forecast: dict[datetime, float], ts: datetime) -> None:
        """Merge a poll's future buckets into the rolling map; expire buckets > 48 h old."""
        cutoff = ts - _RETENTION
        async with self._lock:
            retained = dict(self._data.get("solcast_retained", {}))
            for t, w in forecast.items():
                retained[t.isoformat()] = {"w": float(w), "fetched": ts.isoformat()}
            retained = {iso: e for iso, e in retained.items() if datetime.fromisoformat(iso) >= cutoff}
            self._data["solcast_retained"] = retained
            self._data["last_solcast_ts"] = ts.isoformat()
            self._data["last_poll_ts"] = ts.isoformat()

    async def bump_quota(self, now: datetime, count: int = 1) -> None:
        today = now.astimezone(UTC).date().isoformat()
        async with self._lock:
            self._data["quota_used"] += count
            self._data["quota_date"] = today

    async def mark_mirror_synced(self, now: datetime) -> None:
        today = now.astimezone(UTC).date().isoformat()
        async with self._lock:
            self._data["mirror_sync_date"] = today
        await self.save_now()
