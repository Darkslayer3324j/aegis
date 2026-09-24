"""One forecast cycle at a single origin: vintage view -> observation model -> nowcast -> forecast.

Used by the backtest (at every historical origin) and by the live run (at today's date),
so the two can never drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import observation as ob
from . import observation_v2 as ob2
from .models import LAGS_NEEDED, TRAIN_WINDOWS, forecast_all
from .scoring import CountForecast
from .vintage import VintageStore

HORIZONS = (1, 2, 3)
# Model name for each observation candidate. "nbar+vis" is V0, the v0.1 estimator.
VIS_MODELS = {"V0": "nbar+vis", "V1": "nbar+V1", "V2": "nbar+V2", "V3g": "nbar+V3g"}
WINDOW = TRAIN_WINDOWS + LAGS_NEEDED + max(HORIZONS)

# Visibility decision thresholds. Abstention follows from an impaired observation
# process, never from the forecasting model's own confidence.
C_ABSTAIN = 0.5
C_WARN = 0.8
VOL_WARN = 1.0
DARK_MIN_ACTIVITY = 3.0


class CoverageGap(Exception):
    """Some month in the model window is covered by no release available at the origin.

    Such a month is unknown, not zero, so the origin is skipped rather than filled in.
    """

    def __init__(self, origin, gaps):
        self.origin, self.gaps = origin, gaps
        super().__init__(f"{origin.date()}: {len(gaps)} uncovered months")


@dataclass
class OriginRun:
    origin: pd.Timestamp
    L: int
    first: int
    countries: np.ndarray
    panel: pd.DataFrame              # long vintage panel with is_final
    Y: np.ndarray                    # vintage matrix (countries x months)
    Y_vis: np.ndarray                # nowcast-corrected means
    Y_draws: np.ndarray | None       # (countries, months, draws)
    is_final: np.ndarray             # (countries, months)
    obs_model: ob.ObservationModel   # V0: drives the visibility flags and completeness display
    obs_models: dict                 # every candidate, keyed by VIS_MODELS
    forecasts: dict[int, dict[str, list[CountForecast]]]
    status: pd.DataFrame             # per-country visibility state


def wide(panel: pd.DataFrame, value, countries: np.ndarray, first: int, last: int) -> np.ndarray:
    v = panel.assign(_v=value).pivot(index="country_id", columns="m", values="_v")
    return v.reindex(index=countries, columns=range(first, last + 1)).fillna(0).to_numpy(float)


def visibility_status(run_Y: np.ndarray, countries: np.ndarray, model: ob.ObservationModel) -> pd.DataFrame:
    rows = []
    for i, c in enumerate(countries):
        c1 = model.C(int(c), 1)
        vol = float(model.volatility.get(int(c), 0.0))
        act12 = float(run_Y[i, -12:].mean())
        last = float(run_Y[i, -1])
        dark = act12 >= DARK_MIN_ACTIVITY and last == 0
        lam0 = model.lam0(int(c), 1)
        if c1 < C_ABSTAIN or (dark and lam0 >= 1.0):
            status = "ABSTAIN"
        elif c1 < C_WARN or vol > VOL_WARN or dark:
            status = "WARN"
        else:
            status = "OK"
        rows.append({"country_id": int(c), "C1": c1, "C2": model.C(int(c), 2), "C3": model.C(int(c), 3),
                     "volatility": vol, "activity12": act12, "dark": dark, "status": status})
    return pd.DataFrame(rows)


def run_origin(store: VintageStore, history: pd.DataFrame, origin: pd.Timestamp,
               target: str = "events", draws: int = 40, seed: int = 0,
               countries: np.ndarray | None = None,
               candidates: tuple[str, ...] = ("V0", "V1", "V2", "V3g")) -> OriginRun:
    L = store.last_data_month(origin)
    first = L - WINDOW + 1
    months = np.arange(first, L + 1)
    gaps = months[~store.covered(origin, months)]
    if len(gaps):
        raise CoverageGap(origin, gaps)
    if countries is None:
        countries = store.countries_at(origin)
    panel = store.panel(origin, first, L, countries=countries)
    Y = wide(panel, panel[target], countries, first, L)
    fin = wide(panel, panel["is_final"].astype(float), countries, first, L).astype(bool)

    models = ob2.fit_all(history, store, origin, target)
    views = {}
    for key, name in VIS_MODELS.items():
        if key not in candidates:
            continue
        vals, dr = ob.correct_panel(panel, models[key], L, target, draws=draws,
                                    rng=np.random.default_rng(seed))
        Yv = wide(panel, vals, countries, first, L)
        Yd = None
        if dr is not None:
            Yd = np.stack([wide(panel, dr[:, d], countries, first, L) for d in range(draws)], axis=2)
        views[name] = (Yv, Yd)

    fcs = {h: forecast_all(Y, h, views) for h in HORIZONS}
    status = visibility_status(Y, countries, models["V0"])
    Y_vis, Y_draws = views.get("nbar+vis", (Y, None))
    return OriginRun(origin, L, first, countries, panel, Y, Y_vis, Y_draws, fin, models["V0"], models,
                     fcs, status)


def final_view(store: VintageStore, countries: np.ndarray, first: int, last: int,
               target: str, truth_name: str) -> np.ndarray:
    """The same window seen through a pinned final release (the leaky retrospective view)."""
    truth, _ = store.truth(truth_name)
    t = truth[target].reset_index()
    t = t[(t["m"] >= first) & (t["m"] <= last)]
    v = t.pivot(index="country_id", columns="m", values=target)
    return v.reindex(index=countries, columns=range(first, last + 1)).fillna(0).to_numpy(float)
