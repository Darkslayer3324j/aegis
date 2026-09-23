"""Synthetic vintage store: small enough to reason about by hand."""

import pandas as pd
import pytest

from aegis.vintage import ReleaseMeta, VintageStore, month_index


def m(s: str) -> int:
    return month_index(pd.Period(s, "M"))


def ev(i, date, country=1, release="x", best=1):
    return {"id": i, "date_start": pd.Timestamp(date), "date_end": pd.Timestamp(date), "date_prec": 1,
            "country_id": country, "country": f"C{country}", "region": "R", "type_of_violence": 1,
            "best": best, "latitude": 0.0, "longitude": 0.0, "release": release}


@pytest.fixture
def store() -> VintageStore:
    releases = [
        ReleaseMeta("final-24.1", "final", pd.Timestamp("2024-01-15"), m("1989-01"), m("2023-12")),
        ReleaseMeta("cand-m-24.01", "monthly", pd.Timestamp("2024-02-20"), m("2024-01"), m("2024-01")),
        ReleaseMeta("cand-m-24.02", "monthly", pd.Timestamp("2024-03-20"), m("2024-02"), m("2024-02")),
        ReleaseMeta("cand-m-24.03", "monthly", pd.Timestamp("2024-04-20"), m("2024-03"), m("2024-03")),
        ReleaseMeta("cand-c-24.01-24.03", "cumulative", pd.Timestamp("2024-05-10"), m("2024-01"), m("2024-03")),
        ReleaseMeta("cand-m-24.04", "monthly", pd.Timestamp("2024-05-20"), m("2024-04"), m("2024-04")),
        ReleaseMeta("final-25.1", "final", pd.Timestamp("2025-06-01"), m("1989-01"), m("2024-12")),
    ]
    rows = [
        # final 24.1: December 2023 has 2 events
        ev(1, "2023-12-05", release="final-24.1"), ev(2, "2023-12-06", release="final-24.1"),
        # January 2024 first release: events 10, 11
        ev(10, "2024-01-03", release="cand-m-24.01"), ev(11, "2024-01-09", release="cand-m-24.01"),
        # February release adds Feb event 20 and a LATE January event 12
        ev(20, "2024-02-02", release="cand-m-24.02"), ev(12, "2024-01-20", release="cand-m-24.02"),
        ev(30, "2024-03-02", release="cand-m-24.03"),
        # quarterly revision: removes event 11, keeps 10, 12, 20, 30, adds 31
        ev(10, "2024-01-03", release="cand-c-24.01-24.03"), ev(12, "2024-01-20", release="cand-c-24.01-24.03"),
        ev(20, "2024-02-02", release="cand-c-24.01-24.03"), ev(30, "2024-03-02", release="cand-c-24.01-24.03"),
        ev(31, "2024-03-15", release="cand-c-24.01-24.03"),
        # April release, plus a late March event after the quarterly file
        ev(40, "2024-04-02", release="cand-m-24.04"), ev(32, "2024-03-28", release="cand-m-24.04"),
        # final 25.1: January 2024 ends up with 4 events, Dec 2023 revised to 3
        *[ev(100 + k, "2024-01-10", release="final-25.1") for k in range(4)],
        *[ev(200 + k, "2023-12-10", release="final-25.1") for k in range(3)],
        ev(20, "2024-02-02", release="final-25.1"),
        ev(30, "2024-03-02", release="final-25.1"), ev(31, "2024-03-15", release="final-25.1"),
        ev(32, "2024-03-28", release="final-25.1"), ev(40, "2024-04-02", release="final-25.1"),
    ]
    return VintageStore(pd.DataFrame(rows), releases)
