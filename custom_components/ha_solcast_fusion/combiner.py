import math
from datetime import datetime, timedelta, UTC

EPS = 1.0  # watts
HALF_BUCKET = timedelta(minutes=30)


def daily_scalar(om: dict, solcast: dict, k_min: float, k_max: float) -> float:
    overlap_keys = om.keys() & solcast.keys()
    sum_om = sum(om[t] for t in overlap_keys)
    if sum_om <= EPS:
        return 1.0
    sum_sc = sum(solcast[t] for t in overlap_keys)
    return max(k_min, min(k_max, sum_sc / sum_om))


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


def compute_k(om_w, solcast_w, k_min, k_max):
    if not math.isfinite(om_w) or not math.isfinite(solcast_w) or om_w <= EPS or solcast_w < 0:
        return None
    return max(k_min, min(k_max, solcast_w / om_w))


def is_clamped(om_w, solcast_w, k_min, k_max):
    if om_w <= EPS or solcast_w < 0 or not math.isfinite(om_w) or not math.isfinite(solcast_w):
        return False
    raw = solcast_w / om_w
    return raw < k_min or raw > k_max


def decay_k(k, age_s, halflife_s):
    if halflife_s <= 0:
        return k  # no-decay / divide-by-zero guard
    age_s = max(0.0, age_s)  # clock-skew guard
    return 1.0 + (k - 1.0) * 0.5 ** (age_s / halflife_s)


def blend(om, k_by_bucket, solcast, age_s, halflife_s):
    out = {}
    for t, om_w in om.items():
        if t in k_by_bucket and om_w > EPS:  # collapsed-OM falls through
            out[t] = om_w * decay_k(k_by_bucket[t], age_s, halflife_s)
        elif om_w <= EPS and t in solcast:
            out[t] = solcast[t]  # OM≈0 -> substitute Solcast
        else:
            out[t] = om_w
    for t, sc_w in solcast.items():  # shoulder buckets OM lacks
        if t not in out:
            out[t] = sc_w
    return out
