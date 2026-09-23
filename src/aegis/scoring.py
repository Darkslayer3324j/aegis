"""Count forecast distributions and proper scoring rules.

Every AEGIS forecast is a negative binomial, or an equal-weight mixture of negative
binomials when the inputs themselves are uncertain (nowcast draws). Scores are computed
on the exact probability mass function, not on samples:

* CRPS for integer outcomes: sum_k (F(k) - 1{y <= k})^2
* log score: -log p(y), computed in log space (no probability floor)
* Brier score for the event "at least one event": (P(Y > 0) - 1{y > 0})^2
* central 80% interval coverage and a randomised PIT value for calibration plots
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats
from scipy.optimize import minimize_scalar
from scipy.special import logsumexp

MU_FLOOR = 1e-3
TAIL = 1e-7  # probability mass allowed beyond the evaluation grid


def nb(mu: np.ndarray, alpha: float):
    """scipy negative binomial with mean ``mu`` and variance ``mu + alpha * mu**2``."""
    mu = np.maximum(np.asarray(mu, dtype=float), MU_FLOOR)
    n = 1.0 / max(alpha, 1e-8)
    return stats.nbinom(n, n / (n + mu))


@dataclass
class CountForecast:
    """Equal-weight mixture of NB(mu_s, alpha) over draws ``mus``."""

    mus: np.ndarray
    alpha: float

    @classmethod
    def point(cls, mu: float, alpha: float) -> "CountForecast":
        return cls(np.array([mu], dtype=float), alpha)

    @property
    def mean(self) -> float:
        return float(np.maximum(self.mus, MU_FLOOR).mean())

    def _grid(self, y: int = 0) -> np.ndarray:
        hi = int(nb(self.mus.max(), self.alpha).ppf(1 - TAIL))
        return np.arange(max(hi, y) + 2)

    def pmf(self, k: np.ndarray) -> np.ndarray:
        return nb(self.mus[None, :], self.alpha).pmf(k[:, None]).mean(axis=1)

    def cdf(self, k: np.ndarray) -> np.ndarray:
        return nb(self.mus[None, :], self.alpha).cdf(k[:, None]).mean(axis=1)

    def quantile(self, q: float) -> int:
        k = self._grid()
        c = self.cdf(k)
        return int(k[np.searchsorted(c, q)]) if c[-1] >= q else int(k[-1])

    def p_positive(self) -> float:
        return float(1.0 - self.cdf(np.array([0]))[0])

    def logpmf(self, y: int) -> float:
        """log p(y) for the mixture, via logsumexp: exact, with no floor or underflow."""
        lp = nb(self.mus, self.alpha).logpmf(y)
        return float(logsumexp(lp) - np.log(len(self.mus)))

    def score(self, y: int, rng: np.random.Generator | None = None) -> dict[str, float]:
        y = int(y)
        k = self._grid(y)
        p = self.pmf(k)
        c = np.cumsum(p)
        crps = float(np.sum((c - (k >= y)) ** 2))
        logs = -self.logpmf(y)
        p0 = float(p[0])
        brier = float(((1 - p0) - (y > 0)) ** 2)
        lo = int(k[np.searchsorted(c, 0.1)])
        hi = int(k[min(np.searchsorted(c, 0.9), len(k) - 1)])
        below = c[y - 1] if y > 0 else 0.0
        u = (rng or np.random.default_rng()).random()
        pit = float(below + u * p[y])
        return {
            "crps": crps, "logs": logs, "brier": brier, "in80": float(lo <= y <= hi),
            "pit": pit, "mean": self.mean, "p_pos": 1 - p0,
        }


def fit_alpha(y: np.ndarray, mu: np.ndarray, weights: np.ndarray | None = None) -> float:
    """Maximum-likelihood NB dispersion for fixed means."""
    y = np.asarray(y, dtype=float)
    mu = np.maximum(np.asarray(mu, dtype=float), MU_FLOOR)
    w = np.ones_like(y) if weights is None else np.asarray(weights, dtype=float)
    if len(y) == 0:
        return 1.0

    def nll(log_a: float) -> float:
        return -float(np.sum(w * nb(mu, np.exp(log_a)).logpmf(y)))

    res = minimize_scalar(nll, bounds=(np.log(1e-4), np.log(50.0)), method="bounded")
    return float(np.exp(res.x))
