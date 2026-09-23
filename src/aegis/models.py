"""Forecasting models. Deliberately simple: complexity has to earn its place.

All models forecast the count for month ``L + h`` (h = 1, 2, 3) where ``L`` is the last
month with any data. Inputs are a country x month matrix ``Y`` (the view of the world the
model is allowed to see).

* ``naive``     persistence: mean = Y[L]
* ``ma6``       mean of the last six months
* ``nbar``      pooled negative-binomial autoregression on log1p lags (the baseline to beat)
* ``nbar+vis``  AEGIS: the same regression, but recent months are replaced by nowcasts of
                their eventual value, and the forecast integrates over the nowcast
                uncertainty (mixture over draws)
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import statsmodels.api as sm

from .scoring import CountForecast, fit_alpha

LAGS_NEEDED = 12
TRAIN_WINDOWS = 36
MODELS = ("naive", "ma6", "nbar", "nbar+vis")


LEVEL_EPS = 0.1


def features(Y: np.ndarray, s: int) -> tuple[np.ndarray, np.ndarray]:
    """(design matrix, log offset) for predicting from column ``s`` of ``Y``.

    The model is anchored to the recent level: ``log mu = log(ma6 + eps) + X @ beta``.
    Large counts therefore scale proportionally instead of being extrapolated through a
    power law (an unanchored log1p-lag regression forecast ~9,900 events for Ukraine when
    710 happened). The regressors only describe momentum and small-count behaviour.
    """
    lag1 = Y[:, s]
    ma3 = Y[:, s - 2:s + 1].mean(axis=1)
    ma6 = Y[:, s - 5:s + 1].mean(axis=1)
    ma12 = Y[:, s - 11:s + 1].mean(axis=1)
    X = np.column_stack([
        np.ones(len(Y)),
        np.log((lag1 + 1) / (ma6 + 1)),   # latest month vs half-year level
        np.log((ma3 + 1) / (ma12 + 1)),   # quarter vs year: acceleration
        1.0 / (1.0 + ma6),                # small-count regime
        (ma12 > 0).astype(float) * (ma6 == 0),  # recently quiet after activity
    ])
    return X, np.log(ma6 + LEVEL_EPS)


@dataclass
class NBAR:
    beta: np.ndarray
    alpha: float

    @classmethod
    def fit(cls, Y: np.ndarray, h: int, windows: int = TRAIN_WINDOWS) -> "NBAR":
        """Fit on every (country, s) with s + h inside ``Y`` and enough history before s."""
        last = Y.shape[1] - 1
        ss = [s for s in range(last - h - windows + 1, last - h + 1) if s >= LAGS_NEEDED - 1]
        parts = [features(Y, s) for s in ss]
        X = np.vstack([p[0] for p in parts])
        off = np.concatenate([p[1] for p in parts])
        y = np.round(np.concatenate([Y[:, s + h] for s in ss]))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                res = sm.NegativeBinomial(y, X, offset=off).fit(disp=0, maxiter=300, method="bfgs")
                beta, alpha = res.params[:-1], float(res.params[-1])
                if not np.all(np.isfinite(beta)) or not (1e-4 < alpha < 50):
                    raise ValueError("unstable NB fit")
            except Exception:
                res = sm.GLM(y, X, family=sm.families.Poisson(), offset=off).fit()
                beta = res.params
                alpha = fit_alpha(y, np.exp(X @ beta + off))
        return cls(np.asarray(beta), alpha)

    def mean(self, Xo: tuple[np.ndarray, np.ndarray]) -> np.ndarray:
        X, off = Xo
        return np.exp(np.clip(X @ self.beta + off, -20, 12))


def _alpha_for(Y: np.ndarray, h: int, mean_fn) -> float:
    last = Y.shape[1] - 1
    ss = [s for s in range(last - h - TRAIN_WINDOWS + 1, last - h + 1) if s >= LAGS_NEEDED - 1]
    mu = np.concatenate([mean_fn(Y, s) for s in ss])
    y = np.concatenate([Y[:, s + h] for s in ss])
    return fit_alpha(np.round(y), mu)


def naive_mean(Y: np.ndarray, s: int) -> np.ndarray:
    return Y[:, s]


def ma6_mean(Y: np.ndarray, s: int) -> np.ndarray:
    return Y[:, s - 5:s + 1].mean(axis=1)


def forecast_all(Y: np.ndarray, h: int, Y_vis: np.ndarray | None = None,
                 Y_vis_draws: np.ndarray | None = None) -> dict[str, list[CountForecast]]:
    """Forecasts for every country (row of ``Y``) at horizon ``h`` for each model.

    ``Y_vis`` is the nowcast-corrected mean matrix; ``Y_vis_draws`` has shape
    (countries, months, draws). Without them the visibility model is skipped.
    """
    s = Y.shape[1] - 1
    out: dict[str, list[CountForecast]] = {}
    for name, fn in (("naive", naive_mean), ("ma6", ma6_mean)):
        a = _alpha_for(Y, h, fn)
        out[name] = [CountForecast.point(m, a) for m in fn(Y, s)]
    base = NBAR.fit(Y, h)
    out["nbar"] = [CountForecast.point(m, base.alpha) for m in base.mean(features(Y, s))]
    if Y_vis is not None:
        vis = NBAR.fit(Y_vis, h)
        if Y_vis_draws is not None:
            mus = np.column_stack([
                vis.mean(features(Y_vis_draws[:, :, d], s)) for d in range(Y_vis_draws.shape[2])
            ])
        else:
            mus = vis.mean(features(Y_vis, s))[:, None]
        out["nbar+vis"] = [CountForecast(mus[i], vis.alpha) for i in range(len(Y))]
    return out
