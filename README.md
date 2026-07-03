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

SolcastFusion doesn't blend a stale Solcast reading with fresh Open-Meteo data (that's often worse than either). Instead it **bias-corrects** the live Open-Meteo curve toward Solcast truth:

1. Both forecasts are aligned to a common 30-minute grid keyed by **absolute UTC instants** (DST-safe — no duplicated or dropped periods).
2. At each Solcast poll, a per-period correction factor `k(t) = solcast(t) / openmeteo(t)` is computed, guarded against bad values, then clamped to `[0.5, 2.0]`.
3. The blended output is `openmeteo(t) × k(t)`, recomputed on **every** fresh Open-Meteo poll (~20 min) — always using the freshest cloud data, merely scaled toward Solcast.
4. At dawn/dusk where Open-Meteo ≈ 0 (a factor can't lift a zero), the Solcast value is **substituted directly**.
5. Between Solcast polls the `k` factors **decay toward 1.0** (pure Open-Meteo) as they age, so a stale calibration can't mislead when the sky changes fast.

### Quota-aware Solcast polling

Solcast is polled on a **daylight-aware budget scheduler**, not a fixed interval:

- One poll near **sunrise**, then spread across daylight at an adaptive interval so long summer days never overrun the cap.
- **Never polls at night** — one call returns the whole horizon (up to +14 days), so the last daylight poll already carries tomorrow's curve.
- A persisted daily counter enforces a **hard quota guard** (default cap 8, with 2 in reserve for retries), reset at 00:00 UTC.
- Restarts **never burn quota or lose calibration** — the last curve, `k` factors, and call counter are persisted.
- If the quota is exhausted or Solcast is down, it falls back to **pure Open-Meteo** rather than reporting zero.

### Near-field horizon shading (optional)

Neither free API knows about *your* trees and buildings. Provide an optional horizon file and SolcastFusion applies a single shading mask to the blended curve — identical shading for both sources by construction (see [Horizon file](#horizon-file)).

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

> Solcast is treated as the **source of truth** for geometry. A daily background check (≈00:05, quota-free) re-reads the site and mirrors any changes into the Open-Meteo config in place — so if you edit your array on the Solcast dashboard, the calibration never silently drifts. No manual reconfigure needed.

You can re-enter or change your API key later via the integration's **Reconfigure** action.

### Options

Open **Configure** on the integration to tune behaviour. Every option has a safe default — you can ignore this panel entirely.

| Option | Default | Description |
|--------|---------|-------------|
| Horizon mask file path | *(none)* | Optional near-field shading profile (see below) |
| Diffuse irradiance fraction | `0.15` | Light retained in shaded periods (0 = full block) |
| Minimum correction factor `k_min` | `0.5` | Lower clamp on the per-period factor |
| Maximum correction factor `k_max` | `2.0` | Upper clamp on the per-period factor |
| `k`-factor decay half-life (hours) | `2` | How fast a stale factor decays toward 1.0 (`0` = flat-hold, no decay) |
| Morning damping factor | `0.0` | Rolls off the morning shoulder (e.g. `0.3` for SE shade) |
| Evening damping factor | `0.0` | Rolls off the evening shoulder |
| Panel efficiency factor | `0.93` | Open-Meteo lib efficiency input |
| Open-Meteo poll interval (min) | `20` | Live forecast refresh cadence |
| Solcast daily API call budget | `8` | Hard cap (free tier = 10/day; legacy = 50/day) |
| Solcast calls to keep in reserve | `2` | Held back from the budget for retries |

### Horizon file

To attenuate periods blocked by nearby trees or buildings, point **Horizon mask file path** at a plain `.txt` file:

- **One obstruction-elevation value (in degrees) per line**, evenly spaced clockwise from north.
- The angular step is inferred from the line count (36 lines = every 10°, 12 lines = every 30°). Blank lines are ignored.

For each 30-minute period the sun's azimuth and elevation are computed with `astral`; if the sun sits below the horizon profile, that period is attenuated to the diffuse-retention fraction. Leaving the path empty applies no mask.

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

**Energy Production Today** carries a `watts` attribute — the full blended 30-minute curve as a `{ISO-8601 UTC datetime → watts}` dict — for downstream consumers that read the raw shape. (It's excluded from the recorder to keep the database lean.)

### Diagnostic sensors

| Sensor | Meaning |
|--------|---------|
| Solcast Calls Remaining | Calls left in today's budget |
| Last Solcast Update | Timestamp of the most recent Solcast poll |
| Correction Factor | Current daily-total scalar `K` (Solcast ÷ Open-Meteo) |
| Source | `blended` or `om-only` (pure Open-Meteo fallback) |
| Clamped Periods | % of periods where `k` hit the clamp — visibility into calibration stress |

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
