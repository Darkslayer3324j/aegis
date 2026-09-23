"""v0.2 observation-model candidates (PROTOCOL.md §4).

Each candidate exposes the interface that ``observation.correct_panel`` and the backtest
use: ``nowcast_means(countries, ages, observed)``, ``nowcast(country, age, obs)``,
``alpha`` (NB dispersion per age bucket) and ``n_pairs``. All parameters are fixed in
advance. None is tuned on outer backtest scores, so choosing among them on development
data is the only selection step (PROTOCOL.md §4).

* **V1**: V0 with the correction limited to recent months (age <= 6). Older non-final
  months are left as observed.
* **V2**: robust, long memory. Per country and age, the median log revision ratio over
  all past pairs (no time decay), shrunk toward the global median.
* **V3**: current reporting state from the reporting triangle. The growth of last month's
  count between its first and second release, g = log(obs@age2 + 1) - log(obs@age1 + 1),
  is a real-time signal of whether reporting is lagging *now*. Regression per age:
  log((final + 1) / (obs + 1)) ~ 1 + country prior + g + 1{obs = 0}.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import observation as ob
from .scoring import CountForecast, fit_alpha
from .vintage import VintageStore

CANDIDATES = ("V0", "V1", "V2", "V3")
V1_AGE_CAP = 6
V2_SHRINK_MONTHS = 6.0
V3_SHRINK_MONTHS = 6.0
V3_LOG_CLAMP = 2.0  # predicted log adjustment clamped to [-2, 2] (x0.14 .. x7.4)


def _alpha_by_age(pairs: pd.DataFrame, mu: np.ndarray) -> pd.Series:
    out = {}
    for a, idx in pairs.groupby("age_b").groups.items():
        sel = pairs.index.get_indexer(idx)
        out[a] = fit_alpha(pairs["final"].to_numpy()[sel], mu[sel], pairs["w"].to_numpy()[sel])
    return pd.Series(out).sort_index()


class _Base:
    alpha: pd.Series
    n_pairs: int

    def nowcast_means(self, countries, ages, observed) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError

    def nowcast(self, country: int, age: int, observed: int) -> CountForecast:
        mu = float(self.nowcast_means([country], [age], [observed])[0])
        a = int(min(age, ob.MAX_AGE))
        alpha = float(self.alpha.get(a, self.alpha.iloc[-1] if len(self.alpha) else 0.5))
        return CountForecast.point(mu, alpha)


@dataclass
class V1(_Base):
    """V0 restricted to recent ages; ``age_cap`` is honoured by ``correct_panel``."""
    base: ob.ObservationModel
    age_cap: int = V1_AGE_CAP

    def __post_init__(self):
        self.alpha, self.n_pairs = self.base.alpha, self.base.n_pairs

    def nowcast_means(self, countries, ages, observed) -> np.ndarray:
        mu = self.base.nowcast_means(countries, ages, observed)
        return np.where(np.asarray(ages) > self.age_cap, np.asarray(observed, float), mu)


@dataclass
class V2(_Base):
    log_ratio: pd.Series            # (country_id, age) -> shrunk median log(obs/final)
    global_log_ratio: pd.Series     # age -> global median
    base: ob.ObservationModel       # zero-observation rate borrowed from V0
    alpha: pd.Series = field(default_factory=pd.Series)
    n_pairs: int = 0

    def nowcast_means(self, countries, ages, observed) -> np.ndarray:
        a = ob.age_bucket(ages).astype(int)
        idx = pd.MultiIndex.from_arrays([np.asarray(countries, dtype=int), a])
        lr = self.log_ratio.reindex(idx).to_numpy()
        lr = np.where(np.isnan(lr), self.global_log_ratio.reindex(a).fillna(0.0).to_numpy(), lr)
        C = np.clip(np.exp(lr), 0.2, 3.0)
        obs = np.asarray(observed, float)
        zero = self.base.nowcast_means(countries, ages, np.zeros_like(obs))
        return np.where(obs > 0, obs / C, zero)


def fit_v2(pairs: pd.DataFrame, base: ob.ObservationModel) -> V2:
    pos = pairs[(pairs["obs"] > 0) & (pairs["final"] > 0)]
    lr = np.log(pos["obs"] / pos["final"])
    g = lr.groupby(pos["age_b"]).median()
    by = lr.groupby([pos["country_id"], pos["age_b"]]).agg(["median", "size"])
    gm = g.reindex(by.index.get_level_values(1)).to_numpy()
    shrunk = (by["size"] * by["median"] + V2_SHRINK_MONTHS * gm) / (by["size"] + V2_SHRINK_MONTHS)
    shrunk.index = shrunk.index.rename(["country_id", "age"])
    m = V2(log_ratio=shrunk, global_log_ratio=g, base=base, n_pairs=len(pairs))
    m.alpha = _alpha_by_age(pairs, m.nowcast_means(pairs["country_id"], pairs["age_b"], pairs["obs"]))
    return m


# --------------------------------------------------------------------------- V3
def growth_table(history: pd.DataFrame, target: str) -> pd.Series:
    """g(country, m) = log(obs at age 2 + 1) - log(obs at age 1 + 1), from real vintages."""
    h = history[~history["is_final"] & history["age"].isin([1, 2])]
    first = h.sort_values("origin").drop_duplicates(["country_id", "m", "age"], keep="first")
    w = first.pivot_table(index=["country_id", "m"], columns="age", values=target)
    if 1 not in w or 2 not in w:
        return pd.Series(dtype=float)
    g = np.log(w[2] + 1) - np.log(w[1] + 1)
    return g.dropna()


@dataclass
class V3(_Base):
    beta: dict                      # age -> coefficient vector
    prior: pd.Series                # (country_id, age) -> shrunk mean log adjustment
    global_prior: pd.Series         # age -> global mean
    g_now: pd.Series                # country -> current growth signal
    alpha: pd.Series = field(default_factory=pd.Series)
    n_pairs: int = 0

    def _design(self, countries, a, obs, g):
        idx = pd.MultiIndex.from_arrays([np.asarray(countries, dtype=int), a])
        pr = self.prior.reindex(idx).to_numpy()
        pr = np.where(np.isnan(pr), self.global_prior.reindex(a).fillna(0.0).to_numpy(), pr)
        return np.column_stack([np.ones(len(a)), pr, g, (obs == 0).astype(float)])

    def predict(self, countries, ages, observed, g) -> np.ndarray:
        a = ob.age_bucket(ages).astype(int)
        obs = np.asarray(observed, float)
        X = self._design(countries, a, obs, np.asarray(g, float))
        adj = np.zeros(len(a))
        for age in np.unique(a):
            b = self.beta.get(int(age)) if int(age) in self.beta else self.beta[max(self.beta)]
            sel = a == age
            adj[sel] = X[sel] @ b
        adj = np.clip(adj, -V3_LOG_CLAMP, V3_LOG_CLAMP)
        return np.maximum((obs + 1) * np.exp(adj) - 1, 1e-3)

    def nowcast_means(self, countries, ages, observed) -> np.ndarray:
        g = self.g_now.reindex(np.asarray(countries, dtype=int)).fillna(0.0).to_numpy()
        return self.predict(countries, ages, observed, g)


def fit_v3(pairs: pd.DataFrame, history: pd.DataFrame, origin: pd.Timestamp, target: str) -> V3:
    growth = growth_table(history[history["origin"] <= origin], target)
    # signal available when each pair was observed: growth of the month before its L
    key = pd.MultiIndex.from_arrays([pairs["country_id"].to_numpy(), (pairs["L"] - 1).to_numpy()])
    g_pair = growth.reindex(key).fillna(0.0).to_numpy()
    y = np.log((pairs["final"] + 1) / (pairs["obs"] + 1)).to_numpy()
    ab = pairs["age_b"].to_numpy()

    glob = pd.Series(y).groupby(ab).mean()
    by = pd.DataFrame({"c": pairs["country_id"].to_numpy(), "a": ab, "y": y}).groupby(["c", "a"])["y"].agg(["mean", "size"])
    gm = glob.reindex(by.index.get_level_values(1)).to_numpy()
    prior = (by["size"] * by["mean"] + V3_SHRINK_MONTHS * gm) / (by["size"] + V3_SHRINK_MONTHS)
    prior.index = prior.index.rename(["country_id", "age"])

    m = V3(beta={}, prior=prior, global_prior=glob, g_now=pd.Series(dtype=float), n_pairs=len(pairs))
    X = m._design(pairs["country_id"].to_numpy(), ab, pairs["obs"].to_numpy(float), g_pair)
    w = pairs["w"].to_numpy()
    for age in np.unique(ab):
        sel = ab == age
        sw = np.sqrt(w[sel])
        beta, *_ = np.linalg.lstsq(X[sel] * sw[:, None], y[sel] * sw, rcond=None)
        m.beta[int(age)] = beta

    # current signal at the origin: growth of month L-1, L = newest month in history <= origin
    cur = history[history["origin"] <= origin]
    L_now = int(cur["L"].max())
    gn = growth[growth.index.get_level_values("m") == L_now - 1]
    m.g_now = pd.Series(gn.to_numpy(), index=gn.index.get_level_values("country_id"))
    mu_in = m.predict(pairs["country_id"].to_numpy(), pairs["age_b"].to_numpy(),
                      pairs["obs"].to_numpy(), g_pair)
    m.alpha = _alpha_by_age(pairs, mu_in)
    return m


def fit_all(history: pd.DataFrame, store: VintageStore, origin: pd.Timestamp,
            target: str = "events") -> dict:
    """V0 (the v0.1 estimator) plus the v0.2 candidates, all fitted at ``origin``."""
    v0 = ob.fit(history, store, origin, target)
    pairs, _ = ob.training_pairs(history, store, origin, target)
    return {
        "V0": v0,
        "V1": V1(v0),
        "V2": fit_v2(pairs, v0),
        "V3": fit_v3(pairs, history, origin, target),
    }
