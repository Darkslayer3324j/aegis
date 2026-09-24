"""Reconstruct what was known at any moment from the immutable release store.

Rules for ``snapshot(asof)``:

1. Take the latest *final* GED release available at ``asof``. It is authoritative for
   every month it covers.
2. For each later month, take the latest *cumulative* Candidate release available at
   ``asof`` that covers the month. A cumulative release is a revision: it replaces the
   monthly releases that came before it (events can be removed as well as added).
3. Add events for that month from *monthly* releases published after that cumulative
   release (late additions arrive in later monthly files).
4. If the same event id appears in several releases, keep the latest one.

Nothing published after ``asof`` is ever read. The tests in ``tests/test_vintage.py``
enforce this.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from functools import cached_property

import numpy as np
import pandas as pd

from . import config

Date = dt.date | str | pd.Timestamp


def _ts(d: Date) -> pd.Timestamp:
    return pd.Timestamp(d).normalize()


def month_index(p: pd.Period | pd.Series) -> int | pd.Series:
    """Integer month counter so month arithmetic is plain integer arithmetic."""
    if isinstance(p, pd.Series):
        return p.dt.year * 12 + p.dt.month - 1
    return p.year * 12 + p.month - 1


def month_from_index(i: int) -> pd.Period:
    return pd.Period(year=i // 12, month=i % 12 + 1, freq="M")


def to_units(df: pd.DataFrame, scope: str) -> pd.DataFrame:
    """Relabel a national scope's events so that each province plays the role of a country."""
    spec = config.SCOPES[scope]
    adm = df["adm_1"].fillna("").str.lower()
    uid = pd.Series(spec["unassigned"][0], index=df.index)
    name = pd.Series(spec["unassigned"][1], index=df.index)
    for unit_id, unit_name, keys in spec["units"]:
        hit = adm.str.contains("|".join(keys), regex=True) & (uid == spec["unassigned"][0])
        uid[hit], name[hit] = unit_id, unit_name
    out = df.drop(columns=["adm_1"]).copy()
    out["country_id"], out["country"], out["region"] = uid.astype(int), name, spec["title"]
    return out


@dataclass
class ReleaseMeta:
    name: str
    kind: str
    available: pd.Timestamp
    cover_start: int  # month index
    cover_end: int


class VintageStore:
    """All releases held in memory with their availability dates."""

    def __init__(self, events: pd.DataFrame, releases: list[ReleaseMeta]):
        self.releases = sorted(releases, key=lambda r: (r.available, r.name))
        self.meta = {r.name: r for r in self.releases}
        ev = events.copy()
        ev["m"] = month_index(ev["date_start"].dt.to_period("M")).astype(int)
        ev["available"] = ev["release"].map({r.name: r.available for r in releases})
        ev["kind"] = ev["release"].map({r.name: r.kind for r in releases})
        self.events = ev

    # ------------------------------------------------------------------ loading
    @classmethod
    def load(cls, scope: str = "world") -> "VintageStore":
        """All releases for a scope. A national scope's "countries" are its provinces."""
        if not config.MANIFEST.exists():
            raise FileNotFoundError("No vintage store yet. Run `aegis sync` first.")
        rows = json.loads(config.MANIFEST.read_text(encoding="utf-8"))
        store_dir = config.scope_store(scope)
        if scope != "world" and not all((store_dir / r["store_file"]).exists() for r in rows):
            from .ingest import build_scope_store
            build_scope_store(scope)
        releases, frames = [], []
        for r in rows:
            meta = ReleaseMeta(
                name=r["name"], kind=r["kind"], available=_ts(r["available"]),
                cover_start=month_index(pd.Period(r["cover_start"], "M")),
                cover_end=month_index(pd.Period(r["cover_end"], "M")),
            )
            df = pd.read_parquet(store_dir / r["store_file"])
            if scope != "world":
                df = to_units(df, scope)
            if meta.kind == "final":
                # Finals carry 35+ years of history; AEGIS only needs recent years.
                df = df[df["date_start"] >= "2015-01-01"]
            df["release"] = meta.name
            releases.append(meta)
            frames.append(df)
        return cls(pd.concat(frames, ignore_index=True), releases)

    # ------------------------------------------------------------------ queries
    def available(self, asof: Date, kind: str | None = None) -> list[ReleaseMeta]:
        t = _ts(asof)
        return [r for r in self.releases if r.available <= t and (kind is None or r.kind == kind)]

    def latest_final(self, asof: Date) -> ReleaseMeta | None:
        finals = self.available(asof, "final")
        return finals[-1] if finals else None

    def covered(self, asof: Date, months: np.ndarray) -> np.ndarray:
        """Which of ``months`` some release available at ``asof`` actually covers.

        An uncovered month is *unknown*, not zero. It arises before the first Candidate
        release, or when a release is dated late (e.g. a re-upload).
        """
        months = np.asarray(months)
        ok = np.zeros(len(months), dtype=bool)
        for r in self.available(asof):
            ok |= (months >= r.cover_start) & (months <= r.cover_end)
        return ok

    def last_data_month(self, asof: Date) -> int | None:
        """Most recent month with a monthly Candidate release available at ``asof``."""
        monthly = self.available(asof, "monthly")
        return max(r.cover_end for r in monthly) if monthly else None

    def snapshot(self, asof: Date, candidates_only: bool = False) -> pd.DataFrame:
        """Events as known at ``asof``, one row per event, with an ``is_final`` flag."""
        t = _ts(asof)
        final = None if candidates_only else self.latest_final(t)
        ev = self.events[self.events["available"] <= t]
        parts = []
        final_end = -1
        if final is not None:
            f = ev[ev["release"] == final.name]
            final_end = final.cover_end
            parts.append(f[f["m"] <= final_end].assign(is_final=True))

        cand = ev[(ev["kind"] != "final") & (ev["m"] > final_end)]
        if not cand.empty:
            cums = [r for r in self.available(t, "cumulative")]
            months = cand["m"].unique()
            best_cum: dict[int, ReleaseMeta] = {}
            for m in months:
                cover = [r for r in cums if r.cover_start <= m <= r.cover_end]
                if cover:
                    best_cum[m] = max(cover, key=lambda r: (r.available, r.name))
            cum_name = cand["m"].map({m: r.name for m, r in best_cum.items()})
            cum_date = pd.to_datetime(cand["m"].map({m: r.available for m, r in best_cum.items()}))
            cum_date = cum_date.where(cum_date.notna(), pd.Timestamp.min)
            keep_cum = (cand["kind"] == "cumulative") & (cand["release"] == cum_name)
            keep_mon = (cand["kind"] == "monthly") & (cand["available"] > cum_date)
            c = cand[keep_cum | keep_mon].sort_values(["available", "release"])
            c = c.drop_duplicates("id", keep="last")
            parts.append(c.assign(is_final=False))
        if not parts:
            return ev.iloc[0:0].assign(is_final=pd.Series(dtype=bool))
        return pd.concat(parts, ignore_index=True)

    # ------------------------------------------------------------------ panels
    def countries_at(self, asof: Date) -> np.ndarray:
        """The forecasting universe at ``asof``: every country (or unit) with at least one
        event in some release available by then.

        The roster must be origin-aware. Taking it from the whole store would let a country
        that first appears in a later release enter earlier forecasts, the historical
        training panel and the observation model (found in external review, 24 Sep 2026).
        """
        ev = self.events[self.events["available"] <= _ts(asof)]
        return np.sort(ev["country_id"].unique())

    @cached_property
    def countries(self) -> pd.DataFrame:
        """Country id -> name/region, for display only. Never use it as a roster: it spans
        every release, including ones after any given origin. Use ``countries_at``."""
        c = (self.events.sort_values("available")
             .drop_duplicates("country_id", keep="last")[["country_id", "country", "region"]])
        return c.set_index("country_id").sort_index()

    def panel(self, asof: Date, first_month: int, last_month: int,
              countries: np.ndarray | None = None, candidates_only: bool = False) -> pd.DataFrame:
        """Country x month counts known at ``asof``.

        Columns: country_id, m, events, deaths, is_final. Zero rows are filled in so that
        a quiet month is explicit.
        """
        snap = self.snapshot(asof, candidates_only=candidates_only)
        snap = snap[(snap["m"] >= first_month) & (snap["m"] <= last_month)]
        agg = snap.groupby(["country_id", "m"]).agg(
            events=("id", "size"), deaths=("best", "sum"), is_final=("is_final", "max")
        )
        if countries is None:
            countries = self.countries_at(asof)
        full = pd.MultiIndex.from_product(
            [countries, np.arange(first_month, last_month + 1)], names=["country_id", "m"]
        )
        out = agg.reindex(full)
        final = self.latest_final(asof) if not candidates_only else None
        final_end = final.cover_end if final else -1
        out["is_final"] = full.get_level_values("m") <= final_end
        out[["events", "deaths"]] = out[["events", "deaths"]].fillna(0).astype(int)
        return out.reset_index()

    def truth(self, final_name: str | None = None) -> pd.DataFrame:
        """Country x month counts from one final release (default: the newest one)."""
        finals = [r for r in self.releases if r.kind == "final"]
        rel = self.meta[final_name] if final_name else finals[-1]
        ev = self.events[self.events["release"] == rel.name]
        agg = ev.groupby(["country_id", "m"]).agg(events=("id", "size"), deaths=("best", "sum"))
        return agg, rel

    # ------------------------------------------------------------------ origins
    def origins(self, start: Date | None = None, end: Date | None = None) -> list[pd.Timestamp]:
        """Forecast origins: the dates on which a new monthly release became available."""
        dates = sorted({r.available for r in self.releases if r.kind == "monthly"})
        if start is not None:
            dates = [d for d in dates if d >= _ts(start)]
        if end is not None:
            dates = [d for d in dates if d <= _ts(end)]
        return dates
