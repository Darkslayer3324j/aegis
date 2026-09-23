# AEGIS: adversarial prior-art review and build plan

> **Read §8 (Corrections) first.** Four statements below were corrected after review.

Researched 23 September 2026. Every claim below links to a source I opened or saw
in search results. Anything I did not check against a primary page is marked
`[VERIFY]`.

---

## 0. Summary

1. **The "god's eye" dashboard has already been built.** [World Monitor](https://github.com/koala73/worldmonitor)
   (AGPL-3.0) had about 65,500 GitHub stars by July 2026. It has a 3D WebGL globe, 65+ feeds,
   an official CLI and an MCP surface. Another globe plus news map would be a clone of a
   much larger project. **The only defensible part of AEGIS is the epistemic layer**:
   observation modelling, vintages and abstention.
2. **Most of the individual components are already published.** Hawkes models on ACLED,
   DTW analogues, conformal intervals, entropy-based forecastability, adaptive elastic-net,
   ensemble weighting by CRPS and HMMs on GDELT all have papers from 2025–2026 (§2).
3. **Three gaps are real, recent and testable:**
   - **Nowcasting ACLED/UCDP reporting delays and feeding that into forecasts.**
     Razakason et al. (March 2026) measured ACLED delays and said outright that nowcasting
     is the *next* step. It has not been built for conflict data. Epidemiology already has
     the tooling ([epinowcast](https://github.com/epinowcast/epinowcast)).
   - **Vintage-aware evaluation using UCDP Candidate monthly releases.** UCDP publishes
     numbered monthly Candidate versions that are later replaced by the annual GED. That is a
     ready-made real-time dataset of vintages. I found no paper that re-scores conflict
     forecasts against the vintage that was available at forecast time.
   - **Hawkes/count dynamics with an explicit, time-varying detection probability for
     conflict.** Seismology already does this (ETASI, rate-dependent incompleteness).
     The 2026 Bayesian Hawkes paper on ACLED treats the observed data as complete.
4. **Some of your hypotheses have strong counter-evidence and should be downgraded:**
   - H2 (disagreement predicts failure): in meteorology, spread–skill correlation rarely
     exceeds 0.5. In streaming tree ensembles, disagreement-based drift detection
     *underperforms* loss-based detectors (2026).
   - Adaptive ensemble weights: the forecast-combination puzzle. On the COVID-19 hubs,
     equal weights were hard to beat.
   - Four-way uncertainty decomposition: 2024–2025 benchmarks show that aleatoric and
     epistemic estimates are highly correlated in practice, not separate quantities.
   - Selective prediction under shift: accuracy gains from abstaining fall to zero or turn
     negative as the shift gets worse.
   - LLM forecasting of conflict: an 11-feature logistic regression beat GPT-4o and
     Llama-3.3-70B at every coverage tier (2026).
5. **Recommended thesis, narrowed:** *Observer-aware real-time conflict forecasting.
   Nowcast reporting completeness from vintage data, propagate it into count forecasts, and
   test whether this improves calibration during reporting disruptions, compared with an
   autoregressive baseline scored against the vintages available at the time.* It is
   publishable, feasible for one person, and the literature supports it.

---

## 1. Classification of each novelty candidate

Scale taken from §64 of your brief.

| # | Candidate | Verdict | Closest prior art |
|---|---|---|---|
| 1 | Latent reality + explicit observation model for conflict | **Related prior art → Strong gap for the forecasting version** | AfroGrid latent-variable model fills in missing ACLED/UCDP/SCAD values ([ref](https://libguides.princeton.edu/politics/conflict)); REMSE mixture of signal and spurious-event processes ([Network Science](https://www.cambridge.org/core/journals/network-science/article/all-that-glitters-is-not-gold-relational-events-models-with-spurious-events/F5B3E40C3AF7F9A60F1B27C9154F20C7)); Vesco et al. 2026 under-reporting elicitation ([JCR](https://journals.sagepub.com/doi/full/10.1177/00220027261423826)); HRDAG multiple-systems estimation (retrospective counting, not forecasting) |
| 2 | Vintage-aware forecasting on UCDP/ACLED | **Strong research gap candidate** | Economics treats real-time vintages as standard ([revision risk, 2026](https://arxiv.org/pdf/2607.05882)). For conflict, only the UCDP Candidate paper, which showed Candidate data lifts average precision by 20–40% ([Hegre et al. 2020](https://journals.sagepub.com/doi/10.1177/2053168020935257)), and VIEWS's summary-event handling fix, October 2025 ([VIEWS](https://viewsforecasting.org/news/improved-handling-of-ucdp-summary-events-in-views-forecasts-and-api-data/)). Neither scores forecasts per vintage |
| 3 | Reporting delay as a stochastic process fed into forecasts | **Strong research gap candidate (most promising)** | [Razakason, Racek, Thurner, Kauermann, arXiv 2603.25964, March 2026](https://arxiv.org/abs/2603.25964): grouped proportional-hazards model of ACLED delays; more than half of events reported within 2 weeks; slower in restrictive regimes; nowcasting named as future work. Method to borrow: [epinowcast](https://github.com/epinowcast/epinowcast), [Biometrics 2026 Bayesian nowcasting](https://academic.oup.com/biometrics/article/82/1/ujag020/8492787) |
| 4 | Hawkes + latent observation | **Related prior art (other domains), gap in conflict** | Crime: WGAN likelihood-free Hawkes with unreported events ([arXiv 2502.07111](https://arxiv.org/abs/2502.07111)); ABC-Hawkes with missing events ([2006.09015](https://arxiv.org/abs/2006.09015)). Seismology: ETASI / rate-dependent incompleteness ([Hainzl GJI](https://academic.oup.com/gji/article/236/3/1609/7512212), [Mizrahi 2021](https://arxiv.org/pdf/2105.00888), [GJI 2025](https://academic.oup.com/gji/article/242/1/ggaf156/8123633)). Conflict Hawkes without an observation model: [Browning et al., JRSS-A 2026](https://doi.org/10.1093/jrsssa/qnag039) |
| 5 | Historical analogues (DTW) | **Established** | ShapeFinder, [Schincariol, Frank & Chadefaux, JPR 2025](https://journals.sagepub.com/doi/full/10.1177/00223433251330790); 3D spatio-temporal extension ([arXiv 2604.21067](https://arxiv.org/pdf/2604.21067)) |
| 6 | Analogues + observation uncertainty | **Weak novelty** | A small variation on #5. Worth doing only as an ablation |
| 7 | Forecastability / regime-dependent predictability | **Established for conflict** | [Schincariol & Chadefaux 2026, "Echoes of conflict", PSRM](https://www.cambridge.org/core/journals/political-science-research-and-methods/article/echoes-of-conflict-quantifying-redundancy-in-fatality-time-series/74CE45D34DD299547F7378672B8AE150): entropy + DTW over 130 countries, 1989–2023; low-intensity conflicts more forecastable than high-intensity ones |
| 8 | "Is forecastability loss caused by missing observations?" | **Strong research gap candidate** | Nobody separates intrinsic entropy from entropy caused by observation. This is your "predictive information loss" idea (§20) and could be tested with #3 |
| 9 | Conformal intervals for conflict | **Established** | [Bin-conditional CP, Political Analysis 2026](https://arxiv.org/abs/2410.14507); [CP for Markov processes, April 2026](https://arxiv.org/abs/2604.25139) |
| 10 | Model disagreement as early warning | **Weak novelty, with negative evidence** | Meteorology spread–skill correlation "rarely exceed[s] 0.5" ([AMS glossary](https://glossary.ametsoc.org/wiki/Spread_skill_correlation)); disagreement-based drift detection underperforms ([arXiv 2605.12803](https://arxiv.org/abs/2605.12803)) |
| 11 | Forecasting the reliability of your own forecast | **Established in ML/forecasting** | FFORMPP forecast-error prediction ([IJF](https://www.sciencedirect.com/science/article/abs/pii/S0169207021001138)); selective prediction literature. New only when applied to conflict with vintage-true errors |
| 12 | Four-way uncertainty decomposition | **Related prior art, with methodological warnings** | [NeurIPS 2024 benchmark](https://proceedings.neurips.cc/paper_files/paper/2024/file/5afa9cb1e917b898ad418216dc726fbd-Paper-Datasets_and_Benchmarks_Track.pdf): decomposed estimates are "internally highly correlated". [Position 2025](https://arxiv.org/html/2505.23506v4): epistemic estimation is fundamentally incomplete. Present only observation uncertainty (which can be derived from #3) as a separate component; do not claim four orthogonal quantities |
| 13 | Adaptive regime-conditional ensemble weights | **Related prior art, with negative evidence** | Forecast-combination puzzle; COVID hubs: adaptive weighting "modest and configuration-dependent" ([arXiv 2606.18575](https://arxiv.org/html/2606.18575)); VIEWS challenge ensemble uses inverse-CRPS weights ([JPR 2025](https://academic.oup.com/jpr/article/62/6/2070/8435449)); dynamic elastic net ([arXiv 2205.14073](https://arxiv.org/pdf/2205.14073)) |
| 14 | Full integrated stack (all eight layers) | **Unfalsifiable as stated** | Too many parts to attribute any gain to one of them. Publish the parts separately |
| 15 | Closed-loop information acquisition | **Related prior art (active learning / VoI)** | Treat as a later research topic, not an MVP feature |
| 16 | Forecast feedback / endogeneity | **Established as a concept** | [Chadefaux & Schincariol, EPJ Data Science 2025](https://link.springer.com/article/10.1140/epjds/s13688-025-00599-x); theory only, since it cannot be tested ethically on real populations |

**Nothing here is "proven novel".** Three items (#2, #3, #8) are strong gap candidates.
They need a narrower Google Scholar and SSRN search before any claim is published `[VERIFY]`.

---

## 2. Answers to your 14 questions (§65)

1. **Explicit latent reality + observation model for conflict?** In parts. AfroGrid
   (imputation), REMSE (spurious events), Vesco et al. (fatality under-reporting) and
   Weidmann's reporting-bias work all exist. **None of them is a real-time forecasting
   model with a dynamic detection probability.**
2. **Joint dynamics + reporting + forecastability + disagreement + regime + abstention?**
   Not found. It is also not worth attempting as one model (see #14 above).
3. **Vintage-aware forecasting on UCDP/ACLED?** Not found as an evaluation protocol. The
   raw material exists: numbered UCDP Candidate releases (for example monthly **26.0.7**,
   covering the last 4–18 months, replaced at each annual GED release,
   [UCDP downloads](https://ucdp.uu.se/downloads/)). Whether old Candidate versions stay
   archived and downloadable: `[VERIFY]`. If they do not, start snapshotting now; each
   month you wait is a vintage lost.
4. **Disagreement as an early warning of model failure?** Tested in meteorology and drift
   detection, with mostly weak or negative results. Keep it as a hypothesis to test, not
   as a main pillar.
5. **Forecasting your own reliability?** Yes in general forecasting (FFORMPP, meta-learning).
   Not in conflict with vintage-true targets.
6. **Reporting delay as a forecastable process fed into forecasts?** Measured for ACLED
   (March 2026) and flagged as future work. **This is the opening.**
7. **Hawkes + latent observation + regime switching + adaptive weighting?** Hawkes + missing
   data exists in crime and seismology. The full combination was not found, and would be
   too complex to identify from sparse conflict data anyway.
8. **Analogues + observation uncertainty?** Not found. Weak novelty.
9. **Four-way uncertainty separation in conflict?** Not found. The ML literature says the
   decomposition is unreliable, so claim less.
10. **Equivalent systems in other domains?** Yes, and they make the *architecture* non-novel:
    - epidemiology nowcasting (epinowcast) = delay + truncation + latent incidence
    - seismology ETASI = self-exciting + rate-dependent detection
    - economics real-time vintages
    - NWP data assimilation

    What is new is applying them to conflict event data, which is legitimate and publishable.
11. **Patents or deployed systems?** [US 11,526,776](https://patents.justia.com/patent/11526776)
    (geopolitical event prediction, 2022); [ACLED CAST](https://acleddata.com/methodology/cast-methodology)
    (LightGBM, hierarchical reconciliation, six 4-week horizons, public accuracy; code at
    [ACLED/cast-public](https://github.com/ACLED/cast-public)); VIEWS; ICEWS; World Monitor.
    I did not do a freedom-to-operate search `[VERIFY]`. For academic, open-source work this
    matters little.
12. **What is publishable?**
    - (a) Nowcasting ACLED/UCDP under-reporting and its effect on forecast calibration.
    - (b) "How much do vintages change measured conflict-forecast skill?" A clean empirical
      paper, a good first publication.
    - (c) Decomposing forecastability loss into intrinsic and observation-induced parts.
13. **Defensible contribution:** (b) first, because it is cheapest and certain to produce
    a result. Then (a), then (c) built on (a).
14. **Experiments needed:** see §4.

---

## 3. Evidence that could kill the idea (§66)

| Threat | Evidence | Effect on AEGIS |
|---|---|---|
| Simple models win | Autoregressive models match or beat complex ones, and structural covariates often *degrade* performance ([Chadefaux & Schincariol 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC12638363/)) | Every layer must beat an AR / negative-binomial AR model scored on vintages. Your H9 already says this; make it the gate on every component |
| Conflict is intrinsically high-entropy | Entropy higher than climate data and similar to earthquakes; high-intensity conflict least predictable ([Echoes of conflict 2026](https://www.cambridge.org/core/journals/political-science-research-and-methods/article/echoes-of-conflict-quantifying-redundancy-in-fatality-time-series/74CE45D34DD299547F7378672B8AE150)) | The ceiling is low. Aim for calibration, not sharpness |
| Disagreement is a weak error signal | Spread–skill r ≤ ~0.5; disagreement drift detection underperforms | Downgrade H2 to an exploratory hypothesis |
| Learned weights lose to equal weights | Forecast-combination puzzle; COVID hub results | Default to equal or inverse-CRPS weights. Adaptive weights must beat both |
| Abstention breaks under shift | Selective accuracy gains fall to zero or turn negative with severity (seen in search results for [arXiv 2608.16614](https://arxiv.org/pdf/2608.16614); which paper made the claim `[VERIFY]`); confidence drifts over time in malware classifiers ([arXiv 2505.22843](https://arxiv.org/html/2505.22843)) | Abstention must be triggered by **external** signals (observation completeness, data staleness), not by the model's own confidence |
| Uncertainty decomposition is unreliable | NeurIPS 2024 benchmark | Report observation uncertainty (derived from the delay model) + total predictive interval. Nothing more |
| GDELT is noisy | Key-field accuracy about 55%, about 20% redundancy ([MDPI 2025](https://www.mdpi.com/2306-5729/10/10/158)); one protest audit found 21% of URLs described a real protest ([Comm. Methods & Measures 2022](https://www.tandfonline.com/doi/full/10.1080/19312458.2022.2128099)) | Use GDELT only as a sensor for *media attention and coverage*, never as ground truth. This supports your §22 idea |
| LLMs are worse than simple models | Logistic regression on 11 features beat GPT-4o / Llama-3.3-70B; LLMs fail differently by media coverage, with a 224× coverage gap ([arXiv 2607.00018](https://arxiv.org/abs/2607.00018)) | LLMs only for extraction and explanation, never as the forecaster. The coverage gap itself is a useful observation-model covariate |
| Too complex to identify | Sparse monthly counts cannot identify dynamics, detection, regime and weights at the same time | Build in stages; identify detection from vintages and delays, not from the counts alone |

---

## 4. Experiments

| ID | Question | Design | Pass criterion |
|---|---|---|---|
| E1 | Do vintages change measured skill? | Take the UCDP Candidate snapshots. At each origin *t*, fit the AR, negative-binomial AR and ShapeFinder models on the vintage available at *t* and score them against final GED; repeat with final GED as input | A material change in ranking or in CRPS (report bootstrap intervals). A null result is still publishable |
| E2 | Can reporting completeness be nowcast? | Fit a delay distribution on ACLED `timestamp` minus `event_date` (hazard model; covariates: event type, fatalities, V-Dem press freedom, country); nowcast the counts for the latest weeks | Nowcast beats the "last observed" count on CRPS for the most recent 1–4 weeks |
| E3 | Does feeding the nowcast into forecasts help? | Compare AR forecasts vs AR on nowcast-corrected inputs, scored walk-forward on vintages | Better CRPS / log score and better PIT calibration, **especially during injected or natural reporting disruptions** |
| E4 | Robustness to disruption | Simulate outages (drop X% of sources for a region) and pick natural cases such as internet shutdowns | Degradation smaller than baseline; abstention/observation flag raised before the forecast error |
| E5 | Is forecastability loss caused by missing observations? | Compute entropy/redundancy on raw vs nowcast-corrected series | Measurable difference between the two |
| E6 | Disagreement as error predictor (exploratory) | Correlate ensemble dispersion with realised CRPS on vintages | Report whatever comes out; the prior expectation is weak |
| E7 | Selective prediction | Risk–coverage curves: abstain on the observation-completeness signal vs on model confidence | The completeness trigger beats the confidence trigger |

**Scoring:**
- CRPS, log score, Brier (for escalation thresholds), PIT histograms, interval coverage,
  risk–coverage curves.
- Walk-forward only.
- Units: country-month (compatible with VIEWS/UCDP) and admin-1-week (ACLED/CAST scale).

---

## 5. System design: the CLI god's-eye

### 5.1 How AEGIS should differ from World Monitor

World Monitor is a live news map. AEGIS should show **what the world probably looks like
underneath what is being reported, and how much to trust that picture.** Every region on
the map carries three layers:

1. **Observed**: reported events.
2. **Estimated**: nowcast latent activity, with an interval.
3. **Visibility**: estimated reporting completeness. A region that is dark because nothing
   happened is drawn differently from a region that is dark because nobody can see it.

That third layer is the visual signature no existing dashboard has.

### 5.2 Interface: one command, two views

```
aegis                 # opens the full-screen terminal "god's eye" (default)
aegis --globe         # also serves a local 3D globe at http://127.0.0.1:<port> and opens the browser
aegis sync            # pull new data + snapshot today's vintage
aegis forecast        # run the walk-forward models
aegis explain <ISO3>  # the evidence behind one region's forecast
aegis backtest        # vintage-aware evaluation report
```

| Option | For | Against |
|---|---|---|
| **Terminal TUI (Textual, Python)** | A real CLI, runs over SSH/VPS, strong hacker aesthetic, same language as the models | Map resolution limited to braille characters (2×4 dots per cell); globe rotation is a gimmick at that resolution |
| **Local web globe (CesiumJS / globe.gl / deck.gl) launched from the CLI** | A true 3D god's-eye look, smooth zoom, heatmaps | Needs a browser; more frontend work |
| **Recommended: both, one Python backend** | The TUI is the default; `--globe` serves the web view from the same DuckDB/API | Two frontends to maintain; build the TUI first |

**TUI layout (Textual):**

```
┌ AEGIS ── 2026-09-23 14:02Z ── vintage UCDP-C 26.0.8 · ACLED synced 2h ago ──────────┐
│ [ braille world map: colour = latent risk, dithering = low visibility ]              │
│                                                                                       │
├ WATCHLIST ───────────────┬ SELECTED: SDN ─────────────────┬ SYSTEM HEALTH ───────────┤
│ SDN ▲ 0.71 vis 38% ABST  │ observed 41 · nowcast 63 [52–80]│ baseline CRPS  1.00       │
│ MMR ▲ 0.55 vis 61%       │ regime: persistent-high         │ AEGIS CRPS     0.93       │
│ HTI ─ 0.42 vis 70%       │ visibility ↓ 22pp in 4 wks       │ coverage 90% → 88.1%      │
│ ...                      │ decision: ABSTAIN (visibility)  │ stale feeds: 1            │
└──────────────────────────┴─────────────────────────────────┴───────────────────────────┘
 [/] search  [e] evidence  [h] history  [g] globe  [b] backtest  [q] quit
```

Keys and panels map to §45 of your brief. The system-health panel always shows the
baseline score next to the AEGIS score, so the dashboard itself makes the "boring model"
test visible.

**Map rendering:** Textual with a braille canvas; country polygons from Natural Earth
(public domain). [MapSCII](https://terminaltrove.com/mapscii/) and
[TerminalMap](https://github.com/psmux/TerminalMap) show the technique works.

### 5.3 Architecture

```
ingest/     UCDP GED + Candidate API, ACLED API, GDELT 2.0 (attention sensor), ReliefWeb,
            GDACS, USGS  → raw files, never overwritten
vintage/    immutable daily snapshots (Parquet, content-hashed) → the "as known at t" store
store/      DuckDB: events, snapshots, forecasts, evidence edges
models/     L0 baselines (naive, MA, AR, NB-AR) · L1 delay/nowcast · L2 Hawkes (+detection)
            · L3 ShapeFinder analogues · L4 ensemble (equal / inverse-CRPS)
            · L5 abstention (external triggers)
eval/       walk-forward on vintages · CRPS / log / PIT / risk-coverage
explain/    evidence graph (events → sources → features → forecast) → `aegis explain`
ui/tui/     Textual app      ui/globe/  static web globe + local FastAPI
cli.py      Typer entry point → `aegis`
```

**Stack:**
- Python 3.12; Typer (CLI), Textual (TUI), DuckDB + Parquet (store).
- Models: statsmodels, PyMC or NumPyro (Bayesian nowcast/Hawkes), sktime or tslearn (DTW),
  properscoring / scoringrules (CRPS).
- Globe: FastAPI serving a globe.gl or CesiumJS page.

This is a proposed stack, not a decided one. Choosing it is a critical decision under your
CLAUDE.md rule, so run the council before implementation starts.

### 5.4 Data sources and licences

| Source | Role | Licence / access |
|---|---|---|
| UCDP GED + Candidate | Ground truth + **vintages** | CC BY 4.0, free ([UCDP](https://ucdp.uu.se/downloads/)). Whether the API now needs a token: `[VERIFY]` |
| ACLED | Weekly events + **reporting timestamps** (the delay model depends on these) | Free myACLED account. **The EULA forbids giving anyone direct access to raw data and requires published outputs to be "transformative"** ([ACLED EULA](https://acleddata.com/eula), [FAQ](https://acleddata.com/faq/how-can-i-access-and-use-acled-data)). So AEGIS cannot ship ACLED data in the repo or show raw ACLED rows on a public instance. Each user brings their own key |
| GDELT 2.0 | Media-attention / coverage sensor | Free, open |
| V-Dem / RSF press freedom | Observation-model covariates | Free (licence per dataset: `[VERIFY]`) |
| ReliefWeb, GDACS, USGS | Humanitarian and hazard context layers | Free public APIs |
| Natural Earth | Map polygons | Public domain |
| CISA KEV, NVD | Cyber extension (Phase 9) | Public |

### 5.5 Scope limits built into the code

These follow from your §67:

- The smallest spatial unit is admin-1 or a grid cell of at least 0.5°.
- Named people are never stored.
- Actor names are kept only as the public organisation labels already present in UCDP/ACLED.
- There is no feature that scans anything. Everything is fetched from a public API.
- Stay out of predictive policing entirely. The closest Hawkes-with-under-reporting work
  comes from there ([2502.07111](https://arxiv.org/abs/2502.07111)); borrow the maths, not
  the application.

---

## 6. Build order

Each phase ends with a working `aegis` command.

| Phase | Deliverable | Gate |
|---|---|---|
| 1 | `aegis sync` for UCDP + ACLED + daily vintage snapshots; **start snapshotting on day one** | Snapshots reproducible and hashed |
| 2 | `aegis` TUI v0: map + watchlist from observed counts only | Opens in under 2 s on the cached store |
| 3 | Baselines + walk-forward on vintages → `aegis backtest` (**E1**) | E1 result written up (first paper draft) |
| 4 | Delay model + nowcast → visibility layer on the map (**E2, E3**) | Beats last-observed nowcast |
| 5 | Abstention on external triggers + `aegis explain` evidence graph (**E7**) | Risk–coverage curve beats confidence-only |
| 6 | Hawkes with detection probability, ShapeFinder, ensemble (**E4–E6**) | Each component beats AR on vintages, or is removed |
| 7 | `--globe` web view | — |
| 8 | Cyber / other domains | Only after 3–6 hold up |

---

## 7. Remaining searches before any novelty claim

These need Google Scholar / SSRN / Semantic Scholar with full-text access, which I did not
have here:

- "nowcasting" AND ("ACLED" OR "UCDP" OR "conflict events") after March 2026. Someone may
  already be working on the Razakason follow-up; their group (LMU Munich, Kauermann) is the
  obvious candidate.
- "real-time" / "vintage" AND "UCDP Candidate" forecast evaluation.
- ICEWS / POLECAT revision behaviour. The MDPI 2026 GDELT-vs-POLECAT comparison
  ([doi](https://doi.org/10.3390/data11070158)) returned 403, so it is unread.
- Freedom-to-operate on the geopolitical-prediction patents (only needed if AEGIS is ever
  commercialised).

---

## 8. Corrections

Logged, numbered and kept visible rather than edited away. Raised in review
(ChatGPT, 23 September 2026) and checked against sources before being accepted.

| # | Date | What was wrong | Correction | Source |
|---|---|---|---|---|
| C1 | 23 Sep 2026 | §0 and §5.1 give World Monitor as ~65,500 stars (a July 2026 figure from a secondary blog) | **87.3k stars, 13.3k forks** on the repository page on 23 Sep 2026. The conclusion stands and is stronger: don't compete on the dashboard | [koala73/worldmonitor](https://github.com/koala73/worldmonitor) |
| C2 | 23 Sep 2026 | §1 row 1 and §2 Q1 cite AfroGrid, REMSE and Vesco et al., but leave out the older, directly relevant work on under-reporting. That makes the gap look wider than it is | Explicit models of under-reporting in event data go back at least to **Weidmann (2016, AJPS)** on reporting bias in conflict data and **Cook, Blas, Carroll & Sinha (2017, *Political Analysis* 25(2):223–240)**, a maximum-likelihood estimator separating the true event process from source-specific under-reporting across multiple sources. **Never claim AEGIS is the first to model under-reporting.** The defensible gap is narrower: *estimate current completeness from reporting delays and revisions in real time, use it inside short-horizon probabilistic forecasts, and evaluate the whole procedure only on information that existed at the forecast origin* | [Cook et al. 2017](https://pubmed.ncbi.nlm.nih.gov/29104409/); [Weidmann 2016](https://www.researchgate.net/publication/280916538_A_Closer_Look_at_Reporting_Bias_in_Conflict_Event_Data) |
| C3 | 23 Sep 2026 | §5.1 describes the visibility layer as how much of the world AEGIS "can see" | Unobserved events cannot be counted directly. The quantity is **estimated observation completeness**, C(c, a) = E[count reported by vintage age a] / E[eventual final count], learned from past revision pairs. The code and interface use this term | — |
| C4 | 23 Sep 2026 | §2 Q3 marks archived UCDP Candidate versions as `[VERIFY]` | Verified: UCDP archives every monthly Candidate release (global from 20.0.10) plus quarterly cumulative releases, and every final GED. AEGIS v0.1 ingests 95 of them (2021-01 → 2026-08) | [UCDP archive](https://ucdp.uu.se/downloads/olddw.html) |

**Revised research programme** (agreed after review):

1. **Paper 1, the measurement problem.** Does evaluating conflict forecasts on revised
   (final) data instead of the data that existed at the time change measured skill or
   model rankings?
2. **Paper 2, the visibility problem.** Delay/revision model → nowcast → forecast.
   Compare an autoregressive model with and without the visibility correction,
   especially where reporting is slow.
3. **Paper 3, the predictability problem.** Only after 1 and 2: how much apparent
   unpredictability remains after correcting for incomplete observation?

Model disagreement, four-way uncertainty decomposition and confidence-based abstention
are downgraded to diagnostics. Abstention in AEGIS is triggered only by an impaired
observation process (low completeness, high revision volatility, a silent feed after
recent activity), never by model confidence.
