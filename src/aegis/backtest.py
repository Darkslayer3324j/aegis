"""Vintage-aware walk-forward backtest.

Two questions, answered at every historical origin and scored against the newest final
release:

* **Paper 1, the measurement problem.** Does scoring models on the data that existed at
  the time (vintage view) instead of the revised data (final view) change how good they
  look, or which one looks best?
* **Paper 2, the visibility problem.** Does correcting the vintage view for incomplete
  reporting (``nbar+vis``) beat the same model without the correction (``nbar``)?

Every model, both views and the visibility status share the same origins, countries and
targets, so the comparisons are paired.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from . import config
from . import observation as ob
from .models import forecast_all
from .pipeline import HORIZONS, final_view, run_origin
from .scoring import CountForecast
from .vintage import VintageStore, month_from_index

BASELINES = ("naive", "ma6", "nbar")
HISTORY_VERSION = 2  # bump when build_history changes, to invalidate the cache


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


def run(start: str = "2022-06-01", end: str | None = None, target: str = "events",
        draws: int = 40, progress: Callable[[str], None] = print) -> Path:
    store = VintageStore.load()
    history = load_history(store)
    truth, truth_rel = store.truth()
    truth_end = truth_rel.cover_end
    y_truth = truth[target]
    origins = [o for o in store.origins(start, end) if store.last_data_month(o) + 1 <= truth_end]
    progress(f"{len(origins)} origins, truth = {truth_rel.name} (through {month_from_index(truth_end)})")

    rng = np.random.default_rng(12345)
    rows, nowcast_rows = [], []
    for i, T in enumerate(origins, 1):
        run_ = run_origin(store, history, T, target=target, draws=draws, seed=i)
        L, C = run_.L, run_.countries
        Y_final = final_view(store, C, run_.first, L, target)
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
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    out = config.RESULTS / f"backtest-{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    scores.to_parquet(out / "scores.parquet", index=False)
    nowcasts = pd.DataFrame(nowcast_rows)
    nowcasts.to_parquet(out / "nowcasts.parquet", index=False)
    summary = summarise(scores)
    summary["nowcast"] = summarise_nowcast(nowcasts)
    summary["meta"] = {
        "target": target, "draws": draws, "origins": [str(o.date()) for o in origins],
        "truth": truth_rel.name, "truth_through": str(month_from_index(truth_end)),
        "created": dt.datetime.now().isoformat(timespec="seconds"),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    (out / "report.md").write_text(report(summary), encoding="utf-8")
    (config.RESULTS / "latest_backtest.txt").write_text(out.name, encoding="utf-8")
    progress(f"wrote {out}")
    return out


# ---------------------------------------------------------------------- summaries
def _agg(df: pd.DataFrame) -> dict:
    return {
        "n": int(len(df)), "crps": float(df["crps"].mean()), "logs": float(df["logs"].mean()),
        "brier": float(df["brier"].mean()), "cov80": float(df["in80"].mean()),
    }


def paired_diff(scores: pd.DataFrame, a: str, b: str, regime: str = "vintage",
                metric: str = "crps", mask=None, reps: int = 2000, seed: int = 0) -> dict:
    """Mean of metric(a) - metric(b) with a bootstrap CI that resamples whole origins."""
    s = scores[scores["regime"] == regime]
    if mask is not None:
        s = s[mask(s)]
    key = ["origin", "country_id", "h"]
    pa = s[s["model"] == a].set_index(key)[metric]
    pb = s[s["model"] == b].set_index(key)[metric]
    d = (pa - pb).dropna().reset_index()
    if d.empty:
        return {"n": 0}
    per_origin = d.groupby("origin")[metric].agg(["sum", "count"])
    rng = np.random.default_rng(seed)
    k = len(per_origin)
    idx = rng.integers(0, k, size=(reps, k))
    sums = per_origin["sum"].to_numpy()[idx].sum(1)
    cnts = per_origin["count"].to_numpy()[idx].sum(1)
    boots = sums / cnts
    return {"n": int(len(d)), "mean_diff": float(d[metric].mean()),
            "ci95": [float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))],
            "share_a_better": float((d[metric] < 0).mean())}


def summarise_nowcast(nc: pd.DataFrame, reps: int = 2000, seed: int = 0) -> dict:
    """Nowcast vs raw count, per vintage age, with an origin-block bootstrap."""
    out = {}
    if nc.empty:
        return out
    rng = np.random.default_rng(seed)
    for age, g in nc.groupby("age"):
        w = g.pivot_table(index=["origin", "country_id"], columns="kind", values=["crps", "logs"])
        d = (w[("crps", "nowcast")] - w[("crps", "raw")]).rename("d").reset_index()
        per = d.groupby("origin")["d"].agg(["sum", "count"])
        idx = rng.integers(0, len(per), size=(reps, len(per)))
        boots = per["sum"].to_numpy()[idx].sum(1) / per["count"].to_numpy()[idx].sum(1)
        low = g[g["kind"] == "raw"].set_index(["origin", "country_id"])["C"] < 0.8
        dl = d.set_index(["origin", "country_id"])["d"][low.reindex(d.set_index(["origin", "country_id"]).index).fillna(False).to_numpy()]
        out[int(age)] = {
            "n": int(len(d)),
            "crps_raw": float(w[("crps", "raw")].mean()), "crps_nowcast": float(w[("crps", "nowcast")].mean()),
            "logs_raw": float(w[("logs", "raw")].mean()), "logs_nowcast": float(w[("logs", "nowcast")].mean()),
            "mean_diff": float(d["d"].mean()),
            "ci95": [float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))],
            "low_completeness_n": int(len(dl)),
            "low_completeness_diff": float(dl.mean()) if len(dl) else None,
        }
    return out


def summarise(scores: pd.DataFrame) -> dict:
    active = scores[scores["active"]]
    out: dict = {}

    # Paper 1: final vs vintage view for the baselines
    p1 = {}
    for scope, df in (("all", scores), ("active", active)):
        tab = {}
        for regime in ("final", "vintage"):
            tab[regime] = {m: _agg(df[(df["regime"] == regime) & (df["model"] == m)]) for m in BASELINES}
            order = sorted(BASELINES, key=lambda m: tab[regime][m]["crps"])
            tab[regime]["_rank_crps"] = order
        p1[scope] = tab
    view_gap = {}
    for m in BASELINES:
        f = scores[(scores["regime"] == "final") & (scores["model"] == m)].set_index(["origin", "country_id", "h"])["crps"]
        v = scores[(scores["regime"] == "vintage") & (scores["model"] == m)].set_index(["origin", "country_id", "h"])["crps"]
        d = (v - f).dropna()
        view_gap[m] = {"mean_vintage_minus_final": float(d.mean()), "share_worse_on_vintage": float((d > 0).mean())}
    p1["vintage_minus_final_crps"] = view_gap
    out["paper1_measurement"] = p1

    # Paper 2: visibility correction
    p2 = {"overall_crps": paired_diff(scores, "nbar+vis", "nbar"),
          "overall_logs": paired_diff(scores, "nbar+vis", "nbar", metric="logs"),
          "active_crps": paired_diff(scores, "nbar+vis", "nbar", mask=lambda s: s["active"])}
    buckets = {"C1<0.8": lambda s: s["C1"] < 0.8, "0.8<=C1<1.0": lambda s: (s["C1"] >= 0.8) & (s["C1"] < 1.0),
               "C1>=1.0": lambda s: s["C1"] >= 1.0}
    p2["by_completeness"] = {k: paired_diff(scores, "nbar+vis", "nbar", mask=lambda s, f=f: f(s) & s["active"])
                             for k, f in buckets.items()}
    p2["by_horizon"] = {int(h): paired_diff(scores, "nbar+vis", "nbar", mask=lambda s, h=h: (s["h"] == h) & s["active"])
                        for h in HORIZONS}
    big_rev = lambda s: (s["revision_L"].abs() >= 5) & s["active"]
    p2["large_revision_months"] = paired_diff(scores, "nbar+vis", "nbar", mask=big_rev)
    vint = scores[scores["regime"] == "vintage"]
    p2["models_vintage_active"] = {m: _agg(vint[(vint["model"] == m) & vint["active"]]) for m in (*BASELINES, "nbar+vis")}
    out["paper2_visibility"] = p2

    # Visibility-triggered abstention
    ab = {}
    for status in ("OK", "WARN", "ABSTAIN"):
        d = vint[(vint["model"] == "nbar+vis") & (vint["status"] == status) & vint["active"]]
        if len(d):
            ab[status] = {**_agg(d), "pit_mean": float(d["pit"].mean())}
    out["visibility_status"] = ab

    # Calibration: PIT histograms (active countries, vintage view)
    pit = {}
    for m in (*BASELINES, "nbar+vis"):
        d = vint[(vint["model"] == m) & vint["active"]]["pit"]
        hist, _ = np.histogram(d, bins=10, range=(0, 1))
        pit[m] = (hist / max(len(d), 1)).round(4).tolist()
    out["pit_histograms"] = pit
    return out


def report(s: dict) -> str:
    m = s["meta"]
    p1, p2 = s["paper1_measurement"], s["paper2_visibility"]
    lines = [
        f"# AEGIS backtest ({m['created']})", "",
        f"- Target: `{m['target']}` per country-month; horizons 1–3 months after the last month with data.",
        f"- Origins: {len(m['origins'])} ({m['origins'][0]} → {m['origins'][-1]}), one per UCDP Candidate monthly release.",
        f"- Scored against `{m['truth']}` (final data through {m['truth_through']}).",
        "- Lower is better for CRPS, log score and Brier. The 80% interval should cover 80%.", "",
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
              f"Ranking by CRPS, vintage view: {' < '.join(a['vintage']['_rank_crps'])}", ""]
    for mdl, g in p1["vintage_minus_final_crps"].items():
        lines.append(f"- `{mdl}`: vintage view raises mean CRPS by {g['mean_vintage_minus_final']:+.3f} "
                     f"(worse on {g['share_worse_on_vintage']:.0%} of forecasts).")

    def diff_line(label, d):
        if not d.get("n"):
            return f"| {label} | – | – | – | 0 |"
        lo, hi = d["ci95"]
        verdict = "AEGIS better" if hi < 0 else ("baseline better" if lo > 0 else "no clear difference")
        return f"| {label} | {d['mean_diff']:+.4f} | [{lo:+.4f}, {hi:+.4f}] | {verdict} | {d['n']} |"

    nc = s.get("nowcast", {})
    if nc:
        lines += ["", "## E2: nowcasting the newest months", "",
                  "Does the observation model's estimate of the eventual (final) count beat treating the "
                  "count seen at that age as final? Both are negative-binomial forecasts of the final value. "
                  "Countries with no activity are excluded.", "",
                  "| Age (1 = newest month) | n | CRPS raw | CRPS nowcast | Diff | 95% CI | Log raw | Log nowcast | Diff where C<0.8 (n) |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for age, g in nc.items():
            lo, hi = g["ci95"]
            low = "–" if g["low_completeness_diff"] is None else f"{g['low_completeness_diff']:+.2f} ({g['low_completeness_n']})"
            lines.append(f"| {age} | {g['n']} | {g['crps_raw']:.3f} | {g['crps_nowcast']:.3f} | {g['mean_diff']:+.3f} | "
                         f"[{lo:+.3f}, {hi:+.3f}] | {g['logs_raw']:.3f} | {g['logs_nowcast']:.3f} | {low} |")
    lines += ["", "## Paper 2: does correcting for reporting completeness help?", "",
              "Difference = score(`nbar+vis`) − score(`nbar`), vintage view. Negative favours AEGIS. "
              "The 95% CI comes from a bootstrap over whole origins.", "",
              "| Slice | Mean diff | 95% CI | Verdict | n |", "|---|---|---|---|---|",
              diff_line("All countries (CRPS)", p2["overall_crps"]),
              diff_line("All countries (log score)", p2["overall_logs"]),
              diff_line("Active countries (CRPS)", p2["active_crps"])]
    for k, d in p2["by_completeness"].items():
        lines.append(diff_line(f"Active, {k}", d))
    for h, d in p2["by_horizon"].items():
        lines.append(diff_line(f"Active, h={h}", d))
    lines.append(diff_line("Active, last month later revised by ≥5 events", p2["large_revision_months"]))
    lines += ["", "| Model (vintage, active) | CRPS | Log | Brier | Cov80 |", "|---|---|---|---|---|"]
    for mdl, g in p2["models_vintage_active"].items():
        lines.append(f"| {mdl} | {g['crps']:.3f} | {g['logs']:.3f} | {g['brier']:.4f} | {g['cov80']:.1%} |")
    lines += ["", "## Visibility status (nbar+vis, active countries)", "",
              "| Status | n | CRPS | Log | Cov80 | Mean PIT |", "|---|---|---|---|---|---|"]
    for k, g in s["visibility_status"].items():
        lines.append(f"| {k} | {g['n']} | {g['crps']:.3f} | {g['logs']:.3f} | {g['cov80']:.1%} | {g['pit_mean']:.3f} |")
    lines += ["", "A well-calibrated model has a mean PIT near 0.5 and a flat PIT histogram.", "",
              "## PIT histograms (10 bins, active, vintage view)", ""]
    for mdl, hist in s["pit_histograms"].items():
        lines.append(f"- `{mdl}`: " + " ".join(f"{x:.2f}" for x in hist))
    return "\n".join(lines) + "\n"
