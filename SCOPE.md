# AEGIS scope

Adopted 23 September 2026, after a five-advisor review of the proposal to make AEGIS
"useful enough that countries can use it to predict threats".

## What AEGIS is

A research-grade, aggregate-only forecaster of **recorded** organised-violence events
per country-month. It is built from public UCDP data, and its evaluation is honest about
how complete that data is.

## What AEGIS is not, and does not claim to be

- **Not a threat-prediction or national-security system.** The phrase "countries can use
  it to predict threats" is retracted. It named no user, no decision and no authority, so
  it could not be validated.
- **Not decision-ready.** On its own pre-agreed primary metric (CRPS), the visibility
  correction does not yet beat a simple baseline (RESULTS.md). It fails worst where
  reporting is weakest, which is exactly where operational users would rely on it.
- **Not a statement about anyone's personal safety,** and not travel or security advice.

A claim of operational usefulness would need all three of the following:
1. a named user, and the decision it informs;
2. validation against that decision, including the asymmetric cost of a false "OK"
   during an onset versus a false "WARN";
3. a passed confirmatory test under PROTOCOL.md.

None of these exists today.

## Dual use

A public violence forecaster can be pointed at any population by anyone. AEGIS
therefore:
- stays at **country level, or province level for reviewed national scopes** (currently
  Pakistan; see below). It publishes nothing finer, names no groups or individuals, and
  does no predictive policing, targeting or scanning;
- is not marketed to, or tailored for, any military, police or intelligence body;
- will review dual-use and export-control questions **before** any change to that
  position, and record the decision here.

## Readiness: what "good enough to rely on" requires

The owner's standard (23 September 2026): *if it fails its tests, it is not ready.* These
are the tests. AEGIS may be described as reliable only when every row is **met**.

| # | Test | How it is checked | Status (24 Sep 2026) |
|---|---|---|---|
| 1 | Engineering integrity: no leakage, reproducible | `pytest` (46 tests, incl. mutation-checked future-release and future-country leak tests); pinned truth and commit | **met** |
| 2 | Beats the simple baseline on development data | PROTOCOL.md §5 decision rule over 38 origins | world: not met. **Pakistan: met, borderline** (V1, round 1b) |
| 3 | Beats it on data never seen | Single confirmatory run against `final-27.1` (about June 2027) | pending |
| 4 | Matches or beats established systems on the same targets | Head-to-head with VIEWS (country-month) and ACLED CAST (province-level; needs the user's own ACLED key) | not started |
| 5 | Calibrated: the 80% range covers 75–85% | Coverage in the backtest (currently 91–94%: ranges too wide to be useful) | not met |
| 6 | A prospective record | At least 12 months of forecasts archived *before* their outcomes were known, then scored | not started |
| 7 | A named user and decision, with a harm analysis | Written with that user: what action the forecast informs, and the cost of a false OK during an onset vs a false WARN | not started |

## Province-level scope (dual-use review, 23 September 2026)

The owner asked for Pakistan-specific forecasting, where terrorism is a major concern.
Reviewed before building:

- **Granularity:** first-level administrative units (provinces), monthly. The same
  granularity is published openly for every country by ACLED CAST, so AEGIS adds no new
  capability for misuse at this level. **District, city or grid-cell forecasts are out of
  scope** without a new review.
- **Content:** counts by UCDP violence type ("state vs armed groups", "attacks on
  civilians", "between armed groups"). **No actor, group or individual is named**
  anywhere in the interface or summaries.
- **"Terrorism"** is not a UCDP category. AEGIS does not claim to forecast terrorism as
  such; it forecasts recorded organised violence, which in Pakistan is dominated by
  fighting between the state and armed groups and by attacks on civilians.
- **Purpose:** research and preparedness framing only, under all the rules above. It is
  not marketed to military, police or intelligence users.

## Globe view (24 September 2026)

`aegis globe` adds a 3D view within the same limits:
- served on 127.0.0.1 only;
- forecasts at country or province level only;
- recorded events sent to the browser **only as counts per ~55 km cell** (0.5°). No
  individual event coordinates, sources or actor names leave the server
  (`tests/test_globe.py` checks this);
- the same template evidence summaries.

The owner asked for a view to "see and monitor the location in depth". "In depth" stops
at these limits; district-, city- or event-level drill-down needs a new dual-use review
first.

## Evidence panel wording rules

The per-country "why" summary must:

| Rule | Detail |
|---|---|
| Describe evidence, not danger | Never "dangerous", "safe", "threat", "risk level" or advice verbs ("avoid", "evacuate"). Say "AEGIS expects roughly X–Y recorded events next month (80% range)." |
| Be generated, not written | Fixed templates filled from numbers the model actually used; no free-text LLM prose. Every sentence maps to a model input or output. |
| Put visibility first | At WARN: "Reporting from here looks incomplete; real activity may be higher than shown." At ABSTAIN: no number at all. |
| Show its track record | "In backtests, the outcome fell outside the 80% range N% of the time here (n forecasts)." |
| Never reassure by silence | A low or zero count is always paired with its visibility. A quiet feed is not a quiet world. |
| Carry a fixed footer | "Counts of past recorded events and a statistical estimate of future ones. Not a statement about personal safety. Not travel or security advice. Source: UCDP." |

`tests/test_evidence.py` enforces these rules mechanically.

## Recurring pattern to watch

The pull toward state-level framing ("god's eye", "countries can use it") has come up
more than once in this project. Each time, the answer is the same: aim ambition at rigour
and a narrow, testable claim, not at reach.
