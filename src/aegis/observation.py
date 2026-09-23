"""Observation model: how much of a month has been reported, and what will it become?

For a month ``m`` seen at vintage age ``a`` (a = 1 is the newest month, first release),
AEGIS estimates the **expected observation completeness**

    C[c, a] = E[ count reported by age a ] / E[ eventual final count ]

for each country ``c``, from past pairs of (count at age a, final count). It is learned
only from months whose final value had been published by the forecast origin, so the
model never sees revisions that arrive later.

Completeness can exceed 1: Candidate data sometimes contains events that the annual
vetting later removes. That is reported as-is rather than clipped.

The nowcast of the eventual count is negative binomial:

    mean = observed / C[c, a]          if observed > 0
    mean = lambda0[c, a]               if observed == 0 (events that surface later)
    dispersion alpha[a], fitted by maximum likelihood on the same pairs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .scoring import CountForecast, fit_alpha
from .vintage import VintageStore

MAX_AGE = 12          # ages above this are pooled into one bucket
KAPPA = 20.0          # pseudo-events pulling a country's completeness toward its age average
KAPPA_ZERO = 6.0      # pseudo-months for the zero-observation rate
HALF_LIFE = 18.0      # months; older reporting behaviour counts for less
HISTORY_MONTHS = 24   # how far back each historical snapshot is kept


def age_bucket(age: np.ndarray | pd.Series) -> np.ndarray:
    return np.minimum(np.asarray(age), MAX_AGE)


def build_history(store: VintageStore, origins: list[pd.Timestamp], progress=None) -> pd.DataFrame:
    """Counts as they looked at each origin, for the last ``HISTORY_MONTHS`` months."""
    frames = []
    for i, t in enumerate(origins):
        L = store.last_data_month(t)
        if L is None:
            continue
        p = store.panel(t, L - HISTORY_MONTHS + 1, L)
        # Keep only months some available release actually covered. Without this, months
        # before the first Candidate release (and before the first final in the store)
        # look like "0 reported" and poison the completeness estimates.
        p = p[store.covered(t, p["m"].to_numpy())]
        p["origin"] = t
        p["L"] = L
        p["age"] = L - p["m"] + 1
        frames.append(p)
        if progress:
            progress(i + 1, len(origins))
    return pd.concat(frames, ignore_index=True)


@dataclass
class ObservationModel:
    target: str
    completeness: pd.DataFrame      # index (country_id, age) -> C
    global_completeness: pd.Series  # index age -> C
    lambda0: pd.DataFrame           # index (country_id, age) -> expected count when 0 observed
    alpha: pd.Series                # index age -> NB dispersion
    volatility: pd.Series           # country -> sd of log revision ratio at age 1
    n_pairs: int
    origin: pd.Timestamp
    final_name: str
    extras: dict = field(default_factory=dict)

    def C(self, country: int, age: int) -> float:
        a = int(min(age, MAX_AGE))
        try:
            return float(self.completeness.loc[(country, a), "C"])
        except KeyError:
            return float(self.global_completeness.get(a, 1.0))

    def lam0(self, country: int, age: int) -> float:
        a = int(min(age, MAX_AGE))
        try:
            return float(self.lambda0.loc[(country, a), "lam0"])
        except KeyError:
            return float(self.extras["global_lam0"].get(a, 0.0))

    def nowcast(self, country: int, age: int, observed: int) -> CountForecast:
        a = int(min(age, MAX_AGE))
        alpha = float(self.alpha.get(a, self.alpha.iloc[-1] if len(self.alpha) else 0.5))
        if observed > 0:
            mu = observed / max(self.C(country, a), 0.05)
        else:
            mu = self.lam0(country, a)
        return CountForecast.point(mu, alpha)

    def nowcast_mean(self, country: int, age: int, observed: int) -> float:
        if observed > 0:
            return observed / max(self.C(country, age), 0.05)
        return self.lam0(country, age)

    def nowcast_means(self, countries, ages, observed) -> np.ndarray:
        """Vectorised ``nowcast_mean``."""
        a = age_bucket(ages).astype(int)
        idx = pd.MultiIndex.from_arrays([np.asarray(countries, dtype=int), a])
        C = self.completeness["C"].reindex(idx).to_numpy()
        C = np.where(np.isnan(C), self.global_completeness.reindex(a).fillna(1.0).to_numpy(), C)
        l0 = self.lambda0["lam0"].reindex(idx).to_numpy()
        l0 = np.where(np.isnan(l0), self.extras["global_lam0"].reindex(a).fillna(0.0).to_numpy(), l0)
        obs = np.asarray(observed, dtype=float)
        return np.where(obs > 0, obs / np.maximum(C, 0.05), l0)


def training_pairs(history: pd.DataFrame, store: VintageStore, origin: pd.Timestamp,
                   target: str) -> tuple[pd.DataFrame, str]:
    """(observed at age a, final) pairs whose final value was public at ``origin``."""
    final = store.latest_final(origin)
    if final is None:
        raise ValueError(f"no final release available at {origin.date()}")
    truth, _ = store.truth(final.name)
    h = history[(history["origin"] <= origin) & (~history["is_final"]) & (history["m"] <= final.cover_end)]
    h = h.join(truth[target].rename("final"), on=["country_id", "m"])
    h["final"] = h["final"].fillna(0).astype(int)
    h = h.rename(columns={target: "obs"})
    # time-decay weights, measured from the origin being fitted
    L_now = store.last_data_month(origin)
    h["w"] = 0.5 ** ((L_now - h["L"]) / HALF_LIFE)
    h["age_b"] = age_bucket(h["age"])
    return h[["country_id", "m", "L", "age", "age_b", "obs", "final", "w"]], final.name


def fit(history: pd.DataFrame, store: VintageStore, origin: pd.Timestamp,
        target: str = "events") -> ObservationModel:
    pairs, final_name = training_pairs(history, store, origin, target)
    if pairs.empty:
        raise ValueError(f"no observation pairs available at {origin.date()}")

    pos = pairs[(pairs["obs"] > 0) | (pairs["final"] > 0)]
    wo = (pos["w"] * pos["obs"]).groupby(pos["age_b"]).sum()
    wf = (pos["w"] * pos["final"]).groupby(pos["age_b"]).sum()
    global_C = (wo / wf.replace(0, np.nan)).fillna(1.0).clip(0.05, 3.0)

    by_c = pos.assign(wo=pos["w"] * pos["obs"], wf=pos["w"] * pos["final"]).groupby(
        ["country_id", "age_b"])[["wo", "wf"]].sum()
    gC = global_C.reindex(by_c.index.get_level_values("age_b")).to_numpy()
    C = (by_c["wo"] + KAPPA * gC) / (by_c["wf"] + KAPPA)
    completeness = C.clip(0.05, 3.0).rename("C").to_frame()
    completeness.index = completeness.index.rename(["country_id", "age"])

    zero = pairs[pairs["obs"] == 0]
    g_lam0 = ((zero["w"] * zero["final"]).groupby(zero["age_b"]).sum()
              / zero["w"].groupby(zero["age_b"]).sum()).fillna(0.0)
    zc = zero.assign(wf=zero["w"] * zero["final"]).groupby(["country_id", "age_b"]).agg(
        wf=("wf", "sum"), w=("w", "sum"))
    gl = g_lam0.reindex(zc.index.get_level_values("age_b")).to_numpy()
    lam0 = ((zc["wf"] + KAPPA_ZERO * gl) / (zc["w"] + KAPPA_ZERO)).rename("lam0").to_frame()
    lam0.index = lam0.index.rename(["country_id", "age"])

    model = ObservationModel(
        target=target, completeness=completeness, global_completeness=global_C,
        lambda0=lam0, alpha=pd.Series(dtype=float), volatility=pd.Series(dtype=float),
        n_pairs=len(pairs), origin=origin, final_name=final_name,
        extras={"global_lam0": g_lam0},
    )

    # Dispersion per age, fitted on the nowcast means the model would have produced.
    mu = model.nowcast_means(pairs["country_id"], pairs["age_b"], pairs["obs"])
    alphas = {}
    for a, idx in pairs.groupby("age_b").groups.items():
        sel = pairs.index.get_indexer(idx)
        alphas[a] = fit_alpha(pairs["final"].to_numpy()[sel], mu[sel], pairs["w"].to_numpy()[sel])
    model.alpha = pd.Series(alphas).sort_index()
    # Dispersion for the naive alternative that treats the raw count as the final count.
    model.extras["raw_alpha"] = {
        a: fit_alpha(pairs["final"].to_numpy()[pairs.index.get_indexer(idx)],
                     pairs["obs"].to_numpy()[pairs.index.get_indexer(idx)],
                     pairs["w"].to_numpy()[pairs.index.get_indexer(idx)])
        for a, idx in pairs.groupby("age_b").groups.items()
    }

    a1 = pairs[(pairs["age"] == 1) & ((pairs["obs"] > 0) | (pairs["final"] > 0))]
    lr = np.log((a1["obs"] + 1) / (a1["final"] + 1))
    model.volatility = lr.groupby(a1["country_id"]).std().fillna(0.0)
    return model


def correct_panel(panel: pd.DataFrame, model: ObservationModel, L: int, target: str,
                  draws: int = 0, rng: np.random.Generator | None = None):
    """Replace non-final counts with nowcast means (and optionally sample draws).

    Returns (mean_values, draw_matrix | None) aligned with ``panel`` rows. Final rows keep
    their observed value. **Every** non-final row is corrected: rows older than
    ``MAX_AGE`` share the pooled age-``MAX_AGE`` completeness. (Whether old non-final
    months should be corrected at all is an open v0.2 question; see RESULTS.md.)
    """
    values = panel[target].to_numpy(dtype=float).copy()
    ages = (L - panel["m"].to_numpy() + 1)
    open_rows = np.flatnonzero(~panel["is_final"].to_numpy())
    mu = model.nowcast_means(panel["country_id"].to_numpy()[open_rows], ages[open_rows],
                             values[open_rows])
    mu = np.maximum(mu, 1e-3)
    values[open_rows] = mu
    samples = None
    if draws:
        rng = rng or np.random.default_rng(0)
        samples = np.repeat(values[:, None], draws, axis=1)
        a = age_bucket(ages[open_rows])
        fallback = float(model.alpha.iloc[-1]) if len(model.alpha) else 0.5
        alpha = model.alpha.reindex(a).fillna(fallback).to_numpy()
        n = 1.0 / np.maximum(alpha, 1e-8)
        p = n / (n + mu)
        samples[open_rows] = rng.negative_binomial(n[:, None], p[:, None], size=(len(open_rows), draws))
    return values, samples
