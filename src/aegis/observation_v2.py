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
* **M2**: two-state visibility benchmark (see the M2 section below; PROTOCOL.md A4).
* **V3g**: current reporting state from the reporting triangle. (Round 1 ran this under
  the name "V3", but it is *not* PROTOCOL.md's V3, the mean-reverting latent state model,
  which has not been built yet; see PROTOCOL.md deviation D1.) The growth of last month's
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

CANDIDATES = ("V0", "V1", "V2", "V3g", "M2")
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


# --------------------------------------------------------------------------- M2
# Two-state visibility benchmark (PROTOCOL.md amendment A4). Every threshold is fixed here,
# before M2 has been run once.
M2_LOW = 0.8                           # age-1 completeness below this = LOW state
M2_MIN_FINAL = 5                       # states are only labelled when the final count >= 5
M2_GROWTH_EDGES = (0.02, 0.15)         # buckets of first-to-second-release growth g
M2_STATE_CLAMP = (0.2, 3.0)            # completeness bounds per state


@dataclass
class M2(_Base):
    """Completeness is HIGH or LOW; the state is short-lived (RESULTS.md Table 5).

    A month's true state is only known when its final count is published, far too late to
    matter. So M2 infers it from a signal visible in real time: the growth g of a month's
    count between its first and second release, bucketed and mapped to P(LOW | bucket).
    The newest month has no second release yet; its P(LOW) is propagated one step through
    the Markov chain from the previous month's. The nowcast is observed x E[1 / C] over
    the two states, so it is always bounded between the two state levels; V3g had no such
    bound and overshot.
    """
    base: V2                            # country long-run completeness (robust)
    level: dict                         # (state, age) -> log completeness offset vs base
    p_low_given_bucket: np.ndarray      # P(LOW | growth bucket 0, 1, 2)
    p_ll: float                         # P(LOW next | LOW now)
    p_hl: float                         # P(LOW next | HIGH now)
    p_low_now: pd.Series                # (country_id, m) -> P(LOW) for months at the origin
    L: int
    alpha: pd.Series = field(default_factory=pd.Series)
    n_pairs: int = 0

    def _state_C(self, countries, a):
        idx = pd.MultiIndex.from_arrays([np.asarray(countries, dtype=int), a])
        lr = self.base.log_ratio.reindex(idx).to_numpy()
        lr = np.where(np.isnan(lr), self.base.global_log_ratio.reindex(a).fillna(0.0).to_numpy(), lr)
        lo_off = np.array([self.level.get(("LOW", int(x)), self.level.get(("LOW", ob.MAX_AGE), 0.0)) for x in a])
        hi_off = np.array([self.level.get(("HIGH", int(x)), self.level.get(("HIGH", ob.MAX_AGE), 0.0)) for x in a])
        c_lo = np.clip(np.exp(lr + lo_off), *M2_STATE_CLAMP)
        c_hi = np.clip(np.exp(lr + hi_off), *M2_STATE_CLAMP)
        return c_lo, c_hi

    def nowcast_means(self, countries, ages, observed, p_low=None) -> np.ndarray:
        countries = np.asarray(countries, dtype=int)
        ages = np.asarray(ages)
        a = ob.age_bucket(ages).astype(int)
        if p_low is None:
            months = self.L - ages + 1
            key = pd.MultiIndex.from_arrays([countries, months])
            denom = 1 - self.p_ll + self.p_hl
            base_rate = self.p_hl / denom if denom > 0 else 0.25  # stationary P(LOW)
            p_low = self.p_low_now.reindex(key).fillna(base_rate).to_numpy()
        c_lo, c_hi = self._state_C(countries, a)
        inv_c = p_low / c_lo + (1 - p_low) / c_hi
        obs = np.asarray(observed, float)
        zero = self.base.base.nowcast_means(countries, ages, np.zeros_like(obs))
        return np.where(obs > 0, obs * inv_c, zero)


def _bucket(g: np.ndarray) -> np.ndarray:
    return np.digitize(np.asarray(g, float), M2_GROWTH_EDGES)


def fit_m2(pairs: pd.DataFrame, history: pd.DataFrame, origin: pd.Timestamp, target: str,
           base: V2) -> M2:
    growth = growth_table(history[history["origin"] <= origin], target)

    # 1. label age-1 states where the final count is known and large enough
    a1 = pairs[(pairs["age"] == 1) & (pairs["final"] >= M2_MIN_FINAL)].drop_duplicates(["country_id", "m"])
    state = pd.Series(np.where(a1["obs"] / a1["final"] < M2_LOW, "LOW", "HIGH"),
                      index=pd.MultiIndex.from_arrays([a1["country_id"], a1["m"]]))

    # 2. P(LOW | growth bucket), add-one smoothed
    g = growth.reindex(state.index)
    ok = g.notna()
    b = _bucket(g[ok].to_numpy())
    is_low = (state[ok] == "LOW").to_numpy()
    p_bucket = np.array([(is_low[b == k].sum() + 1) / ((b == k).sum() + 2) for k in range(3)])

    # 3. transitions between consecutive months
    s = state.sort_index()
    nxt = s.groupby(level=0).shift(-1)
    months = s.index.get_level_values(1).to_numpy()
    nxt_m = pd.Series(months, index=s.index).groupby(level=0).shift(-1).to_numpy()
    consec = (nxt_m == months + 1) & nxt.notna().to_numpy()
    cur, fut = s.to_numpy()[consec], nxt.to_numpy()[consec]
    p_ll = ((cur == "LOW") & (fut == "LOW")).sum() / max((cur == "LOW").sum(), 1)
    p_hl = ((cur == "HIGH") & (fut == "LOW")).sum() / max((cur == "HIGH").sum(), 1)

    # 4. completeness level of each state, as an offset from the country's long-run level
    pos = pairs[(pairs["obs"] > 0) & (pairs["final"] >= M2_MIN_FINAL)].copy()
    pos["state"] = state.reindex(pd.MultiIndex.from_arrays([pos["country_id"], pos["m"]])).to_numpy()
    pos = pos.dropna(subset=["state"])
    idx = pd.MultiIndex.from_arrays([pos["country_id"].to_numpy(), pos["age_b"].to_numpy()])
    base_lr = base.log_ratio.reindex(idx).to_numpy()
    base_lr = np.where(np.isnan(base_lr), base.global_log_ratio.reindex(pos["age_b"]).fillna(0.0).to_numpy(), base_lr)
    resid = np.log(pos["obs"] / pos["final"]).to_numpy() - base_lr
    level = pd.Series(resid).groupby([pos["state"].to_numpy(), pos["age_b"].to_numpy()]).median().to_dict()

    # 5. P(LOW) for months at the origin: own growth signal where it exists (age >= 2),
    #    Markov step from the previous month for the newest month
    cur_hist = history[history["origin"] <= origin]
    L = int(cur_hist["L"].max())
    p_now = {}
    countries = cur_hist["country_id"].unique()
    for c in countries:
        for mm in range(L - ob.MAX_AGE, L):
            gv = growth.get((c, mm))
            if gv is not None and np.isfinite(gv):
                p_now[(c, mm)] = p_bucket[_bucket([gv])[0]]
        prev = p_now.get((c, L - 1))
        if prev is not None:
            p_now[(c, L)] = prev * p_ll + (1 - prev) * p_hl
    p_low_now = pd.Series(p_now, dtype=float)
    if len(p_low_now):
        p_low_now.index = pd.MultiIndex.from_tuples(p_low_now.index)

    m = M2(base=base, level=level, p_low_given_bucket=p_bucket, p_ll=float(p_ll), p_hl=float(p_hl),
           p_low_now=p_low_now, L=L, n_pairs=len(pairs))
    # dispersion, fitted on in-sample nowcasts using each pair's own state probability
    key = pd.MultiIndex.from_arrays([pairs["country_id"].to_numpy(), pairs["m"].to_numpy()])
    gp = growth.reindex(key).to_numpy()
    stationary = p_hl / (1 - p_ll + p_hl) if (1 - p_ll + p_hl) > 0 else 0.25
    p_pair = np.where(np.isfinite(gp), p_bucket[_bucket(np.nan_to_num(gp))], stationary)
    mu = m.nowcast_means(pairs["country_id"], pairs["age_b"], pairs["obs"], p_low=p_pair)
    m.alpha = _alpha_by_age(pairs, np.maximum(mu, 1e-3))
    return m


def fit_all(history: pd.DataFrame, store: VintageStore, origin: pd.Timestamp,
            target: str = "events") -> dict:
    """V0 (the v0.1 estimator) plus the v0.2 candidates, all fitted at ``origin``."""
    v0 = ob.fit(history, store, origin, target)
    pairs, _ = ob.training_pairs(history, store, origin, target)
    v2 = fit_v2(pairs, v0)
    return {
        "V0": v0,
        "V1": V1(v0),
        "V2": v2,
        "V3g": fit_v3(pairs, history, origin, target),
        "M2": fit_m2(pairs, history, origin, target, v2),
    }
