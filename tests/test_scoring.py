import numpy as np
import pytest
from scipy import stats

from aegis.scoring import CountForecast, fit_alpha, nb


def sample_crps(samples: np.ndarray, y: float) -> float:
    """CRPS = E|X - y| - 0.5 E|X - X'| (Gneiting & Raftery 2007)."""
    a = np.abs(samples - y).mean()
    b = np.abs(samples[:, None] - samples[None, :]).mean()
    return a - 0.5 * b


@pytest.mark.parametrize("mu,alpha,y", [(3.0, 0.5, 0), (3.0, 0.5, 7), (40.0, 0.2, 35), (0.2, 1.0, 1)])
def test_crps_matches_sample_estimate(mu, alpha, y):
    fc = CountForecast.point(mu, alpha)
    rng = np.random.default_rng(1)
    n = 1 / alpha
    draws = rng.negative_binomial(n, n / (n + mu), size=3000).astype(float)
    assert fc.score(y)["crps"] == pytest.approx(sample_crps(draws, y), rel=0.08, abs=0.02)


def test_log_score_is_negative_log_pmf():
    fc = CountForecast.point(5.0, 0.3)
    assert fc.score(4)["logs"] == pytest.approx(-nb(5.0, 0.3).logpmf(4))


def test_mixture_mean_and_ppos():
    fc = CountForecast(np.array([1.0, 9.0]), 0.5)
    assert fc.mean == pytest.approx(5.0)
    p0 = 0.5 * (nb(1.0, 0.5).pmf(0) + nb(9.0, 0.5).pmf(0))
    assert fc.p_positive() == pytest.approx(1 - p0)


def test_perfect_forecast_beats_wrong_one():
    good, bad = CountForecast.point(10, 0.1), CountForecast.point(60, 0.1)
    assert good.score(10)["crps"] < bad.score(10)["crps"]
    assert good.score(10)["logs"] < bad.score(10)["logs"]


def test_fit_alpha_recovers_dispersion():
    rng = np.random.default_rng(0)
    mu = rng.uniform(1, 50, size=4000)
    alpha = 0.4
    n = 1 / alpha
    y = rng.negative_binomial(n, n / (n + mu))
    assert fit_alpha(y, mu) == pytest.approx(alpha, rel=0.15)


def test_interval_coverage_is_calibrated():
    rng = np.random.default_rng(3)
    fc = CountForecast.point(12.0, 0.3)
    n = 1 / 0.3
    ys = rng.negative_binomial(n, n / (n + 12.0), size=800)
    cov = np.mean([fc.score(int(y), rng)["in80"] for y in ys])
    # discrete intervals are conservative, so coverage is at least nominal
    assert 0.78 <= cov <= 0.93
