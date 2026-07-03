from datetime import datetime, timezone, timedelta
from custom_components.ha_solcast_fusion import combiner as c

UTC = timezone.utc
def dt(h, m=0): return datetime(2026, 6, 30, h, m, tzinfo=UTC)

def test_normalize_solcast_shifts_period_end_to_start_and_kw_to_w():
    slots = [{"period_end": "2026-06-30T10:30:00Z", "pv_estimate": 2.0}]
    out = c.normalize_solcast(slots)
    assert out == {dt(10, 0): 2000.0}

def test_compute_k_clamps():
    assert c.compute_k(1000, 3000, 0.5, 2.0) == 2.0      # 3.0 clamped
    assert c.compute_k(1000, 100, 0.5, 2.0) == 0.5       # 0.1 clamped
    assert c.compute_k(1000, 1500, 0.5, 2.0) == 1.5

def test_compute_k_guards_zero_negative_and_nonfinite():
    assert c.compute_k(0.0, 1000, 0.5, 2.0) is None
    assert c.compute_k(float("nan"), 1000, 0.5, 2.0) is None
    assert c.compute_k(1000, -5, 0.5, 2.0) is None       # negative → guard, not clamp

def test_decay_halflife():
    assert c.decay_k(2.0, 0, 7200) == 2.0
    assert abs(c.decay_k(2.0, 7200, 7200) - 1.5) < 1e-9  # one half-life → halfway to 1.0

def test_blend_scales_where_k_present():
    om = {dt(12): 4000.0}; k = {dt(12): 1.5}
    assert c.blend(om, k, {}, 0, 7200) == {dt(12): 6000.0}

def test_blend_substitutes_solcast_at_om_zero():
    om = {dt(6): 0.0}; solc = {dt(6): 300.0}
    assert c.blend(om, {}, solc, 0, 7200) == {dt(6): 300.0}

def test_blend_keeps_om_when_no_info():
    om = {dt(13): 4000.0}
    assert c.blend(om, {}, {}, 0, 7200) == {dt(13): 4000.0}

def test_blend_substitutes_when_om_collapses_despite_stale_k():
    # OM dropped to ~0 between polls but a k still exists for this bucket
    om = {dt(15): 0.0}; k = {dt(15): 1.8}; solc = {dt(15): 250.0}
    assert c.blend(om, k, solc, 0, 7200) == {dt(15): 250.0}

def test_decay_k_guards_zero_halflife_and_negative_age():
    assert c.decay_k(2.0, 5, 0) == 2.0          # halflife 0 → no decay, no ZeroDivisionError
    assert c.decay_k(2.0, -100, 7200) == 2.0    # negative age clamped to 0

def test_is_clamped_flags_out_of_band_ratio():
    assert c.is_clamped(1000, 3000, 0.5, 2.0) is True    # raw 3.0 > 2.0
    assert c.is_clamped(1000, 1500, 0.5, 2.0) is False
    assert c.is_clamped(0.0, 1000, 0.5, 2.0) is False    # undefined → not "clamped"

def test_resample_30min_interpolates_hourly_to_half_hourly():
    hourly = {dt(10): 1000.0, dt(11): 2000.0}
    out = c.resample_30min(hourly)
    assert out[dt(10, 0)] == 1000.0
    assert out[dt(10, 30)] == 1500.0            # linear midpoint
    assert out[dt(11, 0)] == 2000.0

def test_resample_30min_floors_offgrid_keys_to_utc_buckets():
    out = c.resample_30min({dt(10, 15): 800.0})
    assert dt(10, 0) in out

def test_resample_30min_aligns_45_offset_input_to_utc_grid():
    # Nepal-style +05:45 offset: local :00/:15/:30/:45 grid maps to UTC
    # :15/:45, NOT UTC :00/:30. Buckets must still land on UTC :00/:30.
    NPT = timezone(timedelta(hours=5, minutes=45))
    def local(h, m): return datetime(2026, 6, 30, h, m, tzinfo=NPT)
    curve = {
        local(10, 0): 100.0, local(10, 15): 200.0,
        local(10, 30): 300.0, local(10, 45): 400.0,
        local(11, 0): 500.0, local(11, 15): 600.0,
        local(11, 30): 700.0, local(11, 45): 800.0,
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
