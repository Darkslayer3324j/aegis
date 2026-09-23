"""Vintage-aware walk-forward backtest.

Two questions, answered at every historical origin and scored against one *pinned*
final release:

* **Paper 1, the measurement problem.** Does scoring models on the data that existed at
  the time (vintage view) instead of revised data (final view) change how good they look,
  or which one looks best?
* **Paper 2, the visibility problem.** Does correcting the vintage view for incomplete
  reporting (``nbar+vis``) beat the same model without the correction (``nbar``)?

Inference. Forecasts made at nearby origins share training data, overlapping horizons and
slowly changing country dynamics, so neither forecasts nor origins are independent.
Intervals come from a **moving-block bootstrap over consecutive origins**: 6-month blocks
are primary, 3 and 9 are reported as sensitivity checks. The effective sample size is
closer to the number of origins than to the number of forecasts.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from . import config
from . import observation as ob
from .models import forecast_all
from .pipeline import HORIZONS, CoverageGap, final_view, run_origin
from .scoring import CountForecast
from .vintage import VintageStore, month_from_index

BASELINES = ("naive", "ma6", "nbar")
HISTORY_VERSION = 3  # bump when build_history changes, to invalidate the cache
BLOCK = 6            # primary bootstrap block length, in origins (months)
SENSITIVITY_BLOCKS = (3, 9)
REPS = 4000


def load_history(store: VintageStore, progress: Callable | None = None) -> pd.DataFrame:
    """Historical snapshots, cached on disk and rebuilt when the manifest changes."""
    cache = config.HOME / "history_cache.parquet"
    stamp = config.HOME / "history_cache.stamp"
    key = f"{HISTORY_VERSION}:{config.MANIFEST.stat().st_mtime_ns}"
    if cache.exists() and stamp.exists() and stamp.read_text(encoding="utf-8") == key:
        return pd.read_parquet(cache)
    hist = ob.build_history(store, store.origins(), progress=progress)
    hist.to_parquet(cache)
    stamp.write_text(key, encoding="utf-8")
    return hist


def code_version() -> dict:
    root = Path(__file__).resolve().parents[2]
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
                              text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "src"], cwd=root,
                                    capture_output=True, text=True).stdout.strip())
        return {"commit": head, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def run(start: str = "2022-06-01", end: str | None = None, target: str = "events",
        draws: int = 40, truth: str | None = None,
        progress: Callable[[str], None] = print) -> Path:
    store = VintageStore.load()
    history = load_history(store)
    finals = [r.name for r in store.releases if r.kind == "final"]
    truth_name = truth or finals[-1]
    if truth_name not in finals:
        raise ValueError(f"unknown truth release {truth_name}; available: {', '.join(finals)}")
    truth_df, truth_rel = store.truth(truth_name)
    manifest = {r["name"]: r for r in json.loads(config.MANIFEST.read_text(encoding="utf-8"))}
    truth_end = truth_rel.cover_end
    y_truth = truth_df[target]
    candidates = store.origins(start, end)
    origins = [o for o in candidates if store.last_data_month(o) + 1 <= truth_end]
    progress(f"{len(origins)} origins, truth = {truth_name} (pinned; through {month_from_index(truth_end)})")

    rng = np.random.default_rng(12345)
    rows, nowcast_rows, skipped = [], [], []
    for i, T in enumerate(origins, 1):
        try:
            run_ = run_origin(store, history, T, target=target, draws=draws, seed=i)
        except CoverageGap as gap:
            skipped.append({"origin": str(T.date()), "uncovered_months": len(gap.gaps)})
            progress(f"[{i}/{len(origins)}] origin {T.date()} skipped: {gap}")
            continue
        L, C = run_.L, run_.countries
        Y_final = final_view(store, C, run_.first, L, target, truth_name)
        final_fcs = {h: forecast_all(Y_final, h) for h in HORIZONS}
        st = run_.status.set_index("country_id")
        vint_L = run_.Y[:, -1]
        fin_L = Y_final[:, -1]
        for h in HORIZONS:
            tm = L + h
            if tm > truth_end:
                continue
            ys = np.array([int(y_truth.get((int(c), tm), 0)) for c in C])
            for regime, fcs in (("vintage", run_.forecasts[h]), ("final", final_fcs[h])):
                for model, fl in fcs.items():
                    for j, c in enumerate(C):
                        sc = fl[j].score(ys[j], rng)
                        rows.append({
                            "origin": T, "L": L, "country_id": int(c), "h": h, "regime": regime,
                            "model": model, "y": ys[j], **sc,
                            "C1": st.at[int(c), "C1"], "status": st.at[int(c), "status"],
                            "active": bool(run_.Y[j, -12:].sum() > 0),
                            "revision_L": float(fin_L[j] - vint_L[j]),
                        })
        # E2: nowcast of the newest months vs treating the raw count as final
        om = run_.obs_model
        for age in (1, 2, 3):
            col = run_.Y.shape[1] - age
            m = L - age + 1
            if m > truth_end:
                continue
            raw_alpha = om.extras["raw_alpha"].get(age, 0.5)
            for j, c in enumerate(C):
                if run_.is_final[j, col]:
                    continue
                obs = int(run_.Y[j, col])
                y = int(y_truth.get((int(c), m), 0))
                if obs == 0 and y == 0 and run_.Y[j, -12:].sum() == 0:
                    continue  # quiet country, nothing to learn
                for kind, fc in (("nowcast", om.nowcast(int(c), age, obs)),
                                 ("raw", CountForecast.point(obs, raw_alpha))):
                    sc = fc.score(y, rng)
                    nowcast_rows.append({"origin": T, "country_id": int(c), "age": age, "kind": kind,
                                         "obs": obs, "y": y, "C": om.C(int(c), age), **sc})
        progress(f"[{i}/{len(origins)}] origin {T.date()} (data through {month_from_index(L)}), "
                 f"{run_.obs_model.n_pairs} observation pairs")

    scores = pd.DataFrame(rows)
    nowcasts = pd.DataFrame(nowcast_rows)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    out = config.RESULTS / f"backtest-{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    scores.to_parquet(out / "scores.parquet", index=False)
    nowcasts.to_parquet(out / "nowcasts.parquet", index=False)

    summary = summarise(scores)
    summary["nowcast"] = summarise_nowcast(nowcasts)
    summary["persistence"] = completeness_persistence(history, store, truth_name, target)
    per_model = scores[(scores["regime"] == "vintage") & (scores["model"] == "nbar")]
    summary["meta"] = {
        "target": target, "draws": draws,
        "origins_in_range": len(origins), "origins_scored": int(per_model["origin"].nunique()),
        "origins_skipped": skipped,
        "origin_horizons_scored": int(per_model.groupby(["origin", "h"]).ngroups),
        "horizons_per_origin": per_model.groupby("origin")["h"].nunique().value_counts().sort_index().to_dict(),
        "countries": int(per_model["country_id"].nunique()),
        "forecasts_per_model_and_view": int(len(per_model)),
        "origins": sorted(str(o.date()) for o in per_model["origin"].unique()),
        "truth": truth_name, "truth_sha256": manifest[truth_name]["sha256"],
        "truth_through": str(month_from_index(truth_end)),
        "late_dated_releases": sorted(r["name"] for r in manifest.values()
                                      if r["date_source"] != "last-modified"),
        "bootstrap": {"type": "moving block over consecutive origins", "block": BLOCK,
                      "sensitivity_blocks": list(SENSITIVITY_BLOCKS), "reps": REPS},
        "code": code_version(),
        "created": dt.datetime.now().isoformat(timespec="seconds"),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    (out / "report.md").write_text(report(summary), encoding="utf-8")
    (config.RESULTS / "latest_backtest.txt").write_text(out.name, encoding="utf-8")
    progress(f"wrote {out}")
    return out


# ---------------------------------------------------------------------- inference
def block_bootstrap(per_origin: pd.DataFrame, block: int, reps: int = REPS, seed: int = 0) -> np.ndarray:
    """Moving-block bootstrap of a ratio mean over time-ordered origins.

    ``per_origin`` has columns ``sum`` and ``count`` and is indexed by origin. Blocks of
    ``block`` consecutive origins are drawn (circularly) until the series length is
    reached, so dependence within a block is preserved.
    """
    po = per_origin.sort_index()
    sums, cnts = po["sum"].to_numpy(), po["count"].to_numpy()
    n = len(po)
    b = max(1, min(block, n))
    nblocks = int(np.ceil(n / b))
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(reps, nblocks))
    idx = (starts[:, :, None] + np.arange(b)[None, None, :]).reshape(reps, -1)[:, :n] % n
    return sums[idx].sum(1) / cnts[idx].sum(1)


def _interval(d: pd.DataFrame, value: str, block: int) -> list[float]:
    per = d.groupby("origin")[value].agg(["sum", "count"])
    boots = block_bootstrap(per, block)
    return [float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))]


def diff_stats(d: pd.DataFrame, value: str = "d") -> dict:
    """Mean paired difference with block-bootstrap intervals (primary and sensitivity)."""
    if d.empty:
        return {"n": 0}
    return {
        "n": int(len(d)), "origins": int(d["origin"].nunique()),
        "mean_diff": float(d[value].mean()),
        "ci95": _interval(d, value, BLOCK),
        "ci95_sensitivity": {str(b): _interval(d, value, b) for b in SENSITIVITY_BLOCKS},
        "share_a_better": float((d[value] < 0).mean()),
    }


def paired_diff(scores: pd.DataFrame, a: str, b: str, regime: str = "vintage",
                metric: str = "crps", mask=None) -> dict:
    s = scores[scores["regime"] == regime]
    if mask is not None:
        s = s[mask(s)]
    key = ["origin", "country_id", "h"]
    pa = s[s["model"] == a].set_index(key)[metric]
    pb = s[s["model"] == b].set_index(key)[metric]
    d = (pa - pb).dropna().rename("d").reset_index()
    return diff_stats(d)


# ---------------------------------------------------------------------- summaries
def _agg(df: pd.DataFrame) -> dict:
    return {
        "n": int(len(df)), "crps": float(df["crps"].mean()), "logs": float(df["logs"].mean()),
        "brier": float(df["brier"].mean()), "cov80": float(df["in80"].mean()),
    }


def summarise_nowcast(nc: pd.DataFrame) -> dict:
    """Nowcast vs raw count, per vintage age, with block-bootstrap intervals."""
    out = {}
    if nc.empty:
        return out
    for age, g in nc.groupby("age"):
        w = g.pivot_table(index=["origin", "country_id"], columns="kind", values=["crps", "logs", "C"])
        d = pd.DataFrame({
            "d": w[("crps", "nowcast")] - w[("crps", "raw")],
            "low": w[("C", "raw")] < 0.8,
        }).reset_index()
        out[int(age)] = {
            "crps_raw": float(w[("crps", "raw")].mean()), "crps_nowcast": float(w[("crps", "nowcast")].mean()),
            "logs_raw": float(w[("logs", "raw")].mean()), "logs_nowcast": float(w[("logs", "nowcast")].mean()),
            "all": diff_stats(d),
            "low_completeness": diff_stats(d[d["low"]]),
            "other": diff_stats(d[~d["low"]]),
        }
    return out


def completeness_persistence(history: pd.DataFrame, store: VintageStore, truth_name: str,
                             target: str, low: float = 0.8, min_final: int = 5) -> dict:
    """Is low first-release completeness persistent, and does it recover?

    Uses each country-month's count at age 1 against the pinned final count, for
    country-months with at least ``min_final`` final events. Returns transition
    probabilities between consecutive months and the distribution of low-episode lengths.
    """
    truth, rel = store.truth(truth_name)
    a1 = history[(history["age"] == 1) & (~history["is_final"]) & (history["m"] <= rel.cover_end)]
    a1 = a1.drop_duplicates(["country_id", "m"], keep="first")
    a1 = a1.join(truth[target].rename("final"), on=["country_id", "m"])
    a1 = a1[a1["final"].fillna(0) >= min_final].copy()
    a1["r"] = a1[target] / a1["final"]
    a1["low"] = a1["r"] < low
    a1 = a1.sort_values(["country_id", "m"])
    nxt = a1.groupby("country_id")[["m", "low"]].shift(-1)
    pairs = a1[nxt["m"].to_numpy() == (a1["m"] + 1).to_numpy()].assign(next_low=nxt["low"])
    pairs = pairs.dropna(subset=["next_low"])
    pairs["next_low"] = pairs["next_low"].astype(bool)

    def p(cond):
        sel = pairs[cond]
        return {"p": float(sel["next_low"].mean()) if len(sel) else None, "n": int(len(sel))}

    # episode lengths: runs of consecutive low months
    lengths = []
    for _, g in a1.groupby("country_id"):
        run = 0
        prev_m = None
        for m, is_low in zip(g["m"], g["low"]):
            if prev_m is not None and m != prev_m + 1 and run:
                lengths.append(run)
                run = 0
            if is_low:
                run += 1
            elif run:
                lengths.append(run)
                run = 0
            prev_m = m
        if run:
            lengths.append(run)
    lengths = np.array(lengths) if lengths else np.array([0])
    return {
        "definition": f"age-1 count / final count < {low}, country-months with final >= {min_final}",
        "n_country_months": int(len(a1)), "base_rate_low": float(a1["low"].mean()) if len(a1) else None,
        "p_low_given_low": p(pairs["low"]), "p_low_given_ok": p(~pairs["low"]),
        "episodes": int(len(lengths)), "episode_mean_months": float(lengths.mean()),
        "episode_share_1_month": float((lengths == 1).mean()),
        "episode_share_3plus": float((lengths >= 3).mean()),
        "countries": int(a1["country_id"].nunique()),
    }


def summarise(scores: pd.DataFrame) -> dict:
    active = scores[scores["active"]]
    out: dict = {}

    # Paper 1: final vs vintage view for the baselines
    p1 = {}
    for scope, df in (("all", scores), ("active", active)):
        tab = {}
        for regime in ("final", "vintage"):
            tab[regime] = {m: _agg(df[(df["regime"] == regime) & (df["model"] == m)]) for m in BASELINES}
            tab[regime]["_rank_crps"] = sorted(BASELINES, key=lambda m: tab[regime][m]["crps"])
        p1[scope] = tab
    key = ["origin", "country_id", "h"]
    view_gap = {}
    for m in BASELINES:
        a = active[active["model"] == m]
        f = a[a["regime"] == "final"].set_index(key)["crps"]
        v = a[a["regime"] == "vintage"].set_index(key)["crps"]
        d = (v - f).dropna().rename("d").reset_index()
        view_gap[m] = {**diff_stats(d), "share_worse_on_vintage": float((d["d"] > 0).mean())}
    p1["vintage_minus_final_crps_active"] = view_gap
    out["paper1_measurement"] = p1

    # Paper 2: visibility correction. Primary: active countries, CRPS.
    p2 = {"primary_active_crps": paired_diff(scores, "nbar+vis", "nbar", mask=lambda s: s["active"]),
          "active_logs": paired_diff(scores, "nbar+vis", "nbar", metric="logs", mask=lambda s: s["active"]),
          "all_crps": paired_diff(scores, "nbar+vis", "nbar"),
          "all_logs": paired_diff(scores, "nbar+vis", "nbar", metric="logs")}
    buckets = {"C1<0.8": lambda s: s["C1"] < 0.8, "0.8<=C1<1.0": lambda s: (s["C1"] >= 0.8) & (s["C1"] < 1.0),
               "C1>=1.0": lambda s: s["C1"] >= 1.0}
    p2["by_completeness"] = {k: paired_diff(scores, "nbar+vis", "nbar", mask=lambda s, f=f: f(s) & s["active"])
                             for k, f in buckets.items()}
    p2["by_horizon"] = {int(h): paired_diff(scores, "nbar+vis", "nbar", mask=lambda s, h=h: (s["h"] == h) & s["active"])
                        for h in HORIZONS}
    vint = scores[scores["regime"] == "vintage"]
    p2["models_vintage_active"] = {m: _agg(vint[(vint["model"] == m) & vint["active"]]) for m in (*BASELINES, "nbar+vis")}
    out["paper2_visibility"] = p2

    # Visibility status. CRPS is scale-dependent, so also report scale-free measures:
    # CRPS normalised by the baseline's expected count, and the tail-miss rate (PIT
    # outside [0.05, 0.95]), which a calibrated forecast hits 10% of the time.
    base_mean = vint[vint["model"] == "nbar"].set_index(key)["mean"].rename("base_mean")
    v = vint[(vint["model"] == "nbar+vis") & vint["active"]].join(base_mean, on=key)
    v["ncrps"] = v["crps"] / (1.0 + v["base_mean"])
    v["tail_miss"] = (v["pit"] < 0.05) | (v["pit"] > 0.95)
    ab = {}
    for status in ("OK", "WARN", "ABSTAIN"):
        d = v[v["status"] == status]
        if len(d):
            ab[status] = {**_agg(d), "pit_mean": float(d["pit"].mean()), "ncrps": float(d["ncrps"].mean()),
                          "tail_miss": float(d["tail_miss"].mean()), "base_mean": float(d["base_mean"].mean())}
    out["visibility_status"] = ab

    pit = {}
    for m in (*BASELINES, "nbar+vis"):
        d = vint[(vint["model"] == m) & vint["active"]]["pit"]
        hist, _ = np.histogram(d, bins=10, range=(0, 1))
        pit[m] = (hist / max(len(d), 1)).round(4).tolist()
    out["pit_histograms"] = pit
    return out


# ---------------------------------------------------------------------- report
def _verdict(lo: float, hi: float) -> str:
    return "AEGIS better" if hi < 0 else ("baseline better" if lo > 0 else "no clear difference")


def _diff_row(label: str, d: dict) -> str:
    if not d.get("n"):
        return f"| {label} | – | – | – | – | 0 |"
    lo, hi = d["ci95"]
    sens = " ".join(f"[{a:+.3f}, {b:+.3f}]" for a, b in d["ci95_sensitivity"].values())
    return f"| {label} | {d['mean_diff']:+.4f} | [{lo:+.4f}, {hi:+.4f}] | {sens} | {_verdict(lo, hi)} | {d['n']} / {d['origins']} |"


DIFF_HEAD = ["| Slice | Mean diff | 95% CI (6-month blocks) | Sensitivity (3, 9) | Verdict | n forecasts / origins |",
             "|---|---|---|---|---|---|"]


def report(s: dict) -> str:
    m = s["meta"]
    p1, p2 = s["paper1_measurement"], s["paper2_visibility"]
    hp = ", ".join(f"{n} origins × {h} horizon{'s' if int(h) > 1 else ''}" for h, n in
                   sorted(m["horizons_per_origin"].items(), key=lambda kv: -int(kv[0])))
    lines = [
        f"# AEGIS backtest ({m['created']})", "",
        "## Setup", "",
        f"- Target: `{m['target']}` per country-month; horizons 1–3 months after the last month with data.",
        f"- Truth: `{m['truth']}` (pinned; SHA-256 `{m['truth_sha256'][:16]}…`; final data through {m['truth_through']}).",
        f"- Code: commit `{(m['code']['commit'] or 'unknown')[:10]}`{' (uncommitted changes in src/)' if m['code']['dirty'] else ''}.",
        f"- Origins: {m['origins_in_range']} release dates in range; {m['origins_scored']} scored "
        f"({m['origins'][0]} → {m['origins'][-1]}); {len(m['origins_skipped'])} skipped for coverage gaps.",
        f"- Horizons scored: {hp} (truth ends {m['truth_through']}) = {m['origin_horizons_scored']} origin-horizons.",
        f"- Forecasts: {m['origin_horizons_scored']} origin-horizons × {m['countries']} countries = "
        f"{m['forecasts_per_model_and_view']} per model and view.",
        f"- Releases dated late (never backdated; they cost vintages): {', '.join(m['late_dated_releases']) or 'none'}.",
        "- Vintages are day-level: a release counts as known from the start of its availability date.",
        "- Intervals: moving-block bootstrap over consecutive origins (6-month blocks; 3 and 9 as sensitivity). "
        "Effective sample size is closer to the number of origins than to the number of forecasts.",
        "- Lower is better for CRPS, log score and Brier. Log score is exact (no probability floor).", "",
        "## Paper 1: does the data view change how good models look?", "",
        "Active countries (any event in the 12 months before the origin).", "",
        "| Model | CRPS (final view) | CRPS (vintage view) | Log (final) | Log (vintage) | Cov80 (final) | Cov80 (vintage) |",
        "|---|---|---|---|---|---|---|",
    ]
    a = p1["active"]
    for mdl in BASELINES:
        f, v = a["final"][mdl], a["vintage"][mdl]
        lines.append(f"| {mdl} | {f['crps']:.3f} | {v['crps']:.3f} | {f['logs']:.3f} | {v['logs']:.3f} | {f['cov80']:.1%} | {v['cov80']:.1%} |")
    lines += ["", f"Ranking by CRPS, final view: {' < '.join(a['final']['_rank_crps'])}",
              f"Ranking by CRPS, vintage view: {' < '.join(a['vintage']['_rank_crps'])}", "",
              "CRPS(vintage view) − CRPS(final view), active countries:", "", *DIFF_HEAD]
    for mdl, g in p1["vintage_minus_final_crps_active"].items():
        lines.append(_diff_row(mdl, g))

    nc = s.get("nowcast", {})
    if nc:
        lines += ["", "## E2: nowcasting the newest months", "",
                  "Nowcast of the eventual (final) count vs treating the count seen at that age as final. "
                  "Countries with no activity are excluded. Diff = CRPS(nowcast) − CRPS(raw).", "",
                  "| Age | CRPS raw | CRPS nowcast | Log raw | Log nowcast |", "|---|---|---|---|---|"]
        for age, g in nc.items():
            lines.append(f"| {age} | {g['crps_raw']:.3f} | {g['crps_nowcast']:.3f} | {g['logs_raw']:.3f} | {g['logs_nowcast']:.3f} |")
        lines += ["", *DIFF_HEAD]
        for age, g in nc.items():
            lines.append(_diff_row(f"age {age}, all", g["all"]))
            lines.append(_diff_row(f"age {age}, C < 0.8", g["low_completeness"]))
            lines.append(_diff_row(f"age {age}, C ≥ 0.8", g["other"]))

    lines += ["", "## Paper 2: does correcting for reporting completeness help?", "",
              "Diff = score(`nbar+vis`) − score(`nbar`), vintage view. Negative favours AEGIS.", "", *DIFF_HEAD,
              _diff_row("**Active, CRPS (primary)**", p2["primary_active_crps"]),
              _diff_row("Active, log score", p2["active_logs"]),
              _diff_row("All countries, CRPS", p2["all_crps"]),
              _diff_row("All countries, log score", p2["all_logs"])]
    for k, d in p2["by_completeness"].items():
        lines.append(_diff_row(f"Active, {k}", d))
    for h, d in p2["by_horizon"].items():
        lines.append(_diff_row(f"Active, h={h}", d))
    lines += ["", "| Model (vintage, active) | CRPS | Log | Brier | Cov80 |", "|---|---|---|---|---|"]
    for mdl, g in p2["models_vintage_active"].items():
        lines.append(f"| {mdl} | {g['crps']:.3f} | {g['logs']:.3f} | {g['brier']:.4f} | {g['cov80']:.1%} |")

    lines += ["", "## Visibility status (nbar+vis, active countries)", "",
              "CRPS depends on scale, and flagged countries are often high-volume. Normalised CRPS divides "
              "by 1 + the baseline's expected count. Tail misses are outcomes outside the forecast's 5–95% "
              "range: 10% for a calibrated forecast, at any scale.", "",
              "| Status | n | Mean expected count | CRPS | Normalised CRPS | Tail-miss rate | Cov80 | Mean PIT |",
              "|---|---|---|---|---|---|---|---|"]
    for k, g in s["visibility_status"].items():
        lines.append(f"| {k} | {g['n']} | {g['base_mean']:.1f} | {g['crps']:.3f} | {g['ncrps']:.3f} | "
                     f"{g['tail_miss']:.1%} | {g['cov80']:.1%} | {g['pit_mean']:.3f} |")

    ps = s.get("persistence")
    if ps and ps.get("n_country_months"):
        ll, lo = ps["p_low_given_low"], ps["p_low_given_ok"]
        lines += ["", "## Is low completeness episodic?", "",
                  f"Definition: {ps['definition']}. {ps['n_country_months']} country-months across {ps['countries']} countries.", "",
                  "| Quantity | Value |", "|---|---|",
                  f"| Base rate of low completeness | {ps['base_rate_low']:.1%} |",
                  f"| P(low next month \\| low this month) | {ll['p']:.1%} (n = {ll['n']}) |",
                  f"| P(low next month \\| not low this month) | {lo['p']:.1%} (n = {lo['n']}) |",
                  f"| Low episodes | {ps['episodes']} |",
                  f"| Mean episode length | {ps['episode_mean_months']:.2f} months |",
                  f"| Episodes lasting 1 month | {ps['episode_share_1_month']:.0%} |",
                  f"| Episodes lasting 3+ months | {ps['episode_share_3plus']:.0%} |"]

    lines += ["", "## PIT histograms (10 bins, active, vintage view)", ""]
    for mdl, hist in s["pit_histograms"].items():
        lines.append(f"- `{mdl}`: " + " ".join(f"{x:.2f}" for x in hist))
    return "\n".join(lines) + "\n"
