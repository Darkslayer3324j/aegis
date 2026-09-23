import numpy as np
import pandas as pd

from conftest import m


def ids(snap, month):
    return sorted(snap[snap["m"] == m(month)]["id"].tolist())


def test_nothing_from_the_future(store):
    snap = store.snapshot("2024-03-01")
    assert set(snap["release"]) <= {"final-24.1", "cand-m-24.01"}
    assert ids(snap, "2024-01") == [10, 11]
    assert ids(snap, "2024-02") == []


def test_late_additions_arrive_with_later_monthly_release(store):
    assert ids(store.snapshot("2024-03-25"), "2024-01") == [10, 11, 12]


def test_cumulative_release_revises_and_removes(store):
    snap = store.snapshot("2024-05-15")
    assert ids(snap, "2024-01") == [10, 12]          # event 11 removed by the revision
    assert ids(snap, "2024-03") == [30, 31]


def test_monthly_after_cumulative_still_adds(store):
    assert ids(store.snapshot("2024-05-25"), "2024-03") == [30, 31, 32]


def test_final_is_authoritative_once_available(store):
    before = store.snapshot("2025-05-31")
    after = store.snapshot("2025-06-01")
    assert ids(before, "2023-12") == [1, 2]
    assert ids(after, "2023-12") == [200, 201, 202]
    assert ids(after, "2024-01") == [100, 101, 102, 103]
    assert after[after["m"] == m("2024-01")]["is_final"].all()


def test_panel_fills_zero_months_and_flags_final(store):
    p = store.panel("2024-05-25", m("2023-12"), m("2024-04"), countries=np.array([1, 2]))
    assert len(p) == 2 * 5
    c1 = p[p["country_id"] == 1].set_index("m")
    assert c1.loc[m("2023-12"), "is_final"] and not c1.loc[m("2024-01"), "is_final"]
    assert c1.loc[m("2024-01"), "events"] == 2
    assert p[p["country_id"] == 2]["events"].sum() == 0


def test_last_data_month_and_origins(store):
    assert store.last_data_month("2024-04-21") == m("2024-03")
    assert store.origins()[0] == pd.Timestamp("2024-02-20")
