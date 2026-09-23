import numpy as np
import pandas as pd

from aegis import observation as ob
from aegis.models import NBAR, features
from conftest import m


def test_training_pairs_only_use_finals_public_at_origin(store):
    hist = ob.build_history(store, store.origins())
    # Before final 25.1 exists, no 2024 month can be a training pair.
    pairs, final = ob.training_pairs(hist, store, pd.Timestamp("2025-05-31"), "events")
    assert final == "final-24.1"
    assert pairs.empty or pairs["m"].max() <= m("2023-12")
    # After it appears, January 2024 pairs use its truth (4 events).
    pairs, final = ob.training_pairs(hist, store, pd.Timestamp("2025-06-02"), "events")
    assert final == "final-25.1"
    jan = pairs[(pairs["m"] == m("2024-01")) & (pairs["country_id"] == 1)]
    assert set(jan["final"]) == {4}
    # January was seen at age 1 with 2 events, age 2 with 3, age 4 with 2 (after revision)
    seen = jan.set_index("age")["obs"].to_dict()
    assert seen[1] == 2 and seen[2] == 3


def test_history_skips_months_no_release_covered():
    """Regression: months before any Candidate coverage must not look like '0 reported'."""
    from aegis.vintage import ReleaseMeta, VintageStore
    from conftest import ev

    releases = [
        ReleaseMeta("cand-m-24.01", "monthly", pd.Timestamp("2024-02-20"), m("2024-01"), m("2024-01")),
        ReleaseMeta("final-25.1", "final", pd.Timestamp("2025-06-01"), m("1989-01"), m("2024-12")),
    ]
    rows = [ev(1, "2024-01-05", release="cand-m-24.01"),
            *[ev(10 + k, "2023-11-05", release="final-25.1") for k in range(50)]]
    s = VintageStore(pd.DataFrame(rows), releases)
    hist = ob.build_history(s, s.origins())
    assert hist["m"].min() == m("2024-01")  # Nov 2023 was covered by nothing at that origin


def test_completeness_below_one_when_reports_lag(store):
    hist = ob.build_history(store, store.origins())
    model = ob.fit(hist, store, pd.Timestamp("2025-06-02"))
    assert model.C(1, 1) < 1.0
    # a nowcast of an under-reported month is above the raw count
    assert model.nowcast(1, 1, 2).mean > 2


def test_nbar_scales_proportionally_for_large_counts():
    rng = np.random.default_rng(0)
    level = rng.uniform(0, 30, size=(80, 1))
    Y = rng.poisson(np.repeat(level, 51, axis=1)).astype(float)
    model = NBAR.fit(Y, 1)
    big = np.full((1, 51), 1000.0)
    bigger = np.full((1, 51), 2000.0)
    r = model.mean(features(bigger, 50))[0] / model.mean(features(big, 50))[0]
    assert 1.9 < r < 2.1  # anchored model: doubling the level doubles the forecast
