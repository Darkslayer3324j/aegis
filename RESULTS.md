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
| **Paper 2.** Does the visibility correction improve forecasts? | **World: not yet.** Log score improves significantly for every candidate; mean CRPS worsens for all of them (round 1b: best is V1, +0.215 [−0.024, +0.472]). **Pakistan: V1 passes the development rule, borderline** (−6.1% CRPS, CI [−0.244, −0.009]; fails the 3-month sensitivity check). |
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
weighs probability assigned to what happened. One plausible explanation (not yet
decomposed) is that the correction widens and re-centres forecasts in cases where the
baseline assigns too little probability to the realised count.

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

## v0.2 development round 1b: current (24 September 2026)

This is round 1 re-run on fixed code: the origin-aware country universe (PROTOCOL.md F1),
bootstrap blocks that do not wrap (F2), and the explicit coverage rule (A1). It also
includes the new two-state benchmark M2 (A4). Commit `01b38c1`, truth `final-26.1`, 38
origins. **This round supersedes round 1 below.**

**World** (137 countries, down from 139: two countries that only appear after some
origins no longer leak into them; `results/backtest-20260924-1106`):

| Candidate | ΔCRPS vs `nbar` [95% CI, 6-mo blocks] | Relative | ΔLog [95% CI] | Worse in % of countries | Passes §5 |
|---|---|---|---|---|---|
| V0 (v0.1 estimator) | +0.331 [+0.058, +0.578] | −3.2% | −0.099 [−0.187, −0.030] | 61% | no |
| V1 (recent months only) | +0.215 [−0.024, +0.472] | −2.1% | −0.095 [−0.184, −0.023] | 59% | no |
| V2 (robust long-run) | +0.271 [+0.106, +0.513] | −2.6% | −0.091 [−0.176, −0.020] | 55% | no |
| V3g (growth regression) | +1.523 [+0.862, +2.342] | −14.9% | −0.083 [−0.151, −0.020] | 21% | no |
| M2 (two-state) | +0.428 [+0.337, +0.610] | −4.2% | −0.091 [−0.183, −0.019] | 62% | no |

**No world candidate passes.** Every candidate improves the log score significantly, and
every one loses on mean CRPS. M2's nowcast is sound (−1.92 [−2.57, −1.04] at age 1) and
bounded where V3g's is not, but that does not carry over into the forecast. So the loss
is in how corrected history feeds the forecasting model, not only in the correction.

**Pakistan** (8 units; `results/pakistan/backtest-20260924-1053`):

| Candidate | ΔCRPS vs `nbar` [95% CI] | 3-mo / 9-mo blocks | Relative | ΔLog [95% CI] | Passes §5 |
|---|---|---|---|---|---|
| V0 | −0.090 [−0.223, +0.013] | [−0.233, +0.022] / [−0.199, +0.020] | +5.1% | −0.071 [−0.116, −0.024] | no |
| **V1** | **−0.108 [−0.244, −0.009]** | [−0.251, **+0.003**] / [−0.222, −0.003] | **+6.1%** | **−0.074 [−0.118, −0.030]** | **yes (borderline)** |
| V2 | −0.065 [−0.171, +0.023] | [−0.176, +0.023] / [−0.135, +0.029] | +3.6% | −0.036 [−0.062, −0.013] | no |
| V3g | +0.057 [−0.144, +0.227] | — | −3.2% | −0.028 [−0.091, +0.042] | no |
| M2 | −0.085 [−0.198, +0.003] | [−0.196, +0.005] / [−0.174, +0.017] | +4.8% | −0.040 [−0.067, −0.016] | no |

**V1 passes the pre-agreed development rule for Pakistan**, the first pass of any
candidate. It is borderline:
- the point estimates are the same as in round 1, where the upper bound was +0.010;
- what moved is the interval, after the correctness fix to the bootstrap (F2), which was
  made before this result was seen;
- it fails the 3-month-block sensitivity check (upper bound +0.003).

This is a development pass, not evidence that anyone can rely on. By the selection rule
(A2), V1 is the candidate for Pakistan's confirmation against `final-27.1`.

## Exploratory findings (24 September 2026; cannot decide a pass, PROTOCOL.md §8)

### Where the world correction loses: almost entirely Brazil

Per-country breakdown of ΔCRPS(candidate − `nbar`), round 1b, active countries, as a
contribution to the per-forecast mean:

| Candidate | Total | Brazil | Next two biggest losses | Total without the 3 biggest losers |
|---|---|---|---|---|
| V0 | +0.331 | **+0.371** | Ecuador +0.039, Israel +0.024 | −0.104 |
| V1 | +0.215 | **+0.318** | Ecuador +0.031, Myanmar +0.018 | −0.152 |
| V2 | +0.271 | **+0.276** | Colombia +0.110, Israel +0.015 | −0.131 |
| M2 | +0.428 | **+0.342** | Colombia +0.145, Myanmar +0.030 | −0.088 |

**Cause.** UCDP expanded its first-release coverage of Brazil over time. The share of
events captured at first release rose 11% (2021) → 54% (2022) → 88% (2023–24) → 113%
(2025). Every candidate learned the early gap and kept correcting for it after coverage
improved. In June 2022, V0 forecast 244 events against 88 actual; in March 2023, 516
against 161.

This is a **change in the reporting process itself**, not the short episodes the
candidates were built for. Removing Brazil would turn every candidate negative, but that
is post-hoc and is **not** claimed. Instead, candidate V5 (coverage-shift aware) was
registered before being built (PROTOCOL.md A5).

### Stronger statistical baselines (StatsForecast, `aegis explore`)

Same 38 origins, same countries, targets and truth. Point forecasts are turned into
negative-binomial distributions, with dispersion fitted to each model's own one-step
errors from the six months before each origin.

**World** (active countries):

| Model | CRPS | ΔCRPS vs `nbar` [95% CI] | Log | Cov80 |
|---|---|---|---|---|
| IMAPA | **9.609** | **−0.617 [−1.027, −0.165]** | 2.735 | 90.1% |
| TSB | 9.634 | −0.592 [−0.981, −0.296] | 2.695 | 90.3% |
| WindowAverage(6) | 9.747 | −0.479 [−0.872, −0.190] | 2.758 | 90.0% |
| AutoTheta | 9.815 | −0.410 [−0.944, +0.370] | 3.366 | 88.3% |
| CrostonOptimized | 10.039 | −0.187 [−0.644, +0.402] | 2.766 | 90.9% |
| `nbar` (protocol baseline) | 10.226 | — | 2.548 | 93.5% |
| V1 | 10.441 | +0.215 [−0.024, +0.472] | 2.453 | 94.1% |
| AutoETS | 10.451 | +0.225 [−0.718, +1.059] | 2.962 | 88.7% |
| V0 | 10.557 | +0.331 [+0.058, +0.578] | **2.450** | 94.0% |

**Pakistan** (8 units): V1 ranks **first** on both CRPS (1.674) and log score (1.683).
IMAPA is third (1.700), and all StatsForecast models do worse on log score.

**What this means:**
- The protocol's baseline `nbar` is **not** the strongest simple model worldwide.
  Intermittent-demand models (IMAPA, TSB), which are built for sparse counts, beat it
  significantly on CRPS. AEGIS's world CRPS gap to the best available simple model is
  therefore about 0.8, not 0.2.
- AEGIS's advantage is the **log score**, which puts less weight on large absolute
  errors: 2.45 against 2.70–3.37 for the StatsForecast models.
- Readiness test 4 (match established methods) is **not met** for the world.
- Next: the visibility correction applied on top of IMAPA/TSB (a candidate to register
  before building) may combine both strengths.

## v0.2 development round 1, superseded by round 1b (PROTOCOL.md §4–5)

Four observation-model candidates, fixed before any result, were run on the same 38 origins
(`results/backtest-20260923-2303`).

| Candidate | ΔCRPS vs `nbar` [95% CI] | Relative | ΔLog [95% CI] | Worse in % of countries | Nowcast ΔCRPS, age 1 |
|---|---|---|---|---|---|
| V0 (v0.1 estimator) | +0.391 [+0.094, +0.744] | −3.8% | −0.099 [−0.192, −0.033] | 54% | −1.99 [−2.88, −1.00] |
| V1 (recent months only) | +0.248 [−0.026, +0.541] | −2.4% | −0.098 [−0.193, −0.029] | 61% | −1.99 [−2.88, −1.00] |
| V2 (robust long-run median) | +0.353 [+0.166, +0.531] | −3.5% | −0.098 [−0.194, −0.028] | 45% | **−2.24 [−3.26, −1.31]** |
| V3 (live growth signal) | +1.453 [+0.796, +2.143] | −14.2% | −0.083 [−0.168, −0.020] | **25%** | +1.22 [−1.02, +3.39] |

**No candidate passes the pre-agreed rule.** What this round shows:
- **The hypothesis behind V3 was wrong as implemented.** A first-to-second-release growth
  signal does not predict the final count well where completeness is low. Its nowcast
  there is worse by +30 CRPS.
- **Better nowcasts do not automatically give better forecasts.** V2 has the best nowcast
  but still loses on the forecast. The loss therefore lies in how corrected history feeds
  the forecasting model, not only in the correction itself.
- **The mean CRPS is dominated by a few high-volume countries.** V3 is better than the
  baseline in 75% of countries and still loses on the mean. The primary metric stays as
  agreed; see PROTOCOL.md §8 for how a change could be proposed honestly.

## Pakistan provinces (national scope)

Same protocol: 8 units (7 provinces plus "not recorded"), 38 origins, 888 forecasts per
model (`results/pakistan/backtest-20260923-2255`).

| | Result |
|---|---|
| Reporting | UCDP's first releases for Pakistan are complete, and slightly over-report (completeness about 107%). No province is flagged. |
| AEGIS (V0) vs baseline | CRPS −0.090 [−0.210, +0.025] (5% better, **not significant**); log score **−0.071 [−0.117, −0.025]** (significantly better) |
| Closest candidate | V1: CRPS −0.108 [−0.229, +0.010] (6.1% better; the upper bound misses zero by 0.010) |
| Calibration | The baseline over-forecasts Pakistan's provinces (PIT mass in the low bins). AEGIS's PIT histogram is close to flat. |
| Decision | Does not pass yet. With 8 units and 38 origins there is little data; the confirmation test adds 2026. |

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
| R8 | End-to-end anti-leak test: a store truncated at the origin must give identical forecasts to the full store plus a fake future revision and final | Mutation-checked: it catches three planted future-*release* leaks. It did **not** cover the country universe; a future-only-country leak was later found by external review (PROTOCOL.md F1) and now has its own mutation-checked test |
