# AEGIS v0.1: results

**Current version: revision 2, 23 September 2026.** This rerun follows an external review.
Revision 1 numbers are superseded; what changed and why is logged in §7.

## Setup

| Setting | Value |
|---|---|
| Code | commit `ee3601a` |
| Truth | `final-26.1`, pinned (SHA-256 `8c941d84954e555e…`), final data through December 2025 |
| Origins | 38 origins, 20 June 2022 → 20 December 2025, one per UCDP Candidate monthly release date |
| Origins lost | 5 (July–November 2022): the underlying releases were re-uploaded on 20 December 2022 and are never backdated |
| Horizons | 36 origins × 3 horizons + 1 × 2 + 1 × 1 (truth ends December 2025) = **111 origin-horizons** |
| Forecasts | 111 × 139 countries = **15,429 per model and view**; 8,803 for active countries (any event in the prior 12 months) |
| Inference | Moving-block bootstrap over consecutive origins: 6-month blocks primary, 3 and 9 as sensitivity. The effective sample size is closer to **38 origins** than to 15,429 forecasts |
| Log score | Exact, computed in log space. Revision 1 floored probabilities at 1e-12, which capped 530 scores |
| Reproduce | `aegis backtest --truth final-26.1` (about 8 minutes) |

The full generated report is `results/backtest-*/report.md`, and per-forecast scores
are in `scores.parquet`.

## Headline

| Question | Answer |
|---|---|
| **Paper 1.** Does scoring on the data available at the time change measured skill? | **Yes for the simple baselines; not clearly for the best model.** Vintage-view CRPS is significantly worse for `naive` (+0.87) and `ma6` (+0.98). For `nbar` it is +0.55, 95% CI [−0.03, +1.04]. Rankings are unchanged for these three models. Richer models are untested. |
| **E2.** Does the nowcast estimate the eventual count better than the raw count? | **Yes at ages 1–2.** CRPS −1.99 at age 1, CI [−2.88, −1.00]. Age 3 is not significant overall. Where estimated completeness is below 0.8, point estimates reverse at every age, but the difference is significant only at age 3. |
| **Paper 2.** Does the visibility correction improve forecasts? | **Split by metric.** **Log score improves:** −0.099, CI [−0.192, −0.033]. **CRPS worsens:** +0.39, CI [+0.09, +0.74], driven by countries with C₁ < 0.8. On the pre-agreed primary metric (CRPS) the baseline wins. |
| Do visibility flags pick out less reliable forecasts? | **Consistent with yes, including on scale-free measures.** Tail-miss rate: 8.4% for OK against 13.3% for WARN and 13.2% for ABSTAIN. Normalised CRPS: 0.38 against 1.09 and 0.90. No interval is attached yet. |
| Is low completeness episodic? | **Short, somewhat persistent episodes.** P(low next \| low now) = 60% against 13% otherwise. Mean episode length is 2.0 months; 67% of episodes last one month and 16% last three or more. |

v0.1 does **not** claim that AEGIS beats the baseline.

## Table 1: Paper 1, CRPS(vintage view) − CRPS(final view), active countries

| Model | CRPS final | CRPS vintage | Diff | 95% CI (6-mo blocks) | 3-mo / 9-mo blocks | Cov80 final → vintage |
|---|---|---|---|---|---|---|
| naive | 12.73 | 13.60 | +0.87 | [+0.17, +1.51] | [+0.29, +1.42] / [+0.08, +1.51] | 91.9% → 89.5% |
| ma6 | 9.91 | 10.88 | +0.98 | [+0.47, +1.45] | [+0.49, +1.49] / [+0.51, +1.39] | 94.7% → 92.7% |
| nbar | 9.67 | 10.22 | +0.55 | [−0.03, +1.04] | [+0.02, +1.04] / [−0.00, +1.02] | 96.1% → 93.3% |

Retrospective evaluation on revised data makes models look better than they could have
been in real time, and the effect is clearest for the simplest baselines. The larger gap
for `ma6` is *consistent with* its equal weighting of recent, still-incomplete months;
this experiment does not establish that mechanism. With exact log scores, `naive`
degrades far more on the vintage view (3.30 → 4.72) than the other models do.

## Table 2: E2, CRPS(nowcast) − CRPS(raw count)

| Age | All: diff [95% CI] | C < 0.8: diff [95% CI] (n) | C ≥ 0.8: diff [95% CI] |
|---|---|---|---|
| 1 | **−1.99 [−2.88, −1.00]** | +2.63 [−7.27, +18.20] (275) | −2.45 [−3.10, −1.84] |
| 2 | **−1.07 [−1.88, −0.20]** | +5.39 [−4.47, +19.84] (207) | −1.54 [−2.08, −1.13] |
| 3 | −0.52 [−1.23, +0.29] | **+19.30 [+7.14, +33.03]** (132) | −1.41 [−1.75, −1.12] |

## Table 3: Paper 2, `nbar+vis` − `nbar` (vintage view; negative favours AEGIS)

| Slice | Diff | 95% CI (6-mo blocks) | n / origins |
|---|---|---|---|
| **Active, CRPS (primary)** | **+0.39** | **[+0.09, +0.74]** | 8,803 / 38 |
| Active, log score | **−0.099** | **[−0.192, −0.033]** | 8,803 / 38 |
| All countries, CRPS | +0.22 | [+0.06, +0.41] | 15,429 / 38 |
| All countries, log score | −0.067 | [−0.125, −0.019] | 15,429 / 38 |
| Active, C₁ < 0.8 | +6.15 | [+3.39, +9.92] | 801 / 38 |
| Active, 0.8 ≤ C₁ < 1.0 | −0.04 | [−0.24, +0.18] | 5,660 / 38 |
| Active, C₁ ≥ 1.0 | −0.53 | [−0.80, −0.28] | 2,342 / 38 |
| Active, h = 1 / 2 / 3 | +0.52 / +0.26 / +0.39 | [+0.07, +0.99] / [−0.05, +0.59] / [+0.15, +0.68] | |

The split between metrics is informative. CRPS weighs absolute error, so it is dominated
by large overshoots in a few high-volume, low-completeness countries. The log score
weighs probability assigned to what happened, and it improves because the correction
widens and re-centres forecasts that the baseline was confidently wrong about.

## Table 4: visibility status (`nbar+vis`, active countries)

| Status | n | Mean expected count | CRPS | Normalised CRPS | Tail-miss rate (5–95%) | Cov80 |
|---|---|---|---|---|---|---|
| OK | 7,876 | 23.6 | 7.93 | 0.38 | 8.4% | 94.6% |
| WARN | 813 | 83.5 | 30.65 | 1.09 | 13.3% | 87.7% |
| ABSTAIN | 114 | 92.7 | 53.12 | 0.90 | 13.2% | 86.0% |

Flagged forecasts have substantially higher error, and the gap persists on scale-free
measures (normalised CRPS, tail-miss rate). This is associative. There is no interval
on it yet, and ABSTAIN is a small group.

## Table 5: persistence of low first-release completeness

Low = age-1 count / final count < 0.8, over country-months with at least 5 final
events. 1,540 country-months across 54 countries.

| Quantity | Value |
|---|---|
| Base rate | 26.3% |
| P(low next month \| low this month) | 59.5% (n = 336) |
| P(low next month \| not low) | 13.1% (n = 1,009) |
| Mean episode length | 1.98 months (205 episodes) |
| One-month episodes | 67% |
| Three-plus-month episodes | 16% |

## §6 What the failure suggests

The correction fails where it should help most (C₁ < 0.8). Table 5 now supports the
mechanism proposed in revision 1:
- low completeness is **persistent but short** (about 2 months on average);
- the v0.1 estimator remembers reporting behaviour with an **18-month half-life**, so it
  keeps applying a large correction after reporting has recovered.

The match between the mismatch and the failure is suggestive, not proof. The test is
whether a model with short, mean-reverting memory fixes the C₁ < 0.8 slice without
hurting the rest. The v0.2 candidates in [PROTOCOL.md](PROTOCOL.md) (V3, V4) are built
for exactly that.

One contributing factor is fixed in the code documentation and left open for testing:
every non-final month is corrected, including months older than 12, which share the
age-12 estimate. Candidate V1 in PROTOCOL.md tests correcting recent months only.

## §7 Changes from revision 1

| # | Change | Effect on results |
|---|---|---|
| R1 | Re-uploaded releases are dated by Last-Modified, never backdated (v0.1 backdated five of them: 22.06–22.09 and the H1 cumulative) | 5 origins lost (43 → 38 distinct dates, 42 → 38 scored); results now contain no re-upload content earlier than it existed |
| R2 | Truth pinned (`--truth`) with SHA-256; code commit recorded | Reruns are reproducible when a newer final appears |
| R3 | Exact log score (the 1e-12 floor capped 530 forecasts) | The AEGIS log-score gain grew from −0.034 to −0.099; `naive`'s vintage log score rose to 4.72 |
| R4 | Moving-block bootstrap replaces the single-origin bootstrap | Intervals widened; Paper 1 for `nbar` is no longer significant; E2 low-completeness reversals at ages 1–2 are not significant |
| R5 | Explicit origin/horizon accounting | Revision 1's "42 origins" and "17,097 forecasts" were both right: 17,097 = (40 × 3 + 2 + 1) × 139. That was never explained, and it is now reported as 111 origin-horizons × 139 |
| R6 | Wording: "is consistent with" instead of causal claims; "episodic" backed by Table 5; flags described as associative | — |
| R7 | The revision 1 "pre-registered" v0.2 split withdrawn: July 2024 → December 2025 was already seen | Replaced by [PROTOCOL.md](PROTOCOL.md): nested walk-forward development, confirmation against `final-27.1` |
| R8 | End-to-end anti-leak test: a store truncated at the origin must give identical forecasts to the full store plus a fake future revision and final | Mutation-checked: it catches three planted leaks (snapshot, observation model, last data month) |
