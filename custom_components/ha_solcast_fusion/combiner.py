from datetime import datetime, timedelta, UTC

EPS = 1.0  # watts
HALF_BUCKET = timedelta(minutes=30)


def rollups(blended: dict, now: datetime, tz) -> dict:
    today_local = now.astimezone(tz).date()
    tomorrow_local = today_local + timedelta(days=1)

    today_buckets = {t: w for t, w in blended.items() if t.astimezone(tz).date() == today_local}
    tomorrow_buckets = {t: w for t, w in blended.items() if t.astimezone(tz).date() == tomorrow_local}

    def _kwh(buckets):
        return sum(w * 0.5 / 1000.0 for w in buckets.values())

    def _peak(buckets):
        if not buckets:
            return None
        return max(buckets, key=buckets.__getitem__).astimezone(tz)

    today_remaining = {t: w for t, w in today_buckets.items() if t + HALF_BUCKET >= now}

    now_hour = now.replace(minute=0, second=0, microsecond=0)
    current_hour = {t: w for t, w in blended.items() if now_hour <= t < now_hour + timedelta(hours=1)}
    next_hour = {t: w for t, w in blended.items() if now_hour + timedelta(hours=1) <= t < now_hour + timedelta(hours=2)}

    current_bucket = _floor_30(now)

    return {
        "today_kwh": _kwh(today_buckets),
        "today_remaining_kwh": _kwh(today_remaining),
        "tomorrow_kwh": _kwh(tomorrow_buckets),
        "peak_time_today": _peak(today_buckets),
        "peak_time_tomorrow": _peak(tomorrow_buckets),
        "current_hour_kwh": _kwh(current_hour),
        "next_hour_kwh": _kwh(next_hour),
        "power_now": blended.get(current_bucket, 0.0),
    }


def normalize_solcast(slots):
    out = {}
    for s in slots:
        end = datetime.fromisoformat(s["period_end"].replace("Z", "+00:00"))
        out[end - HALF_BUCKET] = float(s["pv_estimate"]) * 1000.0
    return out


def _floor_30(t):
    return t.replace(minute=0 if t.minute < 30 else 30, second=0, microsecond=0)


def resample_30min(curve):
    """Any tz-aware curve -> 30-min buckets on the UTC :00/:30 grid, linear interp.

    Keys are normalized to UTC before flooring so Open-Meteo buckets (site-local
    fixed-offset) align with Solcast's UTC grid for every timezone, including
    :45-offset zones. Naive datetimes are assumed UTC.
    """
    if not curve:
        return {}

    def _utc(k):
        return (k if k.tzinfo else k.replace(tzinfo=UTC)).astimezone(UTC)

    pts = sorted((_utc(k), float(v)) for k, v in curve.items())  # [(dt, w), ...]
    start, end = _floor_30(pts[0][0]), _floor_30(pts[-1][0])
    out, t = {}, start
    while t <= end:
        prev = max((p for p in pts if p[0] <= t), default=pts[0])
        nxt = min((p for p in pts if p[0] >= t), default=pts[-1])
        if prev[0] == nxt[0]:
            out[t] = float(prev[1])
        else:
            span = (nxt[0] - prev[0]).total_seconds()
            frac = (t - prev[0]).total_seconds() / span
            out[t] = float(prev[1]) + (float(nxt[1]) - float(prev[1])) * frac
        t += HALF_BUCKET
    return out


def freshness_weight(age_s: float, halflife_s: float, w_min: float, w_max: float) -> float:
    if halflife_s <= 0:
        w = w_max
    else:
        w = w_max * 0.5 ** (max(0.0, age_s) / halflife_s)
    return max(w_min, min(w_max, w))


def daily_bias(solcast: dict, om: dict, lo: float, hi: float) -> float:
    """Sum(solcast)/Sum(om) over overlapping buckets, clamped; 1.0 without overlap."""
    keys = solcast.keys() & om.keys()
    sum_om = sum(om[t] for t in keys)
    if sum_om <= EPS:
        return 1.0
    sum_sc = sum(solcast[t] for t in keys)
    return max(lo, min(hi, sum_sc / sum_om))


def blend(
    om: dict,
    solcast: dict,
    fetched: dict,
    now: datetime,
    halflife_s: float,
    w_min: float,
    w_max: float,
    bias_lo: float,
    bias_hi: float,
) -> dict:
    """Freshness-weighted Solcast/OM blend.

    Solcast bucket + OM bucket -> w*solcast + (1-w)*om, w decaying with fetch age.
    Solcast bucket, no OM      -> solcast as-is (OM lacks the shoulder bucket).
    No Solcast bucket          -> om * daily_bias (today's magnitude calibration).
    """
    bias = daily_bias(solcast, om, bias_lo, bias_hi)
    out: dict = {}
    for t in om.keys() | solcast.keys():
        sc = solcast.get(t)
        om_w = om.get(t)
        if sc is not None:
            if om_w is None:
                out[t] = sc
            else:
                age_s = (now - fetched[t]).total_seconds() if t in fetched else 0.0
                w = freshness_weight(age_s, halflife_s, w_min, w_max)
                out[t] = w * sc + (1.0 - w) * om_w
        else:
            out[t] = (om_w if om_w is not None else 0.0) * bias
    return out


def pct_solcast_covered(om: dict, solcast: dict) -> float:
    """Fraction of daytime buckets that have a retained Solcast value.

    Daytime buckets are normally derived from OM (OM > EPS). If OM has no
    signal (e.g. an outage collapses the curve to {}), fall back to
    Solcast's own above-EPS buckets so an OM outage doesn't zero out
    coverage that Solcast still fully has.
    """
    day = [t for t, w in om.items() if w > EPS]
    if not day:
        day = [t for t, w in solcast.items() if w > EPS]
    if not day:
        return 0.0
    return sum(1 for t in day if t in solcast) / len(day)
