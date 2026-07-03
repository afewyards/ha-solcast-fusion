import pytest
from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo
from custom_components.ha_solcast_fusion import combiner as c

UTC = timezone.utc
AMS = ZoneInfo("Europe/Amsterdam")


def utc(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


# ── daily_scalar ─────────────────────────────────────────────────────────────

def test_daily_scalar_ratio():
    om = {utc(2026, 6, 30, 10): 2000.0, utc(2026, 6, 30, 10, 30): 2000.0}
    sc = {utc(2026, 6, 30, 10): 3000.0, utc(2026, 6, 30, 10, 30): 3000.0}
    # Σsc/Σom = 6000/4000 = 1.5
    assert c.daily_scalar(om, sc, 0.5, 2.0) == pytest.approx(1.5)


def test_daily_scalar_returns_1_when_om_zero():
    om = {utc(2026, 6, 30, 10): 0.0}
    sc = {utc(2026, 6, 30, 10): 1000.0}
    assert c.daily_scalar(om, sc, 0.5, 2.0) == pytest.approx(1.0)


def test_daily_scalar_clamps_high():
    om = {utc(2026, 6, 30, 10): 100.0}
    sc = {utc(2026, 6, 30, 10): 500.0}  # ratio 5.0, clamped to 2.0
    assert c.daily_scalar(om, sc, 0.5, 2.0) == pytest.approx(2.0)


def test_daily_scalar_clamps_low():
    om = {utc(2026, 6, 30, 10): 1000.0}
    sc = {utc(2026, 6, 30, 10): 100.0}  # ratio 0.1, clamped to 0.5
    assert c.daily_scalar(om, sc, 0.5, 2.0) == pytest.approx(0.5)


def test_daily_scalar_uses_overlap_only():
    # om has extra bucket not in solcast; only overlap counts
    om = {utc(2026, 6, 30, 10): 1000.0, utc(2026, 6, 30, 10, 30): 1000.0}
    sc = {utc(2026, 6, 30, 10): 1500.0}  # only first bucket overlaps → 1500/1000
    assert c.daily_scalar(om, sc, 0.5, 2.0) == pytest.approx(1.5)


# ── rollups ───────────────────────────────────────────────────────────────────

def test_rollups_flat_day_sums_to_4kwh():
    # 2 × 4000 W × 0.5 h = 4000 Wh = 4.0 kWh
    now = utc(2026, 6, 30, 9)
    blended = {
        utc(2026, 6, 30, 10): 4000.0,
        utc(2026, 6, 30, 10, 30): 4000.0,
    }
    result = c.rollups(blended, now, AMS)
    assert result["today_kwh"] == pytest.approx(4.0)


def test_rollups_today_remaining_keeps_partial_bucket():
    # now = 10:15 UTC; bucket 10:00 ends 10:30 (>= now) → included
    # bucket 09:30 ends 10:00 (< now) → excluded
    now = utc(2026, 6, 30, 10, 15)
    blended = {
        utc(2026, 6, 30, 9, 30): 2000.0,   # end 10:00 → excluded
        utc(2026, 6, 30, 10, 0): 2000.0,   # end 10:30 → included (partial)
        utc(2026, 6, 30, 10, 30): 2000.0,  # end 11:00 → included
    }
    result = c.rollups(blended, now, AMS)
    # 2 buckets × 2000 W × 0.5 / 1000 = 2.0 kWh
    assert result["today_remaining_kwh"] == pytest.approx(2.0)


def test_rollups_peak_time_returns_local_timestamp():
    # 11:00 UTC = 13:00 Amsterdam (CEST = UTC+2) → peak
    now = utc(2026, 6, 30, 9)
    blended = {
        utc(2026, 6, 30, 10): 2000.0,
        utc(2026, 6, 30, 11): 5000.0,  # peak
        utc(2026, 6, 30, 12): 3000.0,
    }
    result = c.rollups(blended, now, AMS)
    peak = result["peak_time_today"]
    assert peak is not None
    assert peak.tzinfo is not None
    assert peak.hour == 13  # 11:00 UTC → 13:00 CEST


def test_rollups_dst_fall_back_50_buckets_no_error():
    # 2026-10-25 Amsterdam: clocks back 1h → 25-hour day → 50 × 30-min UTC buckets
    # Local midnight = Oct 24 22:00 UTC (still CEST = UTC+2)
    start_utc = utc(2026, 10, 24, 22)
    blended = {}
    t = start_utc
    for _ in range(50):
        blended[t] = 1000.0
        t += timedelta(minutes=30)

    now = utc(2026, 10, 25, 9)
    result = c.rollups(blended, now, AMS)

    # All 50 buckets belong to Oct 25 local; 50 × 1000 × 0.5 / 1000 = 25.0 kWh
    assert result["today_kwh"] == pytest.approx(25.0)


def test_rollups_dst_spring_forward_46_buckets_no_error():
    # 2026-03-29 Amsterdam: clocks forward 1h → 23-hour day → 46 × 30-min UTC buckets
    # Local midnight = Mar 28 23:00 UTC (CET = UTC+1)
    start_utc = utc(2026, 3, 28, 23)
    blended = {}
    t = start_utc
    for _ in range(46):
        blended[t] = 1000.0
        t += timedelta(minutes=30)

    now = utc(2026, 3, 29, 9)
    result = c.rollups(blended, now, AMS)

    # All 46 buckets belong to Mar 29 local; 46 × 1000 × 0.5 / 1000 = 23.0 kWh
    assert result["today_kwh"] == pytest.approx(23.0)
