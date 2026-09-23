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
- stays at **country level**. It publishes no sub-national cells, names no groups or
  individuals, and does no predictive policing, targeting or scanning;
- is not marketed to, or tailored for, any military, police or intelligence body;
- will review dual-use and export-control questions **before** any change to that
  position, and record the decision here.

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
