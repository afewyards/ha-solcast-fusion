from custom_components.ha_solcast_fusion import horizon as h


def test_load_infers_step_and_skips_blanks():
    prof = h.load_horizon("0\n10\n\n20\n30\n")  # 4 values → step 90°
    assert prof == [0.0, 10.0, 20.0, 30.0]


def test_load_empty_returns_none():
    assert h.load_horizon("\n  \n") is None


def test_horizon_at_interpolates():
    prof = [0.0, 20.0, 0.0, 0.0]  # N=0,E=20,S=0,W=0 (step 90)
    assert abs(h.horizon_at(prof, 45) - 10.0) < 1e-9  # halfway N→E


from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import patch

import pytest

_SEED = Path(__file__).resolve().parent / "fixtures" / "horizon_seed.txt"


def test_transmission_floor_when_beam_blocked():
    assert h.transmission(10.0, 20.0, 6.0, 0.18) == pytest.approx(0.18)


def test_transmission_full_when_well_clear():
    assert h.transmission(40.0, 20.0, 6.0, 0.18) == 1.0  # (40-20)/6 = 3.3 -> clamp 1.0


def test_transmission_linear_within_shoulder():
    assert h.transmission(23.0, 20.0, 6.0, 0.18) == pytest.approx(0.5)  # (23-20)/6


def test_transmission_regression_fixture_real_horizon():
    prof = h.load_horizon(_SEED.read_text())
    # az 136, clear, sun el ~54 -> ~0.62 (re-fit; NOT the old 0.09 binary*diffuse)
    assert h.transmission(54.0, h.horizon_at(prof, 136), 6.0, 0.18) == pytest.approx(0.62, abs=0.02)
    # az ~90, el 25 -> floor
    assert h.transmission(25.0, h.horizon_at(prof, 90), 6.0, 0.18) == pytest.approx(0.18)
    # az 210, el 55 -> fully open
    assert h.transmission(55.0, h.horizon_at(prof, 210), 6.0, 0.18) == 1.0


def test_load_horizon_skips_comment_lines():
    prof = h.load_horizon("# header\n0\t10\n180\t10\n")
    assert prof is not None
    assert len(prof) == 360


def test_apply_transmission_none_is_identity():
    curve = {datetime(2026, 6, 30, 12, tzinfo=UTC): 100.0}
    assert h.apply_transmission(curve, None, 52.0, 4.9, 6.0, 0.18) == curve


def test_apply_transmission_multiplies_by_transmission():
    prof = h.load_horizon(_SEED.read_text())
    t = datetime(2026, 6, 30, 12, tzinfo=UTC)
    with (
        patch("custom_components.ha_solcast_fusion.horizon.azimuth", return_value=136.0),
        patch("custom_components.ha_solcast_fusion.horizon.elevation", return_value=54.0),
    ):
        out = h.apply_transmission({t: 1000.0}, prof, 52.455, 4.822, 6.0, 0.18)
    assert out[t] == pytest.approx(617.0, abs=25.0)
