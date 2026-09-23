"""Today's forecast cycle, saved for the interface and for `aegis explain`."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .backtest import load_history
from .pipeline import HORIZONS, run_origin
from .vintage import VintageStore, month_from_index

def live_dir(scope: str = "world"):
    return config.scope_results(scope) / "live"


def _interval(fc) -> tuple[int, int]:
    return fc.quantile(0.1), fc.quantile(0.9)


def compute(asof: dt.date | None = None, target: str = "events", draws: int = 60,
            progress=print, scope: str = "world") -> Path:
    LIVE_DIR = live_dir(scope)
    store = VintageStore.load(scope)
    history = load_history(store, scope=scope)
    T = pd.Timestamp(asof or dt.date.today())
    run = run_origin(store, history, T, target=target, draws=draws)
    L, C = run.L, run.countries
    names = store.countries
    st = run.status.set_index("country_id")
    om = run.obs_model

    rows, series = [], []
    for j, c in enumerate(C):
        c = int(c)
        obs = int(run.Y[j, -1])
        now = om.nowcast(c, 1, obs) if not run.is_final[j, -1] else None
        row = {
            "country_id": c, "country": names.at[c, "country"], "region": names.at[c, "region"],
            "obs_last": obs,
            "nowcast_last": now.mean if now else float(obs),
            "nowcast_lo": _interval(now)[0] if now else obs,
            "nowcast_hi": _interval(now)[1] if now else obs,
            **{k: st.at[c, k] for k in ("C1", "C2", "C3", "volatility", "activity12", "dark", "status")},
        }
        for h in HORIZONS:
            for model in ("nbar", "nbar+vis"):
                fc = run.forecasts[h][model][j]
                lo, hi = _interval(fc)
                key = "base" if model == "nbar" else "aegis"
                row.update({f"{key}_h{h}": fc.mean, f"{key}_h{h}_lo": lo, f"{key}_h{h}_hi": hi,
                            f"{key}_h{h}_ppos": fc.p_positive()})
        rows.append(row)
        for k in range(24):
            col = run.Y.shape[1] - 24 + k
            series.append({"country_id": c, "m": str(month_from_index(run.first + col)),
                           "observed": float(run.Y[j, col]), "nowcast": float(run.Y_vis[j, col]),
                           "is_final": bool(run.is_final[j, col])})

    table = pd.DataFrame(rows)
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    table.to_parquet(LIVE_DIR / "countries.parquet", index=False)
    pd.DataFrame(series).to_parquet(LIVE_DIR / "series.parquet", index=False)

    snap = store.snapshot(T)
    recent = snap[snap["m"] > L - 3][["country_id", "latitude", "longitude", "m", "best", "type_of_violence"]]
    recent.to_parquet(LIVE_DIR / "events.parquet", index=False)

    releases = store.available(T)
    latest_c = max((r for r in releases if r.kind != "final"), key=lambda r: r.available)
    meta = {
        "scope": scope, "origin": str(T.date()), "data_through": str(month_from_index(L)), "target": target,
        "final_release": om.final_name, "latest_candidate": latest_c.name,
        "latest_candidate_available": str(latest_c.available.date()),
        "observation_pairs": om.n_pairs,
        "global_completeness": {int(k): float(v) for k, v in om.global_completeness.items()},
        "created": dt.datetime.now().isoformat(timespec="seconds"),
    }
    (LIVE_DIR / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    progress(f"live forecast for {meta['origin']} (data through {meta['data_through']}) -> {LIVE_DIR}")
    return LIVE_DIR


@dataclass
class LiveState:
    meta: dict
    countries: pd.DataFrame
    series: pd.DataFrame
    events: pd.DataFrame
    backtest: dict | None
    backtest_by_country: pd.DataFrame | None


def load(scope: str = "world") -> LiveState:
    LIVE_DIR = live_dir(scope)
    if not (LIVE_DIR / "meta.json").exists():
        raise FileNotFoundError("No live forecast yet. Run `aegis forecast`.")
    meta = json.loads((LIVE_DIR / "meta.json").read_text(encoding="utf-8"))
    bt, by_c = None, None
    pointer = config.scope_results(scope) / "latest_backtest.txt"
    if pointer.exists():
        d = config.scope_results(scope) / pointer.read_text(encoding="utf-8").strip()
        if (d / "summary.json").exists():
            bt = json.loads((d / "summary.json").read_text(encoding="utf-8"))
            s = pd.read_parquet(d / "scores.parquet", columns=["regime", "model", "country_id", "crps", "in80"])
            s = s[(s["regime"] == "vintage") & s["model"].isin(["nbar", "nbar+vis"])]
            by_c = s.pivot_table(index="country_id", columns="model", values="crps", aggfunc="mean")
            vis = s[s["model"] == "nbar+vis"].groupby("country_id")["in80"]
            by_c["miss"] = 1.0 - vis.mean()
            by_c["n"] = vis.size()
    return LiveState(
        meta=meta,
        countries=pd.read_parquet(LIVE_DIR / "countries.parquet"),
        series=pd.read_parquet(LIVE_DIR / "series.parquet"),
        events=pd.read_parquet(LIVE_DIR / "events.parquet"),
        backtest=bt, backtest_by_country=by_c,
    )


def revision_trail(store: VintageStore, country_id: int, months: int = 6,
                   target: str = "events", asof: dt.date | None = None) -> pd.DataFrame:
    """How the count for each recent month changed across successive releases (the evidence)."""
    T = pd.Timestamp(asof or dt.date.today())
    L = store.last_data_month(T)
    origins = [o for o in store.origins(end=T)][-(months + 1):]
    cols = {}
    for o in origins:
        p = store.panel(o, L - months + 1, L, countries=np.array([country_id]))
        v = p.set_index("m")[target].astype(float)
        v[v.index > store.last_data_month(o)] = np.nan  # not yet released at that date
        cols[str(o.date())] = v
    df = pd.DataFrame(cols)
    df.index = [str(month_from_index(m)) for m in df.index]
    return df
