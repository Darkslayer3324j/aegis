"""Exploratory comparisons outside the pre-registered protocol (PROTOCOL.md §8).

Nothing here can decide a pass or fail. It exists to understand *where* and *why* the
visibility correction wins or loses, and whether stronger statistical baselines change
the picture.

``baselines``: StatsForecast models on exactly the same vintage panels, origins,
countries and targets as the backtest. The set includes the intermittent-demand models
(Croston, IMAPA, TSB), which are designed for sparse counts like conflict events. Point
forecasts become negative-binomial distributions, with dispersion fitted to each model's
own in-sample errors, so they can be scored with the same CRPS and log score.

Requires the optional extra: ``pip install aegis-forecast[baselines]``.
"""

from __future__ import annotations

import datetime as dt
import json
import warnings
from typing import Callable

import numpy as np
import pandas as pd

from . import config
from .backtest import block_bootstrap
from .pipeline import HORIZONS, WINDOW
from .scoring import CountForecast, fit_alpha
from .vintage import VintageStore, month_from_index


def _models():
    from statsforecast.models import (IMAPA, TSB, AutoETS, AutoTheta, CrostonOptimized,
                                      WindowAverage)
    return [WindowAverage(window_size=6), CrostonOptimized(), IMAPA(), TSB(alpha_d=0.2, alpha_p=0.2),
            AutoETS(season_length=1), AutoTheta(season_length=1)]


def baselines(truth: str = "final-26.1", start: str = "2022-06-01", scope: str = "world",
              reference: str | None = None, progress: Callable[[str], None] = print) -> dict:
    """Score StatsForecast baselines against the pinned truth; compare with ``nbar``.

    ``reference`` is a backtest directory whose ``nbar`` scores are joined for a paired
    comparison (default: the latest backtest for the scope).
    """
    from statsforecast import StatsForecast

    store = VintageStore.load(scope)
    truth_df, rel = store.truth(truth)
    y_truth = truth_df["events"]
    origins = [o for o in store.origins(start) if store.last_data_month(o) + 1 <= rel.cover_end]
    rows = []
    rng = np.random.default_rng(7)
    for i, T in enumerate(origins, 1):
        L = store.last_data_month(T)
        first = L - WINDOW + 1
        C = store.countries_at(T)
        panel = store.panel(T, first, L, countries=C)
        long = panel.assign(ds=panel["m"].map(lambda m: month_from_index(m).to_timestamp()),
                            unique_id=panel["country_id"].astype(str), y=panel["events"].astype(float))
        sf = StatsForecast(models=_models(), freq="MS", n_jobs=1)
        df = long[["unique_id", "ds", "y"]]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fc = sf.forecast(df=df, h=max(HORIZONS))
            # one-step-ahead errors over the last 6 months before the origin (no future data)
            cv = sf.cross_validation(df=df, h=1, n_windows=6, step_size=1)
        fc = fc.reset_index() if "unique_id" not in fc.columns else fc
        cv = cv.reset_index() if "unique_id" not in cv.columns else cv
        model_cols = [c for c in fc.columns if c not in ("unique_id", "ds")]
        # dispersion per model, fitted to its own out-of-sample errors (pooled over countries)
        alphas = {}
        for mcol in model_cols:
            f = cv[["y", mcol]].dropna()
            alphas[mcol] = fit_alpha(f["y"].round().to_numpy(), np.maximum(f[mcol].to_numpy(), 1e-3)) if len(f) else 0.5
        fc["h"] = fc.groupby("unique_id").cumcount() + 1
        for r in fc.itertuples(index=False):
            c, h = int(r.unique_id), int(r.h)
            tm = L + h
            if tm > rel.cover_end:
                continue
            y = int(y_truth.get((c, tm), 0))
            active = bool(panel[(panel["country_id"] == c) & (panel["m"] > L - 12)]["events"].sum() > 0)
            for mcol in model_cols:
                mu = max(float(getattr(r, mcol)), 1e-3)
                sc = CountForecast.point(mu, alphas[mcol]).score(y, rng)
                rows.append({"origin": T, "country_id": c, "h": h, "model": f"sf:{mcol}", "y": y,
                             "active": active, **sc})
        progress(f"[{i}/{len(origins)}] {T.date()}")

    sf_scores = pd.DataFrame(rows)
    results = config.scope_results(scope)
    ref_dir = results / (reference or (results / "latest_backtest.txt").read_text(encoding="utf-8").strip())
    ref = pd.read_parquet(ref_dir / "scores.parquet")
    ref = ref[(ref["regime"] == "vintage") & ref["model"].isin(["nbar", "nbar+V1", "nbar+vis"])]
    key = ["origin", "country_id", "h"]
    both = pd.concat([sf_scores, ref[key + ["model", "y", "active", "crps", "logs", "in80"]]], ignore_index=True)
    base = both[both["model"] == "nbar"].set_index(key)["crps"]

    table = {}
    for mdl, g in both[both["active"]].groupby("model"):
        d = (g.set_index(key)["crps"] - base).dropna().rename("d").reset_index()
        per = d.groupby("origin")["d"].agg(["sum", "count"])
        boots = block_bootstrap(per, 6)
        table[mdl] = {"crps": float(g["crps"].mean()), "logs": float(g["logs"].mean()),
                      "cov80": float(g["in80"].mean()), "n": int(len(g)),
                      "diff_vs_nbar": float(d["d"].mean()),
                      "ci95": [float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))]}
    out = {"scope": scope, "truth": truth, "reference_backtest": ref_dir.name,
           "origins": len(origins), "created": dt.datetime.now().isoformat(timespec="seconds"),
           "note": "Exploratory (PROTOCOL.md section 8): cannot decide a pass or fail.",
           "models": dict(sorted(table.items(), key=lambda kv: kv[1]["crps"]))}
    dest = results / f"explore-baselines-{dt.datetime.now():%Y%m%d-%H%M}"
    dest.mkdir(parents=True, exist_ok=True)
    sf_scores.to_parquet(dest / "scores.parquet", index=False)
    (dest / "summary.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    progress(f"wrote {dest}")
    return out
