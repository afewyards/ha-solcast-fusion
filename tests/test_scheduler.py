import sys
from unittest.mock import MagicMock

# Provide a real base class so OpenMeteoCoordinator(DataUpdateCoordinator) can be defined
class _FakeDUC:
    def __init__(self, *args, **kwargs):
        pass

_duc_mod = MagicMock()
_duc_mod.DataUpdateCoordinator = _FakeDUC

for _name, _mod in [
    ("homeassistant", MagicMock()),
    ("homeassistant.helpers", MagicMock()),
    ("homeassistant.helpers.update_coordinator", _duc_mod),
    ("homeassistant.helpers.event", MagicMock()),
    ("homeassistant.helpers.storage", MagicMock()),
    ("open_meteo_solar_forecast", MagicMock()),
    ("astral", MagicMock()),
    ("astral.sun", MagicMock()),
]:
    sys.modules.setdefault(_name, _mod)

from datetime import datetime, timedelta, timezone

from custom_components.ha_solcast_fusion.coordinator import next_due, solcast_interval

NOW = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
SUNRISE = datetime(2026, 6, 30, 5, 0, tzinfo=timezone.utc)
SUNSET = datetime(2026, 6, 30, 21, 0, tzinfo=timezone.utc)


def test_solcast_interval():
    # 18h / (8 - 2) = 3h
    assert solcast_interval(18, 8, 2) == timedelta(hours=3)


def test_next_due_none_at_night():
    night = datetime(2026, 6, 30, 22, 0, tzinfo=timezone.utc)
    assert next_due(night, SUNRISE, SUNSET, 6, 2, None, timedelta(hours=3)) is None


def test_next_due_none_quota_at_reserve():
    assert next_due(NOW, SUNRISE, SUNSET, 2, 2, None, timedelta(hours=3)) is None


def test_next_due_none_quota_below_reserve():
    assert next_due(NOW, SUNRISE, SUNSET, 1, 2, None, timedelta(hours=3)) is None


def test_next_due_restart_guard():
    # last_poll 10 min ago + 3h interval → due ~2h50m from now, not now.
    # That candidate (14:50 UTC) falls within daylight (sunrise 05:00, sunset 21:00),
    # so it should be returned unchanged.
    last_poll = NOW - timedelta(minutes=10)
    interval = timedelta(hours=3)
    result = next_due(NOW, SUNRISE, SUNSET, 6, 2, last_poll, interval)
    assert result == last_poll + interval
    assert result > NOW


def test_next_due_before_sunrise_defers_to_sunrise():
    # now is before sunrise → must not return now (which is pre-dawn); must return sunrise.
    before_dawn = SUNRISE - timedelta(hours=1)
    result = next_due(before_dawn, SUNRISE, SUNSET, 6, 2, None, timedelta(hours=3))
    assert result == SUNRISE


def test_next_due_none_when_cadence_candidate_after_sunset():
    # last_poll + interval lands after sunset → no more polls today.
    last_poll = SUNSET - timedelta(hours=1)
    interval = timedelta(hours=3)
    result = next_due(NOW, SUNRISE, SUNSET, 6, 2, last_poll, interval)
    assert result is None


def test_next_due_cadence_preserved_within_daylight():
    # last_poll + interval lands within daylight → cadence is preserved exactly.
    last_poll = NOW - timedelta(minutes=30)
    interval = timedelta(hours=2)
    result = next_due(NOW, SUNRISE, SUNSET, 6, 2, last_poll, interval)
    assert result == last_poll + interval
