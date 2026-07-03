from custom_components.ha_solcast_fusion import horizon as h


def test_load_infers_step_and_skips_blanks():
    prof = h.load_horizon("0\n10\n\n20\n30\n")  # 4 values → step 90°
    assert prof == [0.0, 10.0, 20.0, 30.0]


def test_load_empty_returns_none():
    assert h.load_horizon("\n  \n") is None


def test_horizon_at_interpolates():
    prof = [0.0, 20.0, 0.0, 0.0]  # N=0,E=20,S=0,W=0 (step 90)
    assert abs(h.horizon_at(prof, 45) - 10.0) < 1e-9  # halfway N→E


def test_is_shaded():
    prof = [30.0, 30.0, 30.0, 30.0]
    assert h.is_shaded(prof, 90, 20) is True
    assert h.is_shaded(prof, 90, 40) is False


def test_apply_mask_none_is_identity():
    curve = {1: 100.0}
    assert h.apply_mask(curve, None, 52.0, 4.9, 0.15) == curve
