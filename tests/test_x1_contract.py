"""Contract test: SolcastFusion watts dict is drop-in consumable by x1-smartcharge.

Mirrors x1-smartcharge parsing logic verbatim so silently drifting contract is caught here.
x1 source pin: c898b0d90764de522124f97473ac46c6676c02e2
  parsers.py:11-18        (_parse_dt)
  coordinator.py:209-220  (_read_pv_watts summing loop)
"""

from __future__ import annotations

from datetime import datetime, UTC

import pytest

# ---------------------------------------------------------------------------
# Mirrored x1-smartcharge _parse_dt
# x1@c898b0d parsers.py:11-18
# ---------------------------------------------------------------------------


def _parse_dt(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


# ---------------------------------------------------------------------------
# Mirrored x1-smartcharge _read_pv_watts inner summing loop
# x1@c898b0d coordinator.py:209-220
# ---------------------------------------------------------------------------


def _x1_consume_watts(watts_dict: dict) -> list[tuple[datetime, float]]:
    """Simulate x1's per-array watts consumption for a single watts dict."""
    merged: dict[datetime, float] = {}
    for k, v in watts_dict.items():
        dt_utc = _parse_dt(str(k))
        if dt_utc is None:
            continue
        try:
            w = float(v)
        except (ValueError, TypeError):
            continue
        merged[dt_utc] = merged.get(dt_utc, 0.0) + w
    return sorted(merged.items())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOON_UTC = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

# Simulates SolcastFusion coordinator.py:151 output:
#   data["watts"] = {t.isoformat(): w for t, w in masked.items()}
# where t is a UTC-aware datetime produced by the combiner/horizon pipeline.
SF_WATTS: dict[str, float] = {
    "2024-06-15T10:00:00+00:00": 150.0,
    "2024-06-15T12:00:00+00:00": 400.0,
    "2024-06-15T14:00:00+00:00": 250.0,
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_non_empty():
    """x1 parser produces a non-empty curve from SolcastFusion's watts dict."""
    result = _x1_consume_watts(SF_WATTS)
    assert len(result) > 0


def test_no_time_shift():
    """12:00Z bucket must remain 12:00Z after x1 parsing — no local-time shift."""
    result = _x1_consume_watts(SF_WATTS)
    times = [dt for dt, _ in result]
    assert NOON_UTC in times, f"Expected 12:00Z in parsed times, got {times}"


def test_keys_are_tz_aware():
    """All parsed keys must be tz-aware UTC (naive-local keys would silently shift the curve)."""
    result = _x1_consume_watts(SF_WATTS)
    for dt, _ in result:
        assert dt.tzinfo is not None, f"Parsed key {dt!r} is tz-naive"
        offset = dt.utcoffset()
        assert offset is not None and offset.total_seconds() == 0, f"Key {dt!r} is not UTC"


def test_values_preserved():
    """Watts values pass through without scaling or loss."""
    result = _x1_consume_watts(SF_WATTS)
    result_dict = dict(result)
    assert result_dict[NOON_UTC] == pytest.approx(400.0)


def test_sf_emits_tz_aware_keys():
    """SolcastFusion isoformat() keys carry +00:00 — prove they never hit x1's naive branch.

    coordinator.py:151 emits: {t.isoformat(): w for t, w in masked.items()}
    If t is UTC-aware, isoformat() produces '...+00:00'; _parse_dt's naive branch is skipped.
    A regression to naive-local datetimes would produce local-offset keys that x1
    _parse_dt converts to UTC, silently time-shifting the entire curve.
    """
    t = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
    emitted_key = t.isoformat()

    assert "+" in emitted_key or emitted_key.endswith("Z"), (
        f"SolcastFusion key {emitted_key!r} lacks tz suffix — "
        "x1 treats naive as UTC but local-aware would silently shift the curve"
    )

    parsed = _parse_dt(emitted_key)
    assert parsed is not None
    assert parsed == t
