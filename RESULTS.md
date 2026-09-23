# AEGIS v0.1: first results

Backtest run 23 September 2026.

| Setting | Value |
|---|---|
| Origins | 42 forecast origins, 20 June 2022 → 20 December 2025, one per UCDP Candidate monthly release |
| Units | 139 countries × horizons of 1–3 months |
| Target | UCDP events per country-month |
| Truth | `final-26.1` (final data through December 2025) |
| Pairs | 17,097 paired forecasts per model; 9,721 for "active" countries (any event in the prior 12 months) |
| Reproduce | `aegis backtest` (about 8 minutes on a laptop) |

The full generated report is in `results/backtest-*/report.md`, and per-forecast scores
are in `scores.parquet`.

## Headline

| Question | Answer | Evidence |
|---|---|---|
| **Paper 1.** Does scoring on the data available at the time change measured skill? | **Yes in size, no in ranking.** Every model looks 4–10% worse on CRPS and loses 2–3 points of 80% interval coverage. The ranking `nbar < ma6 < naive` holds in both views | Table 1 |
| **E2.** Does the nowcast estimate the eventual count better than the raw count does? | **Yes overall, no where completeness is low.** Better at every age overall; **worse** in countries with estimated completeness below 80% | Table 2 |
| **Paper 2.** Does the visibility correction improve forecasts? | **Mixed. Not yet a win.** Better log score overall and better CRPS where Candidate data over-reports; much worse CRPS in low-completeness countries, which makes overall CRPS worse | Table 3 |
| Do visibility flags pick out untrustworthy forecasts? | **Consistent with yes.** WARN/ABSTAIN forecasts have 3–6× the error of OK ones. This is confounded by scale, because flagged countries tend to be high-volume | Table 4 |

The simple baseline still wins on the headline metric (CRPS). v0.1 does not claim that
AEGIS beats it.

## Table 1: Paper 1, final view vs vintage view (active countries)

| Model | CRPS final | CRPS vintage | Δ | Log final | Log vintage | Cov80 final | Cov80 vintage |
|---|---|---|---|---|---|---|---|
| naive | 12.49 | 13.43 | +7.5% | 2.93 | 3.26 | 91.7% | 89.3% |
| ma6 | 9.70 | 10.75 | +10.9% | 2.33 | 2.53 | 94.5% | 92.5% |
| nbar | 9.47 | 10.11 | +6.8% | 2.27 | 2.49 | 95.9% | 93.2% |

Retrospective evaluation on revised data makes every model look better than it could have
been in real time. The gap is largest for the six-month average. That model is most exposed
to under-reported recent months, since it averages them in with full weight. Rankings did
not change for these three models. Whether they change for richer models (VIEWS-style
ensembles, ShapeFinder) is the natural next test.

## Table 2: E2, nowcast vs raw count

| Vintage age | n | CRPS raw | CRPS nowcast | Diff [95% CI] | Diff where C < 0.8 |
|---|---|---|---|---|---|
| 1 (newest) | 3,364 | 9.01 | 7.43 | −1.58 [−2.04, −1.11] | **+3.86** (n = 302) |
| 2 | 3,361 | 7.91 | 7.01 | −0.91 [−1.29, −0.48] | **+6.31** (n = 223) |
| 3 | 3,356 | 7.40 | 6.91 | −0.49 [−0.91, −0.04] | **+10.05** (n = 202) |

## Table 3: Paper 2, `nbar+vis` minus `nbar` (vintage view; negative favours AEGIS)

| Slice | Mean diff | 95% CI (origin bootstrap) | n |
|---|---|---|---|
| All countries, CRPS | +0.20 | [+0.06, +0.35] | 17,097 |
| All countries, **log score** | **−0.034** | **[−0.048, −0.021]** | 17,097 |
| Active, CRPS | +0.35 | [+0.11, +0.61] | 9,721 |
| Active, C₁ < 0.8 | **+6.25** | [+4.20, +8.64] | 879 |
| Active, 0.8 ≤ C₁ < 1.0 | −0.10 | [−0.26, +0.05] | 6,266 |
| Active, C₁ ≥ 1.0 (Candidate over-reports) | **−0.55** | [−0.74, −0.38] | 2,576 |

## Table 4: visibility status (`nbar+vis`, active countries)

| Status | n | CRPS | Log | Cov80 | Mean PIT |
|---|---|---|---|---|---|
| OK | 8,731 | 8.27 | 2.24 | 94.4% | 0.47 |
| WARN | 855 | 26.94 | 4.23 | 86.7% | 0.53 |
| ABSTAIN | 135 | 47.87 | 4.45 | 91.9% | 0.34 |

## What the failure is telling us

The low-completeness slice is where AEGIS should help most, and it is where AEGIS fails.
Both the nowcast and the forecast **overshoot** there.

The ratio estimator averages past revision behaviour (18-month half-life). Low completeness
turns out to be **episodic**. For example, UCDP back-filled Ukraine heavily in spring 2024:
March 2024 went from 370 events reported to 1,181 final. When reporting recovers, the old
correction keeps inflating the new data.

In other words, completeness is itself non-stationary. That is the next research problem,
and it fits the thesis rather than refuting it.

## Bug found during this run

The first full backtest estimated older-age completeness at 0.08–0.64. The cause: the
store holds final releases only from 22.1 (May 2022). At origins before then, months
before 2021 were covered by no release, so they looked like "0 reported" against large
final counts. Those months are now excluded, and a regression test was added. That fix
turned Paper 2 from "clearly worse" into the mixed result above.

## Pre-registered plan for v0.2

To avoid tuning on the test set, v0.2 changes are chosen on origins **June 2022 → June
2024** and reported once on **July 2024 → December 2025**:

1. **Time-varying completeness.** A state-space or random-walk model on the log revision
   ratio per country, instead of a fixed-decay ratio.
2. **Robust estimation.** Log-ratio median, or a per-event hazard of being added or
   removed, so that one large back-fill cannot dominate.
3. **Shrink low-completeness corrections toward 1 in proportion to their uncertainty,**
   and propagate that uncertainty into the forecast mixture.
4. **Report two metrics alongside CRPS:** CRPS on log1p counts and per-country skill, so a
   few high-volume countries do not decide the verdict.

Success criterion, fixed in advance: `nbar+vis` beats `nbar` on **both** CRPS and log
score on the held-out origins, with the 95% CI excluding 0. If it doesn't, the baseline
stays the default and AEGIS reports that.
