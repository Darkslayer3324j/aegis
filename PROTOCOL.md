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
| Development | all origins whose targets fall in 2022-06 → 2025-12 | `final-26.1` (SHA-256 recorded in each report) | already seen; used freely |
| **Confirmation** | origins whose targets fall in **2026-01 → 2026-12** | **`final-27.1`**, expected around June 2027 | truth not yet published on 23 Sep 2026 |

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

Exactly **one** candidate is carried to confirmation. It is chosen on development results
by the primary metric below, and the choice is recorded in this file before freezing.

## 5. Decision rule (fixed now)

All comparisons are `nbar + V*` against `nbar` on the same origins, countries and
horizons, in the vintage view. Intervals use a moving-block bootstrap over consecutive
origins: 6-month blocks are primary, and 3 and 9 are reported as sensitivity.

**Primary.** Mean ΔCRPS over active countries < 0, with the 95% interval's upper bound
< 0, **and** a relative improvement of at least 2% of the baseline's mean CRPS.

**Secondary (must not fail).** Log score: no significant deterioration, meaning the
interval's lower bound is ≤ 0.

**Guardrails (must not fail).**
- 80% interval coverage within 2 percentage points of the baseline, or closer to 80%.
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
   `aegis backtest --truth final-27.1 --start 2026-01-01`. The result is published as-is.
4. The prospective archive is scored the same way when its truth arrives.

## 7. Development log

| Round | Date | Result (world, 38 origins, truth `final-26.1`) | Decision |
|---|---|---|---|
| 1 | 23 Sep 2026 | No candidate passes §5. ΔCRPS vs `nbar`: V0 +0.39 [+0.09, +0.74]; V1 +0.25 [−0.03, +0.54]; V2 +0.35 [+0.17, +0.53]; V3 +1.45 [+0.80, +2.14]. All improve log score (about −0.09 to −0.10, CIs exclude 0). V2 has the best nowcast; V3's growth signal overshoots badly where completeness < 0.8. V3 is better in 75% of countries but worse on the mean, because the mean is dominated by a few high-volume countries. | Nothing carried to confirmation. Development continues (round 2). §5 is **not** changed after seeing these results. A scale-free primary metric may be proposed only for a *new* confirmation period, logged here before any result on it is seen. |

Pakistan provinces (same protocol, 8 units, round 1): no candidate passes. V1 comes closest: ΔCRPS −0.108 [−0.229, +0.010], +6.1% relative, with log score significantly better.

| Field | Value |
|---|---|
| Chosen candidate | *(to be filled before freezing)* |
| Frozen commit | *(to be filled)* |
| Freeze date | *(to be filled)* |
