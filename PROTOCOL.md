# AEGIS v0.2 evaluation protocol

Written 23 September 2026, **before** any v0.2 model code exists. This replaces the
"pre-registered" split in the first version of RESULTS.md, which was not a real holdout:
July 2024 → December 2025 had already been seen in the v0.1 backtest, and the v0.2
design is shaped by what failed there. That period is now **development data**.

## 1. Question

> Can a time-varying model of reporting completeness improve probabilistic forecasts
> without overcorrecting during transient reporting disruptions?

## 2. Data roles

| Role | Origins | Truth | Status |
|---|---|---|---|
| Development | all forecasts whose target month L + h falls in 2022-06 → 2025-12 | `final-26.1` (SHA-256 recorded in each report) | already seen; used freely |
| **Confirmation** | all forecasts whose **target month L + h falls in 2026-01 → 2026-12**, from every origin that can reach one (in practice origins with L from 2025-10 to 2026-11) | **`final-27.1`**, expected around June 2027 | truth not yet published on 24 Sep 2026 |

The confirmation set is defined by **target month**, not origin date (amendment A3). An
origin at 20 December 2025 (L = November 2025) contributes its h = 2 and h = 3 forecasts
(January and February 2026) but not its h = 1 forecast (December 2025).

**Caveat on the confirmation set.** The 2026 *Candidate* data is already public and has
been seen, because it is the input AEGIS forecasts from. What is unseen is the final,
vetted outcome. The test is therefore clean on the scoring side, not on the input side.
Candidate counts correlate strongly with final counts, so this is a weaker guarantee
than a fully prospective test. That is why forecasts made from October 2026 onward are
also logged prospectively (section 6).

## 3. Development: nested walk-forward only

Any tuning (half-life, shrinkage strength, age cap, state-space hyperparameters) is
chosen inside the backtest, per outer origin:

```
outer origin T
 ├── inner training:   origins < T − 6 months, truth = final available at T
 ├── inner validation: the 6 origins before T, truth = final available at T
 └── outer forecast at T (scored later against the pinned development truth)
```

No hyperparameter may be chosen by looking at outer scores. Reported development
results use this nested procedure, never a single global fit tuned on all outer origins.

## 4. Candidates (all compared against v0.1's ratio estimator)

| ID | Observation model |
|---|---|
| V0 | v0.1 fixed-decay ratio estimator (the reference) |
| V1 | V0 with correction limited to recent ages (≤ 6); older non-final months left raw |
| V2 | Robust: weighted median of log revision ratios with shrinkage |
| V3 | Mean-reverting latent log completeness: z_t = μ_c + φ(z_{t−1} − μ_c) + ε_t, Student-t ε |
| V4 | V3 + hurdle nowcast for zero observations: P(final > 0 \| obs = 0), then count given positive |
| V3g | *(added after round 1; see deviation D1)* reporting-triangle growth regression: log((final + 1)/(obs + 1)) ~ 1 + country prior + g + 1{obs = 0}, where g is last month's growth from first to second release |
| M2 | *(added 24 Sep 2026, before it has run: amendment A4)* two-state visibility benchmark. Each country-month is LOW (age-1 completeness < 0.8) or HIGH. Transition probabilities P(LOW→LOW), P(HIGH→LOW) and a completeness level per state are estimated from past pairs. The correction applies the expected completeness given the most recently *observable* state. This is the simplest direct test of "visibility is a short-lived state" (RESULTS.md Table 5), and must be run before V3 and V4 |

**Selection rule (amendment A2, fixed before any candidate has passed):**
- **0 candidates pass §5:** nothing is carried. `nbar` remains the default, and no
  confirmation run is presented as a success test.
- **1 passes:** that candidate is carried.
- **2 or more pass:** the passing candidate with the lowest development mean CRPS is
  carried.

The choice is recorded in this file before freezing.

**Order of development:** V1 → V2 → M2 → V3 → V4. More complex candidates are promoted
only if they fix a failure the simpler ones leave.

## 5. Decision rule (fixed now)

All comparisons are `nbar + V*` against `nbar` on the same origins, countries and
horizons, in the vintage view. Intervals use a moving-block bootstrap over consecutive
origins: 6-month blocks are primary, and 3 and 9 are reported as sensitivity.

**Primary.** Mean ΔCRPS over active countries < 0, with the 95% interval's upper bound
< 0, **and** a relative improvement of at least 2% of the baseline's mean CRPS.

**Secondary (must not fail).** Log score: no significant deterioration, meaning the
interval's lower bound is ≤ 0.

**Guardrails (must not fail).**
- 80% interval coverage (amendment A1): **both** coverage ≥ baseline coverage − 2
  points, **and** |coverage − 80%| ≤ |baseline coverage − 80%| + 2 points. (The old
  wording, "within 2 points of the baseline, or closer to 80%", would have let 70% pass
  against a 96% baseline.)
- PIT tail-miss rate (outside 5–95%) no more than 2 points above the baseline.
- Per-country: worse CRPS in no more than 60% of active countries.

**Reported regardless, but not decision criteria:** h = 1, 2, 3 separately (the effect
should be strongest at h = 1); the C < 0.8 slice and natural reporting disruptions (the
*mechanism*); scale-free metrics (normalised CRPS, tail misses).

**Outcomes.**
- **Pass:** AEGIS's visibility correction becomes the default.
- **Fail:** the baseline stays the default and the result is published as a negative
  finding.

No post-hoc re-slicing turns a fail into a pass.

## 6. Freeze and prospective logging

1. When a candidate is chosen, tag the commit `v0.2-frozen` and record its hash here.
2. From the first release after the freeze, `aegis forecast` output for every origin is
   archived with the commit hash, and never regenerated.
3. When `final-27.1` appears, run the confirmation once:
   `aegis backtest --truth final-27.1 --target-start 2026-01 --target-end 2026-12`.
   The result is published as-is.
4. The prospective archive is scored the same way when its truth arrives.

## 7. Amendments and deviations

Every change to this protocol, with its date and what had already been seen. None of
them can change a result that was already reported.

| # | Date | Change | Seen before the change | Effect on reported results |
|---|---|---|---|---|
| A1 | 24 Sep 2026 | Coverage guardrail made explicit (§5) | Round 1 | None: no round-1 candidate passed the primary criterion, so no verdict depends on the coverage rule |
| A2 | 24 Sep 2026 | Selection rule for 0, 1 or 2+ passing candidates (§4) | Round 1 (0 passed) | None |
| A3 | 24 Sep 2026 | Confirmation set defined by target month; `--target-start/--target-end` added; the old `--start 2026-01-01` command would have dropped January 2026 at h = 2–3 and February at h = 3 | Nothing from the confirmation period | Corrects the confirmation command before it has ever run |
| A4 | 24 Sep 2026 | Candidate M2 (two-state benchmark) added, suggested by external review | Round 1 | M2 has not run; it will be reported in round 2 |
| D1 | 24 Sep 2026 | **Deviation found:** round 1's "V3" was a reporting-triangle growth regression, not the mean-reverting latent state model registered as V3 above. It is renamed **V3g** everywhere. The registered V3 has not been run. | — | Round 1 V3 numbers are V3g's; RESULTS.md relabelled |
| F1 | 24 Sep 2026 | **Integrity fix:** the country universe was taken from the whole store, so a country first appearing after an origin entered that origin's forecasts, historical training panel and observation model. Now origin-aware (`countries_at`), with a mutation-checked test | Round 1 | Round 1 is re-run (round 1b) on the fixed code; the round 1 numbers in RESULTS.md are superseded |
| F2 | 24 Sep 2026 | Bootstrap blocks no longer wrap from the last origin to the first | Round 1 | Intervals re-computed in round 1b |

## 8. Development log

| Round | Date | Result (world, 38 origins, truth `final-26.1`) | Decision |
|---|---|---|---|
| 1 | 23 Sep 2026 | No candidate passes §5. ΔCRPS vs `nbar`: V0 +0.39 [+0.09, +0.74]; V1 +0.25 [−0.03, +0.54]; V2 +0.35 [+0.17, +0.53]; V3g (reported at the time as "V3"; see D1) +1.45 [+0.80, +2.14]. All improve log score (about −0.09 to −0.10, CIs exclude 0). V2 has the best nowcast; V3g's growth signal overshoots badly where completeness < 0.8. V3g is better in 75% of countries but worse on the mean, because the mean is dominated by a few high-volume countries. | Nothing carried to confirmation. Development continues (round 2). The §5 criteria that decide a pass are **not** changed after seeing these results (A1 only clarified the wording of a guardrail no candidate reached). **Superseded by round 1b** (fix F1). A scale-free primary metric may be proposed only for a *new* confirmation period, logged in §7 before any result on it is seen. |

Pakistan provinces (same protocol, 8 units, round 1): no candidate passes. V1 comes closest: ΔCRPS −0.108 [−0.229, +0.010], +6.1% relative, with log score significantly better.

| 1b | 24 Sep 2026 | Round 1 re-run on the fixed code (F1, F2, A1), plus M2. **World:** no candidate passes. ΔCRPS V0 +0.331 [+0.058, +0.578]; V1 +0.215 [−0.024, +0.472]; V2 +0.271 [+0.106, +0.513]; V3g +1.523 [+0.862, +2.342]; M2 +0.428 [+0.337, +0.610]. All improve log score (CIs exclude 0). **Pakistan:** V1 passes §5, ΔCRPS −0.108 [−0.244, −0.009] (+6.1%), but fails the 3-month-block sensitivity check (upper +0.003); V0, V2 and M2 miss; V3g worse. | World: nothing carried, and development continues (the registered V3 and V4 are still unbuilt). Pakistan: V1 is the candidate under A2. **Not frozen yet**: freezing (§6) is the next step and needs the owner's go-ahead. |

| Field | Value |
|---|---|
| Chosen candidate | *(to be filled before freezing)* |
| Frozen commit | *(to be filled)* |
| Freeze date | *(to be filled)* |
