"""The SCOPE.md wording rules, enforced."""

import itertools
import re

import pandas as pd
import pytest

from aegis import config
from aegis.evidence import BANNED, FOOTER, build


def row(**kw) -> pd.Series:
    base = dict(country_id=1, country="Testland", region="R", obs_last=12, nowcast_last=15.0,
                nowcast_lo=10, nowcast_hi=21, C1=0.8, C2=0.85, C3=0.9, volatility=0.3,
                activity12=14.0, dark=False, status="OK",
                aegis_h1=16.0, aegis_h1_lo=8, aegis_h1_hi=27, aegis_h1_ppos=0.99,
                aegis_h2=16.5, aegis_h3=17.0, base_h1=12.0)
    base.update(kw)
    return pd.Series(base)


def series(values) -> pd.DataFrame:
    months = pd.period_range("2024-09", periods=len(values), freq="M").astype(str)
    return pd.DataFrame({"m": months, "observed": values, "nowcast": values, "is_final": False})


CASES = {
    "ok": row(),
    "warn_low_visibility": row(status="WARN", C1=0.6, volatility=1.4),
    "abstain": row(status="ABSTAIN", C1=0.3),
    "silent_feed": row(status="ABSTAIN", obs_last=0, dark=True, activity12=9.0),
    "over_reported": row(C1=1.8, aegis_h1=5.0, base_h1=9.0),
    "quiet": row(obs_last=0, nowcast_last=0.1, nowcast_lo=0, nowcast_hi=0, activity12=0.0,
                 aegis_h1=0.2, aegis_h1_lo=0, aegis_h1_hi=1, aegis_h2=0.2, aegis_h3=0.2, base_h1=0.1),
}
TRACKS = [None, pd.Series({"miss": 0.25, "n": 90, "nbar": 3.1, "nbar+vis": 2.9})]


@pytest.mark.parametrize("case,track", list(itertools.product(CASES, range(len(TRACKS)))))
def test_wording_rules(case, track):
    r = CASES[case]
    vals = [0] * 24 if case == "quiet" else [14] * 21 + [15, 16, 12]
    ev = build(r, series(vals), TRACKS[track])
    body = " ".join([ev.headline] + [s for _, s in ev.points])

    assert not BANNED.search(body), BANNED.search(body).group(0)   # evidence, not danger
    assert ev.points[0][0] == "Visibility"                           # visibility first
    assert ev.footer == FOOTER and "Not travel or security advice" in ev.text()
    if r["status"] == "ABSTAIN":                                     # no number when abstaining
        assert not ev.shows_number
        assert not re.search(r"\d", ev.headline)
        assert not any(label in ("Newest month", "Correction", "Further ahead") for label, _ in ev.points)
    else:
        assert "80% range" in ev.headline


def test_quiet_countries_are_never_reassured():
    ev = build(CASES["quiet"], series([0] * 24))
    text = ev.text()
    assert "not evidence that nothing is happening" in text


def test_silent_feed_is_explained():
    ev = build(CASES["silent_feed"], series([9] * 23 + [0]))
    assert any(label == "Silent feed" and "quiet feed is not a quiet world" in s for label, s in ev.points)


def test_track_record_reported():
    ev = build(CASES["ok"], series([14] * 24), TRACKS[1])
    rec = dict(ev.points)["Track record"]
    assert "25%" in rec and "90 forecasts" in rec and "more accurate" in rec


@pytest.mark.skipif(not (config.RESULTS / "live" / "countries.parquet").exists(), reason="no live forecast")
def test_every_live_country_obeys_the_rules():
    from aegis import live

    state = live.load()
    for _, r in state.countries.iterrows():
        s = state.series[state.series["country_id"] == r["country_id"]]
        ev = build(r, s)
        body = " ".join([ev.headline] + [x for _, x in ev.points])
        assert not BANNED.search(body), (r["country"], BANNED.search(body).group(0))
        if r["status"] == "ABSTAIN":
            assert not re.search(r"\d", ev.headline), r["country"]
