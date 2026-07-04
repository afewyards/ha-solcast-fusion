# SolcastFusion

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/v/release/afewyards/ha-solcast-fusion?include_prereleases)](https://github.com/afewyards/ha-solcast-fusion/releases)

A Home Assistant custom integration that produces **one calibrated PV-production forecast** by fusing two upstream solar APIs:

- **[Open-Meteo Solar Forecast](https://open-meteo.com/)** — free, no API key, unlimited. Refreshes often and tracks moving cloud cover, so it provides the *shape* of the forecast.
- **[Solcast Rooftop PV](https://solcast.com/)** — high accuracy, but the hobbyist free tier is capped at ~10 calls/day. It provides the *magnitude* (calibration).

The goal: **Solcast-grade accuracy at Open-Meteo refresh rates**, while staying inside the Solcast daily call budget.

SolcastFusion is a **drop-in replacement** for the official `open_meteo_solar_forecast` integration — it mirrors the same sensor keys, units, and `watts` attribute, so any consumer (dashboards, energy automations, EV/battery smart-charging) works unchanged.

---

## How it works

SolcastFusion keeps a **rolling, freshness-weighted blend** of both forecasts, then applies **your local horizon shading** on top. Solcast supplies the trusted shape and magnitude; the horizon layer models what neither API can see:

1. Both forecasts are aligned to a common 30-minute grid keyed by **absolute UTC instants** (DST-safe — no duplicated or dropped periods).
2. Each Solcast poll is **merged into a retained per-period curve** (kept ~48 h), so calibration from earlier in the day is never overwritten by a later poll.
3. Per period the base is `base(t) = w·solcast(t) + (1 − w)·openmeteo(t)`, with the Solcast weight `w = clamp(w_max · 0.5^(age/half-life), w_min, w_max)` — Solcast-dominant when fresh, still leaning Solcast when stale (floor `w_min`), since Open-Meteo is the one that drifts.
4. Where no Solcast is retained for a period, the base is `openmeteo(t) × daily_bias` — the Solcast⁄Open-Meteo daily-total ratio (clamped `[k_min, k_max]`) — so today's magnitude calibration carries into uncovered periods.
5. The base is then scaled by a **graded horizon transmission** (below), and the whole output is recomputed on **every** fresh Open-Meteo poll (~20 min).

### Quota-aware Solcast polling

Solcast is polled on a **daylight-aware budget scheduler**, not a fixed interval:

- One poll near **sunrise**, then spread across daylight at an adaptive interval so long summer days never overrun the cap.
- **Never polls at night** — one call returns the whole horizon (up to +14 days), so the last daylight poll already carries tomorrow's curve.
- A persisted daily counter enforces a **hard quota guard** (default cap 10, no reserve — the full free-tier budget), reset at 00:00 UTC.
- Restarts **never burn quota or lose calibration** — the retained Solcast curve and call counter are persisted.
- If the quota is exhausted or Solcast is down, it falls back to **pure Open-Meteo** rather than reporting zero.

### Near-field horizon shading (optional)

Neither free API knows about *your* trees and buildings. Point SolcastFusion at a horizon-elevation profile and it applies a **graded transmission** to the blended curve: for each period `transmission = clamp((sun_elevation − horizon(azimuth)) / shoulder, floor, 1)` — full sun well above the obstruction, a soft ramp across its edge, and a `floor` (diffuse-only) fraction when the beam is fully blocked (see [Horizon file](#horizon-file)).

---

## Installation

### HACS (recommended)

1. In HACS, open the three-dot menu → **Custom repositories**.
2. Add `https://github.com/afewyards/ha-solcast-fusion` with category **Integration**.
3. Search for **SolcastFusion**, install it, and **restart Home Assistant**.
4. Go to **Settings → Devices & Services → Add Integration** and search for **SolcastFusion**.

### Manual

1. Copy `custom_components/ha_solcast_fusion` into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.
3. Add the integration from **Settings → Devices & Services**.

---

## Configuration

You only need a **Solcast API key** — the PV geometry is pulled from Solcast automatically.

1. **API key** — paste your Solcast API key. The setup call reads your rooftop site list and **does not consume your daily forecast quota**.
2. **Choose your site** — pick a rooftop site (skipped automatically if you only have one).
3. **Confirm** — latitude, longitude, tilt, azimuth, DC peak and AC limit are read from Solcast and shown for review.

> Solcast is treated as the **source of truth** for geometry. A **weekly** background check re-reads the site and mirrors any changes into the Open-Meteo config in place — so if you edit your array on the Solcast dashboard, the calibration never silently drifts. It spends one Solcast call from the daily budget on the day it runs, and defers if the budget is already exhausted. No manual reconfigure needed.

You can re-enter or change your API key later via the integration's **Reconfigure** action.

### Options

Open **Configure** on the integration to tune behaviour. Every option has a safe default — you can ignore this panel entirely.

| Option | Default | Description |
|--------|---------|-------------|
| Horizon mask file path (optional) | *(none)* | Path to a horizon-elevation profile (see below) |
| Horizon diffuse floor | `0.18` | Transmission when the beam is fully blocked (`0` = full block) |
| Horizon soft-edge width (degrees) | `6` | Elevation span over which shading ramps from floor to full sun |
| Max Solcast weight when fresh | `0.9` | Blend weight on a just-fetched Solcast period |
| Min Solcast weight when stale | `0.5` | Floor on the Solcast blend weight as it ages |
| Solcast freshness half-life (hours) | `2` | How fast the Solcast weight decays toward the floor (`0` = flat-hold) |
| Minimum daily bias (Solcast/OM) | `0.5` | Lower clamp on the fallback bias for uncovered periods |
| Maximum daily bias (Solcast/OM) | `2.0` | Upper clamp on the fallback bias |
| Morning damping factor | `0.0` | Rolls off the morning shoulder |
| Evening damping factor | `0.0` | Rolls off the evening shoulder |
| Panel efficiency factor | `0.93` | Open-Meteo lib efficiency input |
| Open-Meteo poll interval (minutes) | `20` | Live forecast refresh cadence |
| Solcast daily API call budget | `10` | Hard cap (free tier = 10/day; legacy = 50/day) |
| Solcast calls to keep in reserve | `0` | Held back from the budget for retries |

### Horizon file

To model obstructions from nearby trees or buildings, point **Horizon mask file path** at a plain `.txt` file describing how high the horizon rises at each compass bearing. Two formats are accepted:

- **Sparse (recommended):** `azimuth<tab>elevation` pairs, one per line (tab, space, or comma separated), interpolated across the full circle. Azimuth is degrees clockwise from north; elevation is the obstruction's top, in degrees. Lines starting with `#` are comments; blank lines are ignored.
- **Dense:** one elevation value per line, evenly spaced clockwise from north (36 lines = every 10°).

```
# az_deg  horizon_elevation_deg
0    0
90   25
140  53
175  0     # clears to the south-west
```

For each 30-minute period the sun's azimuth and elevation are computed with `astral`, and the period is scaled by `transmission = clamp((sun_elevation − horizon(azimuth)) / shoulder, floor, 1)`, using the **Horizon soft-edge width** and **Horizon diffuse floor** options. Leaving the path empty applies no shading.

---

## Sensors

SolcastFusion exposes the **complete sensor roster** of `open_meteo_solar_forecast`, with identical keys and units:

| Sensor | Unit | Class |
|--------|------|-------|
| Energy Production Today | kWh | energy / measurement |
| Energy Production Today Remaining | kWh | energy / measurement |
| Energy Production Tomorrow | kWh | energy / measurement |
| Power Production Now | W | power / measurement |
| Peak Power Time Today | timestamp | timestamp |
| Peak Power Time Tomorrow | timestamp | timestamp |
| Energy Current Hour | kWh | energy / measurement |
| Energy Next Hour | kWh | energy / measurement |

**Energy Production Today** carries a `watts` attribute — the full 30-minute output curve (blend × horizon transmission) as a `{ISO-8601 UTC datetime → watts}` dict — for downstream consumers that read the raw shape. (It's excluded from the recorder to keep the database lean.)

### Diagnostic sensors

| Sensor | Meaning |
|--------|---------|
| Solcast Calls Remaining | Calls left in today's budget |
| Last Solcast Update | Timestamp of the most recent Solcast poll |
| Daily Bias | Solcast⁄Open-Meteo daily-total ratio, applied to periods with no retained Solcast |
| Source | `blended` or `om-only` (pure Open-Meteo fallback) |
| Solcast Coverage | Fraction of daytime periods backed by a retained Solcast value |

If **both** sources are unavailable, sensors report `unavailable` (never `0`), so downstream logic treats solar as *unknown* rather than *zero*.

---

## Requirements

- Home Assistant 2024.1 or newer.
- A free [Solcast](https://solcast.com/) hobbyist account with at least one configured rooftop site, and its API key.
- No Open-Meteo account or key is needed.

## Credits

- Uses the [`open-meteo-solar-forecast`](https://pypi.org/project/open-meteo-solar-forecast/) library — the same one the official Home Assistant Open-Meteo integration is built on.
- Forecast magnitude and rooftop geometry from [Solcast](https://solcast.com/).

## Contributing

Issues and pull requests are welcome at [afewyards/ha-solcast-fusion](https://github.com/afewyards/ha-solcast-fusion).
