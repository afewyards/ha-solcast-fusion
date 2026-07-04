from datetime import datetime, timezone, timedelta, UTC
from custom_components.ha_solcast_fusion import combiner as c


def dt(h, m=0):
    return datetime(2026, 6, 30, h, m, tzinfo=UTC)


def test_normalize_solcast_shifts_period_end_to_start_and_kw_to_w():
    slots = [{"period_end": "2026-06-30T10:30:00Z", "pv_estimate": 2.0}]
    out = c.normalize_solcast(slots)
    assert out == {dt(10, 0): 2000.0}


def test_freshness_weight_fresh_returns_wmax():
    assert c.freshness_weight(0.0, 7200, 0.5, 0.9) == 0.9


def test_freshness_weight_one_halflife_clamped_to_floor():
    # 0.9 * 0.5^1 = 0.45 -> clamped up to w_min 0.5
    assert c.freshness_weight(7200, 7200, 0.5, 0.9) == 0.5


def test_freshness_weight_partial_decay():
    # 0.9 * 0.5^0.5 = 0.6364, inside [0.5, 0.9]
    assert abs(c.freshness_weight(3600, 7200, 0.5, 0.9) - 0.63640) < 1e-4


def test_freshness_weight_zero_halflife_holds_wmax():
    assert c.freshness_weight(9999, 0, 0.5, 0.9) == 0.9


def test_daily_bias_ratio_over_overlap():
    om = {dt(10): 2000.0, dt(10, 30): 2000.0}
    sc = {dt(10): 3000.0, dt(10, 30): 3000.0}
    assert c.daily_bias(sc, om, 0.5, 2.0) == 1.5


def test_daily_bias_clamps_high_and_returns_one_without_overlap():
    assert c.daily_bias({dt(10): 500.0}, {dt(10): 100.0}, 0.5, 2.0) == 2.0
    assert c.daily_bias({dt(9): 500.0}, {dt(10): 100.0}, 0.5, 2.0) == 1.0


def test_blend_fresh_solcast_dominates():
    now = dt(12)
    out = c.blend({dt(12): 1000.0}, {dt(12): 2000.0}, {dt(12): dt(12)}, now, 7200, 0.5, 0.9, 0.5, 2.0)
    assert out[dt(12)] == 1900.0  # 0.9*2000 + 0.1*1000


def test_blend_stale_solcast_floor_weight():
    now = dt(12)
    out = c.blend({dt(12): 1000.0}, {dt(12): 2000.0}, {dt(12): dt(6)}, now, 7200, 0.5, 0.9, 0.5, 2.0)
    assert out[dt(12)] == 1500.0  # age 6h, w clamped to 0.5 -> 0.5*2000 + 0.5*1000


def test_blend_no_solcast_bucket_uses_om_times_bias():
    now = dt(12)
    om = {dt(10): 1000.0, dt(12): 1000.0}
    sc = {dt(10): 1500.0}
    fetched = {dt(10): dt(12)}
    out = c.blend(om, sc, fetched, now, 7200, 0.5, 0.9, 0.5, 2.0)
    assert out[dt(12)] == 1500.0  # daily_bias 1.5 * om 1000


def test_blend_solcast_only_bucket_passthrough():
    now = dt(12)
    out = c.blend({}, {dt(7): 300.0}, {dt(7): dt(12)}, now, 7200, 0.5, 0.9, 0.5, 2.0)
    assert out[dt(7)] == 300.0  # OM lacks bucket -> Solcast as-is


def test_pct_solcast_covered_daytime_fraction():
    om = {dt(3): 0.0, dt(10): 1000.0, dt(11): 1000.0}
    assert c.pct_solcast_covered(om, {dt(10): 900.0}) == 0.5  # 1 of 2 daytime buckets
    assert c.pct_solcast_covered({dt(3): 0.0}, {}) == 0.0     # no daytime buckets


def test_resample_30min_interpolates_hourly_to_half_hourly():
    hourly = {dt(10): 1000.0, dt(11): 2000.0}
    out = c.resample_30min(hourly)
    assert out[dt(10, 0)] == 1000.0
    assert out[dt(10, 30)] == 1500.0  # linear midpoint
    assert out[dt(11, 0)] == 2000.0


def test_resample_30min_floors_offgrid_keys_to_utc_buckets():
    out = c.resample_30min({dt(10, 15): 800.0})
    assert dt(10, 0) in out


def test_resample_30min_aligns_45_offset_input_to_utc_grid():
    # Nepal-style +05:45 offset: local :00/:15/:30/:45 grid maps to UTC
    # :15/:45, NOT UTC :00/:30. Buckets must still land on UTC :00/:30.
    NPT = timezone(timedelta(hours=5, minutes=45))

    def local(h, m):
        return datetime(2026, 6, 30, h, m, tzinfo=NPT)

    curve = {
        local(10, 0): 100.0,
        local(10, 15): 200.0,
        local(10, 30): 300.0,
        local(10, 45): 400.0,
        local(11, 0): 500.0,
        local(11, 15): 600.0,
        local(11, 30): 700.0,
        local(11, 45): 800.0,
        local(12, 0): 900.0,
    }
    out = c.resample_30min(curve)
    assert out
    for k in out:
        assert k.tzinfo is not None
        u = k.astimezone(UTC)
        assert u.minute in (0, 30)
        assert u.second == 0


def test_resample_30min_utc_input_unaffected():
    hourly = {dt(10): 1000.0, dt(11): 2000.0}
    out = c.resample_30min(hourly)
    assert out == {dt(10, 0): 1000.0, dt(10, 30): 1500.0, dt(11, 0): 2000.0}
