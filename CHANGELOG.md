# CHANGELOG


## v0.2.0 (2026-07-04)

### Bug Fixes

- Sort manifest keys and add options translations for hassfest
  ([`0121dc1`](https://github.com/afewyards/ha-solcast-fusion/commit/0121dc1d406e5850c89584d3efc76449e8b1c7ab))

- **combiner**: Report Solcast coverage during an Open-Meteo outage
  ([`97b7abb`](https://github.com/afewyards/ha-solcast-fusion/commit/97b7abb9bb5c951b477e53c1fd1e52b613b979fd))

pct_solcast_covered derives daytime buckets from OM; when OM collapses to {} during an outage, fall
  back to Solcast's own above-EPS buckets so full Solcast coverage no longer reports as 0%.

Claude-Session: https://claude.ai/code/session_012bznsaJxz1x1HC7FCNhbEX

- **config-flow**: Fall back to default when name is blank
  ([`e20e7e5`](https://github.com/afewyards/ha-solcast-fusion/commit/e20e7e505f6b872fab57c334a347721b83dbaff2))

Also add a regression test for async_setup_entry wiring entry.title into the device name. Addresses
  non-blocking findings from final review.

Claude-Session: https://claude.ai/code/session_019y7AmCvzNRC9Mk3MvXPBpv

- **horizon**: Re-fit seed profile to observed transmission
  ([`2b6d692`](https://github.com/afewyards/ha-solcast-fusion/commit/2b6d692541e5841df2dbd40c06d9685ffbdd1175))

The first seed under-shaded the deep-east (az 90 gave ~0.67 vs observed ~0.19) and over-shaded the
  SSE approach to noon (az 159 gave ~0.2 vs observed ~0.52). Re-fit H(az) = sun_el -
  T_obs*shoulder(6) so the model reproduces the 7-day actual/Solcast transmission table within 0.07
  worst-bin error.

Verified live on HAOS: today total 6.97 -> 5.95 kWh (actual ~6.2); the late-morning trough lifts
  (158 -> 332 W) while the early-morning east correctly drops toward floor.

Update the az-136 regression assertion (0.57 -> 0.62) and the apply_transmission expectation (570 ->
  617) to the re-fit values, and record the fitted anchors in the design appendix.

Claude-Session: https://claude.ai/code/session_012bznsaJxz1x1HC7FCNhbEX

- **mirror**: Guard the geometry mirror against quota exhaustion
  ([`a5a1b5b`](https://github.com/afewyards/ha-solcast-fusion/commit/a5a1b5b80655d37a51a60df2517d7e193158518b))

Check quota_remaining(cap) <= reserve before fetch_sites, mirroring the poller's guard, so a weekly
  mirror sync triggered after a mid-day restart can't push the day's Solcast calls past the cap.

Claude-Session: https://claude.ai/code/session_012bznsaJxz1x1HC7FCNhbEX

### Chores

- Gitignore internal workflow artifacts (docs/superpowers/)
  ([`b11d8a1`](https://github.com/afewyards/ha-solcast-fusion/commit/b11d8a110d911226a8a1e9cdecb0d25dfa10b1f6))

Keep brainstorming specs and implementation plans out of the repo so they can't slip into commits or
  shipped releases.

Claude-Session: https://claude.ai/code/session_012bznsaJxz1x1HC7FCNhbEX

- Ignore HACS brands check pending brands submission
  ([`5c389f1`](https://github.com/afewyards/ha-solcast-fusion/commit/5c389f15b9622377c8c6ba9ec962f4f86cfc4849))

### Documentation

- Update README for the freshness-blend + graded-horizon pipeline
  ([`45eae23`](https://github.com/afewyards/ha-solcast-fusion/commit/45eae23f648f80a04f946cf224db21eb473fd8eb))

The README still described the removed k-factor pipeline (k=solcast/om clamped [0.5,2.0], decay
  toward 1.0, binary shading mask). Rewrite How-it-works, the options table, the horizon-file
  format, and the diagnostic sensors to match the shipped design: freshness-weighted Solcast/OM
  blend, daily-bias fallback for uncovered periods, graded transmission =
  clamp((sun_el-H(az))/shoulder, floor, 1), quota defaults 10/0, weekly geometry mirror, and the
  Daily Bias / Solcast Coverage sensors.

Claude-Session: https://claude.ai/code/session_012bznsaJxz1x1HC7FCNhbEX

### Features

- **combiner**: Freshness-weighted Solcast blend drives forecast shape
  ([`a9412e7`](https://github.com/afewyards/ha-solcast-fusion/commit/a9412e71e21645cc2476a788b84874ef1d3d1f31))

Replace om*k with w*solcast+(1-w)*om where w decays from w_max toward w_min with fetch age;
  no-Solcast buckets fall back to om*daily_bias. Rewire the coordinator to consume the retained map
  via merge_poll and emit pct_solcast_covered. Remove compute_k/decay_k/is_clamped/ daily_scalar and
  the k-factor poll path.

Claude-Session: https://claude.ai/code/session_012bznsaJxz1x1HC7FCNhbEX

- **config-flow**: Expose transmission and blend tunables, drop diffuse
  ([`d00a5bf`](https://github.com/afewyards/ha-solcast-fusion/commit/d00a5bfb24eccb9487385c7cb1ac1ca8b38cbadb))

Replace the diffuse option with h_floor/h_shoulder (graded transmission) and w_min/w_max (freshness
  blend), relabel k_min/k_max as daily-bias bounds and decay_halflife_h as the Solcast freshness
  half-life. Remove the now-unused CONF_DIFFUSE constant.

Claude-Session: https://claude.ai/code/session_012bznsaJxz1x1HC7FCNhbEX

- **config-flow**: Let each instance set a custom name
  ([`29c4938`](https://github.com/afewyards/ha-solcast-fusion/commit/29c4938c7e8109a1390f49ea35a36a47a935d47d))

Claude-Session: https://claude.ai/code/session_019y7AmCvzNRC9Mk3MvXPBpv

- **const**: Add blend/horizon tunables and raise quota defaults
  ([`b26b9c9`](https://github.com/afewyards/ha-solcast-fusion/commit/b26b9c9b2efb0f2b6ef123890df6edab192d8501))

Add W_MAX/W_MIN (freshness blend), H_SHOULDER/H_FLOOR (graded transmission). Bump Solcast cap 8->10
  and reserve 2->0 for the free tier. CONF_DIFFUSE retained until the transmission layer lands.
  Guard the options round-trip test against the not-yet-wired keys (Task 8 rewires).

Claude-Session: https://claude.ai/code/session_012bznsaJxz1x1HC7FCNhbEX

- **coordinator**: Apply graded transmission over the blended curve
  ([`a5a0288`](https://github.com/afewyards/ha-solcast-fusion/commit/a5a0288a5bc908a91e75ef3e415923fc21158004))

Replace the binary is_shaded*diffuse mask with apply_transmission (shoulder/floor) over the blended
  curve. The horizon profile still loads only from the user's horizon_file option (unset -> no
  shading); the integration ships no site-specific default. Remove the now-dead is_shaded/apply_mask
  helpers.

Claude-Session: https://claude.ai/code/session_012bznsaJxz1x1HC7FCNhbEX

- **horizon**: Graded transmission model with fixture profile
  ([`1f0b8cc`](https://github.com/afewyards/ha-solcast-fusion/commit/1f0b8cc69f215569b071a5f7eb2f89c1785247e7))

Add transmission = clamp((sun_el - H(az))/shoulder, floor, 1) and apply_transmission over the sun
  az/el per bucket. A derived sparse horizon profile fitted from the 7-day actual/Solcast ratio
  ships as a test fixture (not a runtime default). Regression fixture pins az 136 el 54 -> ~0.57
  (was 0.09 under binary*diffuse).

Claude-Session: https://claude.ai/code/session_012bznsaJxz1x1HC7FCNhbEX

- **mirror**: Count the site call and gate the mirror to weekly
  ([`731d041`](https://github.com/afewyards/ha-solcast-fusion/commit/731d041731b6754810050bc3a9f2df90c25edd4b))

Charge the daily geometry mirror against the Solcast quota and skip it unless the last sync was >= 7
  days ago, so most days spend all 10 calls on forecasts.

Claude-Session: https://claude.ai/code/session_012bznsaJxz1x1HC7FCNhbEX

- **sensor**: Group entities under a named per-instance device
  ([`84d305b`](https://github.com/afewyards/ha-solcast-fusion/commit/84d305be9e3ca9ca77590ce55f800673591386da))

Claude-Session: https://claude.ai/code/session_019y7AmCvzNRC9Mk3MvXPBpv

- **sensor**: Replace clamped-periods diagnostic with Solcast coverage
  ([`177eb4c`](https://github.com/afewyards/ha-solcast-fusion/commit/177eb4c0b5b557a72dff703e0d0bd94e6a5c93e2))

pct_periods_clamped no longer has meaning after the k-factor removal; expose pct_solcast_covered
  (fraction of daytime buckets with fresh retained Solcast) and relabel correction_factor as the
  daily bias.

Claude-Session: https://claude.ai/code/session_012bznsaJxz1x1HC7FCNhbEX

- **store**: Retain rolling per-bucket Solcast curve across polls
  ([`08db2c8`](https://github.com/afewyards/ha-solcast-fusion/commit/08db2c8a9dfbefca69bff0ad4d19dcc8a0c8aaa3))

Add solcast_retained map ({bucket: {w, fetched}}), merge_poll (48 h retention, per-bucket fetch
  stamp) and an idempotent v1->v2 migration that upgrades the flat last_solcast schema on load.
  Legacy k-factor keys kept for now; removed once the blend is rewired.

Claude-Session: https://claude.ai/code/session_012bznsaJxz1x1HC7FCNhbEX

### Refactoring

- Align quota guard and coverage fallback with review spec
  ([`4993293`](https://github.com/afewyards/ha-solcast-fusion/commit/49932931f9d882a63ac524458bcee1585f158d22))

Simplify the mirror's quota guard to a flat cap check (drop the reserve term) and
  pct_solcast_covered's OM-outage fallback to plain Solcast presence, matching the reviewer's exact
  specification.

Claude-Session: https://claude.ai/code/session_012bznsaJxz1x1HC7FCNhbEX

- **store**: Drop dead k-factor and flat last_solcast machinery
  ([`5722bc9`](https://github.com/afewyards/ha-solcast-fusion/commit/5722bc9a9e72d63392c89f61d0a0aaecfa88735b))

Remove the k_factors/last_solcast properties, save_poll_result and their init keys now the blend
  consumes solcast_retained; migration pops the legacy keys on load.

Claude-Session: https://claude.ai/code/session_012bznsaJxz1x1HC7FCNhbEX

### Testing

- **integration**: Lock 2026-07-04 replay against the phantom trough
  ([`f0fc885`](https://github.com/afewyards/ha-solcast-fusion/commit/f0fc885e30d39a56c26738f387bb30e973818fde))

Replay an Open-Meteo midday crater with fresh retained Solcast and assert the blended output tracks
  Solcast (no 200 W dip), guarding root causes 1 and 2 from regressing.

Claude-Session: https://claude.ai/code/session_012bznsaJxz1x1HC7FCNhbEX


## v0.1.0 (2026-07-03)

### Chores

- Add CI workflows for tests, hacs and hassfest
  ([`112f841`](https://github.com/afewyards/ha-solcast-fusion/commit/112f841bea0ad82bb6d59707e51d1087c484f718))

- Add pre-commit config
  ([`64f1a20`](https://github.com/afewyards/ha-solcast-fusion/commit/64f1a20a0810c8f3f720ed676db14ed57f3e7162))

- Add project scaffolding and packaging config
  ([`2c62438`](https://github.com/afewyards/ha-solcast-fusion/commit/2c624387f7b9683d9859e291ef7582c7dd4d0c74))

- Add pyright strict config
  ([`5280f2b`](https://github.com/afewyards/ha-solcast-fusion/commit/5280f2b673725915d250fe68998695eaa3127c9d))

- Add ruff config and format codebase to green
  ([`f493a0d`](https://github.com/afewyards/ha-solcast-fusion/commit/f493a0d64b9e12ab2b4916bdbbc96c049fafdba1))

- Add semantic-release config and release workflow
  ([`dae58c2`](https://github.com/afewyards/ha-solcast-fusion/commit/dae58c2c9b027ff6280d48dc366298c400038957))

- Scope pyright to package, drop dead import, un-deprecate ruff hook id
  ([`ac8a3b9`](https://github.com/afewyards/ha-solcast-fusion/commit/ac8a3b9e716a9f2383a7508c3b9d60e9e9cf928e))

### Features

- Add config flow
  ([`735dfa1`](https://github.com/afewyards/ha-solcast-fusion/commit/735dfa1edda983579e060ac3f20eba74230cf725))

- Add data update coordinator and scheduler
  ([`a8a1770`](https://github.com/afewyards/ha-solcast-fusion/commit/a8a177028c06cc12fc8d3e4d8a8bf03eeab78313))

- Add energy dashboard forecast integration
  ([`965c39f`](https://github.com/afewyards/ha-solcast-fusion/commit/965c39f84734e687f02a5cbb64d3d2167ad1aab6))

- Add forecast combiner
  ([`9990d9b`](https://github.com/afewyards/ha-solcast-fusion/commit/9990d9b95dea3b46e4425aada3358d7bb0aa44c1))

- Add horizon shading calculation
  ([`5173070`](https://github.com/afewyards/ha-solcast-fusion/commit/51730706d661d5c49da7fa47f5366b1fffca27d8))

- Add integration manifest, constants and translations
  ([`68bc0ec`](https://github.com/afewyards/ha-solcast-fusion/commit/68bc0ecf0300c36e6d4b3fba4390d14d160c679a))

- Add persistent storage layer
  ([`9a6c83f`](https://github.com/afewyards/ha-solcast-fusion/commit/9a6c83f4d321d93c9a84cd34ee20f9f832334ce4))

- Add sensor platform
  ([`5f22b75`](https://github.com/afewyards/ha-solcast-fusion/commit/5f22b751d3ea79d56e9693b6f007fcbb90d688f0))

- Add Solcast API client
  ([`3b30c05`](https://github.com/afewyards/ha-solcast-fusion/commit/3b30c053f2918ff8faba6d8918a1370bf813d104))

- Add Solcast mirror and geometry check
  ([`f5678c5`](https://github.com/afewyards/ha-solcast-fusion/commit/f5678c5d10bab69e0ee53a5d25b052671f7a78cf))

- Wire up integration setup
  ([`8cb7ad7`](https://github.com/afewyards/ha-solcast-fusion/commit/8cb7ad781c7c791723573d71d3f842cfc8a9128c))

### Refactoring

- Drop dead timezone imports and UTC self-assignments
  ([`3a9acdf`](https://github.com/afewyards/ha-solcast-fusion/commit/3a9acdf233b81c0c44545b1c99c5b883f8bf24fe))

### Testing

- Add x1-smartcharge contract test
  ([`c52e5cf`](https://github.com/afewyards/ha-solcast-fusion/commit/c52e5cf29af5eba5aa95fd56b077c63518e13f35))
