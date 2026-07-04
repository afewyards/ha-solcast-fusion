import sys
from unittest.mock import AsyncMock, MagicMock

# Stub homeassistant before our module imports it
for mod in (
    "homeassistant",
    "homeassistant.helpers",
    "homeassistant.helpers.storage",
):
    sys.modules.setdefault(mod, MagicMock())

import pytest
from datetime import datetime, UTC

from custom_components.ha_solcast_fusion.store import SolcastFusionStore


def _make_store(stored=None):
    mock_ha_store = AsyncMock()
    mock_ha_store.async_load = AsyncMock(return_value=stored)
    mock_ha_store.async_save = AsyncMock()
    mock_ha_store.async_delay_save = MagicMock()

    store = SolcastFusionStore.__new__(SolcastFusionStore)
    store._init_state()
    store._store = mock_ha_store
    import asyncio

    store._lock = asyncio.Lock()
    return store, mock_ha_store


DAY1 = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)
DAY2 = datetime(2026, 7, 1, 0, 0, tzinfo=UTC)


# --- quota_remaining ---


@pytest.mark.asyncio
async def test_quota_remaining_decrements_after_bump():
    store, _ = _make_store()
    cap = 10
    before = store.quota_remaining(cap)
    await store.bump_quota(DAY1)
    assert store.quota_remaining(cap) == before - 1


@pytest.mark.asyncio
async def test_quota_remaining_decrements_twice():
    store, _ = _make_store()
    await store.bump_quota(DAY1)
    await store.bump_quota(DAY1)
    assert store.quota_remaining(10) == 8


# --- reset_if_new_utc_day ---


@pytest.mark.asyncio
async def test_reset_zeroes_on_date_change():
    store, _ = _make_store()
    await store.bump_quota(DAY1)
    await store.bump_quota(DAY1)
    assert store._data["quota_used"] == 2
    await store.reset_if_new_utc_day(DAY2)
    assert store._data["quota_used"] == 0


@pytest.mark.asyncio
async def test_reset_does_not_zero_on_same_day():
    store, _ = _make_store()
    await store.bump_quota(DAY1)
    await store.reset_if_new_utc_day(DAY1)
    assert store._data["quota_used"] == 1


# --- ISO serialization round-trips ---


@pytest.mark.asyncio
async def test_load_migrates_legacy_and_drops_old_keys():
    saved = {
        "last_solcast": {"2026-06-30T10:00:00+00:00": 1500.0},
        "k_factors": {"2026-06-30T10:00:00+00:00": 1.2},
        "last_solcast_ts": "2026-06-30T10:00:00+00:00",
        "quota_date": "2026-06-30",
        "quota_used": 3,
        "last_poll_ts": "2026-06-30T10:00:00+00:00",
    }
    store, _ = _make_store(stored=saved)
    await store.load()
    assert store._data["quota_used"] == 3
    assert store._data["quota_date"] == "2026-06-30"
    assert "last_solcast" not in store._data
    assert "k_factors" not in store._data
    key = datetime.fromisoformat("2026-06-30T10:00:00+00:00")
    assert store.solcast_retained[key]["w"] == 1500.0


@pytest.mark.asyncio
async def test_load_with_nothing_stored_keeps_defaults():
    store, _ = _make_store(stored=None)
    await store.load()
    assert store._data["quota_used"] == 0
    assert store._data["solcast_retained"] == {}


@pytest.mark.asyncio
async def test_retained_iso_key_round_trip_preserved():
    store, _ = _make_store()
    store._data["solcast_retained"][DAY1.isoformat()] = {"w": 2000.0, "fetched": DAY1.isoformat()}
    assert store.solcast_retained[DAY1]["w"] == 2000.0


# --- save_now / save_debounced ---


@pytest.mark.asyncio
async def test_save_now_calls_async_save():
    store, mock_ha = _make_store()
    await store.save_now()
    mock_ha.async_save.assert_called_once_with(store._data)


@pytest.mark.asyncio
async def test_save_debounced_calls_async_delay_save():
    store, mock_ha = _make_store()
    await store.save_debounced()
    mock_ha.async_delay_save.assert_called_once()
    delay_arg = mock_ha.async_delay_save.call_args[0][1]
    assert delay_arg == 30


@pytest.mark.asyncio
async def test_save_debounced_data_func_returns_current_data():
    store, mock_ha = _make_store()
    await store.save_debounced()
    data_func = mock_ha.async_delay_save.call_args[0][0]
    assert data_func() is store._data


# --- bump sets quota_date ---


@pytest.mark.asyncio
async def test_bump_sets_quota_date():
    store, _ = _make_store()
    await store.bump_quota(DAY1)
    assert store._data["quota_date"] == "2026-06-30"


# --- mirror_sync_date ---


@pytest.mark.asyncio
async def test_mirror_sync_date_defaults_none():
    store, _ = _make_store()
    assert store.mirror_sync_date is None


@pytest.mark.asyncio
async def test_mark_mirror_synced_sets_utc_date_and_saves():
    store, mock_ha = _make_store()
    await store.mark_mirror_synced(DAY1)  # 2026-06-30 12:00 UTC
    assert store.mirror_sync_date == "2026-06-30"
    mock_ha.async_save.assert_called_once_with(store._data)


@pytest.mark.asyncio
async def test_mirror_sync_date_round_trips_from_stored():
    saved = {
        "last_solcast": {},
        "k_factors": {},
        "last_solcast_ts": None,
        "quota_date": None,
        "quota_used": 0,
        "last_poll_ts": None,
        "mirror_sync_date": "2026-06-29",
    }
    store, _ = _make_store(stored=saved)
    await store.load()
    assert store.mirror_sync_date == "2026-06-29"


from datetime import timedelta

RT = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_merge_poll_adds_buckets_with_fetched_stamp():
    store, _ = _make_store()
    fc = {RT: 1500.0, RT + timedelta(minutes=30): 1600.0}
    await store.merge_poll(fc, RT)
    r = store.solcast_retained
    assert r[RT]["w"] == 1500.0
    assert r[RT]["fetched"] == RT


@pytest.mark.asyncio
async def test_merge_poll_keeps_prior_and_updates_overlap():
    store, _ = _make_store()
    t1 = datetime(2026, 6, 30, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 6, 30, 11, 0, tzinfo=UTC)
    await store.merge_poll({t1: 1000.0}, t1)
    await store.merge_poll({t1: 1200.0, t2: 2000.0}, t2)
    r = store.solcast_retained
    assert r[t1]["w"] == 1200.0
    assert r[t1]["fetched"] == t2  # overlapping bucket re-stamped
    assert r[t2]["w"] == 2000.0


@pytest.mark.asyncio
async def test_merge_poll_expires_buckets_older_than_48h():
    store, _ = _make_store()
    old = datetime(2026, 6, 28, 10, 0, tzinfo=UTC)  # > 48 h before `new`
    new = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)
    await store.merge_poll({old: 500.0}, old)
    await store.merge_poll({new: 1000.0}, new)
    r = store.solcast_retained
    assert old not in r
    assert new in r


@pytest.mark.asyncio
async def test_migration_upgrades_flat_last_solcast_to_retained():
    saved = {
        "last_solcast": {"2026-06-30T10:00:00+00:00": 1500.0},
        "k_factors": {"2026-06-30T10:00:00+00:00": 1.2},
        "last_solcast_ts": "2026-06-30T09:44:00+00:00",
        "quota_used": 3,
    }
    store, _ = _make_store(stored=saved)
    await store.load()
    key = datetime.fromisoformat("2026-06-30T10:00:00+00:00")
    r = store.solcast_retained
    assert r[key]["w"] == 1500.0
    assert r[key]["fetched"] == datetime.fromisoformat("2026-06-30T09:44:00+00:00")
    assert store._data["schema_version"] == 2


@pytest.mark.asyncio
async def test_migration_is_idempotent_for_v2_data():
    saved = {
        "solcast_retained": {"2026-06-30T10:00:00+00:00": {"w": 1500.0, "fetched": "2026-06-30T09:44:00+00:00"}},
        "schema_version": 2,
        "quota_used": 1,
    }
    store, _ = _make_store(stored=saved)
    await store.load()
    key = datetime.fromisoformat("2026-06-30T10:00:00+00:00")
    assert store.solcast_retained[key]["w"] == 1500.0
    assert store._data["quota_used"] == 1
