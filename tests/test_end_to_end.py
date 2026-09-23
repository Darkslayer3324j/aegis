"""End-to-end invariants that the unit tests cannot see on their own."""

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from aegis import ingest
from aegis import observation as ob
from aegis.backtest import block_bootstrap
from aegis.pipeline import CoverageGap, run_origin
from aegis.scoring import CountForecast
from aegis.vintage import ReleaseMeta, VintageStore, month_from_index, month_index
from conftest import ev, m


def synthetic_store(seed: int = 0, extra_future: bool = False) -> VintageStore:
    """Three countries, 2016–2023. Monthly Candidate releases (2021+) report ~80% of a
    month's events at first and the rest a month later; yearly finals report everything."""
    rng = np.random.default_rng(seed)
    rates = {1: 20.0, 2: 5.0, 3: 0.5}
    rows, releases = [], []
    eid = 0
    events = []  # (id, date, country)
    for mi in range(m("2016-01"), m("2023-12") + 1):
        p = month_from_index(mi)
        for c, lam in rates.items():
            for _ in range(rng.poisson(lam)):
                eid += 1
                events.append((eid, pd.Timestamp(p.year, p.month, 10), c))
    ev_df = pd.DataFrame(events, columns=["id", "date", "country"])
    ev_df["mi"] = month_index(ev_df["date"].dt.to_period("M"))
    ev_df["late"] = rng.random(len(ev_df)) < 0.2

    for year in (2021, 2022, 2023):  # final YY.1 published in June, covers the year before
        name = f"final-{year - 2000}.1"
        releases.append(ReleaseMeta(name, "final", pd.Timestamp(f"{year}-06-01"), m("1989-01"), m(f"{year - 1}-12")))
        for r in ev_df[ev_df["mi"] <= m(f"{year - 1}-12")].itertuples():
            rows.append(ev(r.id, r.date, r.country, release=name))
    for mi in range(m("2021-01"), m("2023-06") + 1):
        p = month_from_index(mi)
        nxt = month_from_index(mi + 1)
        name = f"cand-m-{p.year - 2000:02d}.{p.month:02d}"
        releases.append(ReleaseMeta(name, "monthly", pd.Timestamp(nxt.year, nxt.month, 20), mi, mi))
        now = ev_df[(ev_df["mi"] == mi) & ~ev_df["late"]]
        late = ev_df[(ev_df["mi"] == mi - 1) & ev_df["late"]]
        for r in pd.concat([now, late]).itertuples():
            rows.append(ev(r.id, r.date, r.country, release=name))

    if extra_future:
        # A wild revision and a future final, both published after the test origin.
        releases.append(ReleaseMeta("cand-c-23.01-23.03", "cumulative", pd.Timestamp("2023-04-25"),
                                    m("2023-01"), m("2023-03")))
        rows += [ev(10_000_000 + k, "2023-01-15", 1, release="cand-c-23.01-23.03") for k in range(900)]
        releases.append(ReleaseMeta("final-24.1", "final", pd.Timestamp("2024-06-01"), m("1989-01"), m("2023-12")))
        rows += [ev(20_000_000 + k, "2022-11-15", 2, release="final-24.1") for k in range(700)]
    return VintageStore(pd.DataFrame(rows), releases)


def truncated(store: VintageStore, asof: pd.Timestamp) -> VintageStore:
    """The store as it would have existed on ``asof``: later releases simply absent."""
    keep = [r for r in store.releases if r.available <= asof]
    names = {r.name for r in keep}
    cols = ["id", "date_start", "date_end", "date_prec", "country_id", "country", "region",
            "type_of_violence", "best", "latitude", "longitude", "release"]
    return VintageStore(store.events[store.events["release"].isin(names)][cols], keep)


def test_future_releases_cannot_change_an_earlier_forecast():
    """Store A holds only releases published by the origin; store B holds every release
    plus a wild future revision and a future final. The forecast must be identical."""
    origin = pd.Timestamp("2023-03-20")
    full = synthetic_store(extra_future=True)
    runs = []
    for store in (truncated(full, origin), full):
        hist = ob.build_history(store, store.origins())
        runs.append(run_origin(store, hist, origin, draws=20, seed=7))
    a, b = runs
    assert a.L == b.L == m("2023-02")
    np.testing.assert_array_equal(a.Y, b.Y)
    np.testing.assert_allclose(a.Y_vis, b.Y_vis)
    assert a.obs_model.n_pairs == b.obs_model.n_pairs
    pd.testing.assert_frame_equal(a.obs_model.completeness, b.obs_model.completeness)
    pd.testing.assert_frame_equal(a.status, b.status)
    for h in a.forecasts:
        for model in a.forecasts[h]:
            ma = [f.mean for f in a.forecasts[h][model]]
            mb = [f.mean for f in b.forecasts[h][model]]
            np.testing.assert_allclose(ma, mb, err_msg=f"{model} h={h} changed")


def test_synthetic_underreporting_is_detected():
    store = synthetic_store()
    hist = ob.build_history(store, store.origins())
    model = ob.fit(hist, store, pd.Timestamp("2023-06-10"))
    assert 0.7 < model.C(1, 1) < 0.9       # ~80% reported at first
    assert model.C(1, 2) > model.C(1, 1)   # late events arrive with the next release


def test_origin_with_uncovered_months_is_refused():
    store = synthetic_store()
    hist = ob.build_history(store, store.origins())
    # Remove one monthly release: its month is now unknown, not zero.
    store.releases = [r for r in store.releases if r.name != "cand-m-22.11"]
    with pytest.raises(CoverageGap):
        run_origin(store, hist, pd.Timestamp("2023-03-20"), draws=5)


def test_late_reupload_is_never_backdated():
    rel = ingest.parse_release("candidateged/GEDEvent_v22_0_6.csv")
    lm = dt.datetime(2022, 12, 20, tzinfo=dt.timezone.utc)
    available, source = ingest.resolve_available(rel, lm)
    assert available == "2022-12-20" and source == "last-modified-late"
    on_time = dt.datetime(2022, 7, 19, tzinfo=dt.timezone.utc)
    assert ingest.resolve_available(rel, on_time) == ("2022-07-19", "last-modified")
    assert ingest.resolve_available(rel, None)[1] == "rule-unverified"


def test_log_score_has_no_floor():
    near = CountForecast.point(2.0, 0.05).score(60)["logs"]
    far = CountForecast.point(2.0, 0.05).score(400)["logs"]
    assert far > near > 27.7  # the old 1e-12 floor capped both at 27.63


def test_block_bootstrap_widens_with_autocorrelation():
    rng = np.random.default_rng(0)
    n = 60
    ar = np.zeros(n)
    for t in range(1, n):
        ar[t] = 0.9 * ar[t - 1] + rng.normal()
    per = pd.DataFrame({"sum": ar, "count": np.ones(n)}, index=range(n))
    w1 = np.ptp(np.quantile(block_bootstrap(per, 1), [0.025, 0.975]))
    w6 = np.ptp(np.quantile(block_bootstrap(per, 6), [0.025, 0.975]))
    assert w6 > 1.3 * w1
