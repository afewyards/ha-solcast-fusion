from __future__ import annotations

import math
import re
from datetime import datetime, UTC

from astral import Observer
from astral.sun import azimuth, elevation


def load_horizon(text: str) -> list[float] | None:
    """Load horizon profile from text, supporting sparse azimuth-elevation pairs.

    Accepts either:
    - Dense format: one elevation per line (evenly spaced azimuths)
    - Sparse format: "azimuth<tab>elevation" pairs, interpolated to 360 values
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    # Detect format: sparse if any line has whitespace separator
    if any("\t" in line or "  " in line or " " in line for line in lines):
        return _parse_sparse(lines)

    # Dense format: one value per line
    return [float(line) for line in lines]


def _parse_sparse(lines: list[str]) -> list[float]:
    """Parse sparse azimuth-elevation pairs and interpolate to 360 degrees."""
    points: list[tuple[float, float]] = []
    for line in lines:
        parts = re.split(r"[\t\s,;]+", line.strip())
        if len(parts) >= 2:
            az, el = float(parts[0]), float(parts[1])
            points.append((az % 360, el))

    if not points:
        return [0.0] * 360

    # Sort by azimuth
    points.sort(key=lambda p: p[0])

    # Ensure wrap-around: if no point at 360, copy point at 0
    if points[0][0] > 0:
        # Wrap last point to before 0
        points.insert(0, (points[-1][0] - 360, points[-1][1]))
    if points[-1][0] < 360:
        # Wrap first point to after 360
        points.append((points[0][0] + 360, points[0][1]))

    # Interpolate to 360 values (one per degree)
    result = []
    for deg in range(360):
        # Find surrounding points
        for i in range(len(points) - 1):
            if points[i][0] <= deg <= points[i + 1][0]:
                az1, el1 = points[i]
                az2, el2 = points[i + 1]
                if az2 == az1:
                    result.append(el1)
                else:
                    t = (deg - az1) / (az2 - az1)
                    result.append(el1 + t * (el2 - el1))
                break
        else:
            result.append(0.0)

    return result


def horizon_at(profile: list[float], azimuth_deg: float) -> float:
    n = len(profile)
    step = 360.0 / n
    # Normalise azimuth to [0, 360)
    az = azimuth_deg % 360.0
    idx_f = az / step
    lo = math.floor(idx_f) % n
    hi = (lo + 1) % n
    frac = idx_f - math.floor(idx_f)
    return profile[lo] + frac * (profile[hi] - profile[lo])


def is_shaded(profile: list[float], sun_az: float, sun_el: float) -> bool:
    return sun_el < horizon_at(profile, sun_az)


def apply_mask(
    blended: dict,
    profile: list[float] | None,
    lat: float,
    lon: float,
    diffuse: float,
) -> dict:
    if profile is None:
        return blended

    obs = Observer(latitude=lat, longitude=lon)
    result = {}
    for bucket, value in blended.items():
        dt = datetime.fromtimestamp(bucket, tz=UTC) if isinstance(bucket, (int, float)) else bucket
        az = azimuth(obs, dt)
        el = elevation(obs, dt)
        result[bucket] = value * diffuse if is_shaded(profile, az, el) else value
    return result
