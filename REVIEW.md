# For the reviewer: revision 4 (24 September 2026)

This revision responds to the review of revision 3. Each point below links to the fix
and to where it can be checked. Commit: see `git log`. The latest results are round 1b
in RESULTS.md.

Run the tests (the package does not need to be installed):

```
python -m pytest -q        # 46 tests
```

## Your points and what changed

| # | Review point | Status | Where to check |
|---|---|---|---|
| 1 | Future-country leak: roster taken from the whole store | **Fixed.** `VintageStore.countries_at(asof)` returns countries with an event in some release available at the origin. It is used for the forecast roster (`pipeline.run_origin`) and for every default panel, including `build_history` | `src/aegis/vintage.py` (`countries_at`, `panel`); `tests/test_end_to_end.py::test_future_only_country_cannot_change_an_earlier_forecast` (it fails on the old code: mutation-checked) |
| 2 | The same leak inside the historical training panel | **Fixed** by the same change: `panel()` defaults to `countries_at(asof)`. The mutation check restores the old roster in `panel()` only, and the test fails | as above |
| 3 | R8 claim too strong | **Reworded.** It now says the release-level boundary was mutation-checked and that the country universe needed its own test | RESULTS.md §7, row R8 |
| 5 | pandas `fillna` downcasting warnings | **Fixed.** The suite runs without them | `src/aegis/vintage.py` (`snapshot`) |
| 6 | Circular bootstrap blocks | **Fixed.** Only valid starts are used; blocks never wrap | `src/aegis/backtest.py::block_indices`; `test_bootstrap_blocks_never_wrap` |
| 8 | Confirmation defined by origin date, not target | **Fixed.** `--target-start/--target-end` select every origin that can reach a target month in the window and score only those targets | `backtest.origins_for_targets`; `test_confirmation_window_is_defined_by_target_month`; PROTOCOL.md §2, §6 (A3) |
| 9 | Ambiguous coverage guardrail | **Fixed:** coverage ≥ baseline − 2 points **and** \|coverage − 80%\| ≤ \|baseline − 80%\| + 2 points | PROTOCOL.md §5 (A1); `backtest.decide` |
| 10 | No rule for 0 or 2+ passing candidates | **Added:** 0 → nothing carried; 1 → that one; 2+ → lowest development CRPS | PROTOCOL.md §4 (A2); `backtest.decide` |
| 12 | "Widens and re-centres" stated as fact | **Reworded** as a plausible, undecomposed explanation | RESULTS.md, text under Table 3 |
| 14 | Add a simple two-state visibility benchmark | **Added as M2**, registered before it ran (A4). The current state is inferred from a real-time signal (first-to-second release growth → P(LOW)), propagated one Markov step; the nowcast is bounded between the two state levels | `src/aegis/observation_v2.py` (M2); PROTOCOL.md §4 |

## Problems we found ourselves in this revision

| # | Problem | What was done |
|---|---|---|
| D1 | Round 1's "V3" was **not** the registered V3 (mean-reverting latent state). It was a reporting-triangle growth regression | Renamed **V3g** everywhere and logged as a deviation. The registered V3 and V4 have not been built | 
| — | The history cache was keyed on a version number that was not bumped when `build_history` changed, so a rerun nearly used the leaky cached history | Caught before any result was written. The cache key now includes a SHA-256 of `vintage.py` and `observation.py` (`backtest.load_history`) |

## Round 1b results (all fixes applied; truth `final-26.1`; 38 origins)

- **World (137 countries): no candidate passes §5.** The closest is V1: ΔCRPS +0.215
  [−0.024, +0.472]. Every candidate improves the log score significantly.
- **Pakistan (8 units): V1 passes §5, borderline.** ΔCRPS −0.108 [−0.244, −0.009]
  (+6.1%). It **fails** the 3-month-block sensitivity check (upper bound +0.003). The point
  estimates are unchanged from round 1. Only the interval moved, after the bootstrap fix
  (F2), which was made before this result was seen.
- **Not frozen.** Freezing V1 for Pakistan is pending the owner's decision.

Full tables: RESULTS.md, "v0.2 development round 1b". Decision log: PROTOCOL.md §7–8.

## Questions we would most like answered

1. Does the Pakistan V1 pass stand up, given that it moved across zero only after the
   bootstrap change, and fails the 3-month sensitivity check? Should the sensitivity
   checks be made binding for future rounds? If so, that would be amendment A5, before
   any new result.
2. Is `countries_at` (every country with an event in any available release, from 2015
   onward in the finals) the right universe, or should it be a fixed, pre-declared
   roster?
3. Is M2's real-time state inference sound, in `fit_m2`, step 5 (months at the origin),
   and in the in-sample state probabilities used to fit dispersion?
4. Anything that would stop you freezing the evaluation infrastructure now.
