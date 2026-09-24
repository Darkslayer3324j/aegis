"""First-level administrative units (provinces) for every country.

Events are assigned to provinces **by location**: the province polygon, within the
event's own country, that contains its coordinates. Spellings differ between UCDP and any
boundary dataset, so name matching is avoided. Rules:

* only events geolocated at first-order-admin precision or better (UCDP ``where_prec``
  <= 4) are assigned. Coarser ones (country-level, international waters) go to
  "<country>: province not recorded", never guessed;
* a precise point just outside every polygon of its country (coastline simplification)
  goes to the nearest province centroid of that country;
* boundaries: Natural Earth 1:10m admin-1 (public domain).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from . import config

ADMIN1_FILE = "ne_10m_admin_1_states_provinces.geojson"
ADMIN1_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
              + ADMIN1_FILE)
SIMPLIFIED_FILE = "admin1_simplified.geojson"
SIMPLIFY_DEG = 0.01           # ~1 km; for display and assignment alike
UID_BASE = 100_000            # province ids: UID_BASE + index in the admin-1 file
UNASSIGNED_BASE = 900_000     # "<country>: province not recorded": UNASSIGNED_BASE + UCDP id
MAX_WHERE_PREC = 4            # UCDP: 1 exact .. 4 first-order admin; 5+ too coarse


def ensure_admin1() -> Path:
    path = config.GEO / ADMIN1_FILE
    if not path.exists():
        import httpx

        config.GEO.mkdir(parents=True, exist_ok=True)
        r = httpx.get(ADMIN1_URL, timeout=300, follow_redirects=True)
        r.raise_for_status()
        path.write_bytes(r.content)
    return path


def _dp(points: np.ndarray, tol: float) -> np.ndarray:
    """Douglas-Peucker simplification of one ring (iterative)."""
    n = len(points)
    if n < 5:
        return points
    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        seg = points[b] - points[a]
        norm = np.hypot(*seg)
        rel = points[a + 1:b] - points[a]
        d = np.abs(seg[0] * rel[:, 1] - seg[1] * rel[:, 0]) / norm if norm > 0 else np.hypot(rel[:, 0], rel[:, 1])
        i = int(np.argmax(d))
        if d[i] > tol:
            k = a + 1 + i
            keep[k] = True
            stack += [(a, k), (k, b)]
    out = points[keep]
    return out if len(out) >= 4 else points


def _polys(geom: dict) -> list[list[np.ndarray]]:
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    return [[np.asarray(r, dtype=float) for r in p] for p in polys]


def _clean(name: str) -> str:
    return re.sub(r"\s+", " ", str(name)).strip()


@lru_cache(maxsize=1)
def admin1() -> dict:
    """Simplified provinces: {uid: {name, admin, polys: [[ring,...],...], bbox, centroid}}.

    Also writes the simplified GeoJSON served to the browser (once).
    """
    src = ensure_admin1()
    cache = config.GEO / SIMPLIFIED_FILE
    g = json.loads(src.read_text(encoding="utf-8"))
    units, features = {}, []
    for i, f in enumerate(g["features"]):
        p = f["properties"]
        if not f.get("geometry"):
            continue
        uid = UID_BASE + i
        name = _clean(p.get("name_en") or p.get("name") or p.get("adm1_code"))
        polys = [[_dp(r, SIMPLIFY_DEG) for r in poly] for poly in _polys(f["geometry"])]
        allpts = np.vstack([poly[0] for poly in polys])
        units[uid] = {"name": name, "admin": p["admin"], "polys": polys,
                      "bbox": (allpts[:, 0].min(), allpts[:, 0].max(), allpts[:, 1].min(), allpts[:, 1].max()),
                      "centroid": allpts.mean(axis=0)}
        features.append({"type": "Feature", "properties": {"uid": uid, "name": name, "admin": p["admin"]},
                         "geometry": {"type": "MultiPolygon",
                                      "coordinates": [[np.round(r, 4).tolist() for r in poly] for poly in polys]}})
    if not cache.exists():
        cache.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    return units


def _inside(x: np.ndarray, y: np.ndarray, ring: np.ndarray) -> np.ndarray:
    """Vectorised even-odd ray casting."""
    xi, yi = ring[:-1, 0], ring[:-1, 1]
    xj, yj = ring[1:, 0], ring[1:, 1]
    inside = np.zeros(len(x), dtype=bool)
    for a, b, c, d in zip(xi, yi, xj, yj):
        cross = ((b > y) != (d > y)) & (x < (c - a) * (y - b) / ((d - b) if d != b else 1e-12) + a)
        inside ^= cross
    return inside


def assign(lon, lat, admin_name: str | None, precise: np.ndarray) -> np.ndarray:
    """Province uid for each point of one country (0 where not assignable)."""
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    out = np.zeros(len(lon), dtype=np.int64)
    if admin_name is None or not len(lon):
        return out
    units = {u: v for u, v in admin1().items() if v["admin"] == admin_name}
    if not units:
        return out
    todo = precise & np.isfinite(lon) & np.isfinite(lat)
    for uid, u in units.items():
        x0, x1, y0, y1 = u["bbox"]
        cand = todo & (out == 0) & (lon >= x0) & (lon <= x1) & (lat >= y0) & (lat <= y1)
        if not cand.any():
            continue
        idx = np.flatnonzero(cand)
        hit = np.zeros(len(idx), dtype=bool)
        for poly in u["polys"]:
            inner = _inside(lon[idx], lat[idx], poly[0])
            for hole in poly[1:]:
                inner &= ~_inside(lon[idx], lat[idx], hole)
            hit |= inner
        out[idx[hit]] = uid
    # precise points that fell through a simplified coastline: nearest province centroid
    miss = np.flatnonzero(todo & (out == 0))
    if len(miss):
        uids = np.array(list(units))
        cents = np.array([units[u]["centroid"] for u in uids])
        d = (lon[miss, None] - cents[None, :, 0]) ** 2 + (lat[miss, None] - cents[None, :, 1]) ** 2
        out[miss] = uids[np.argmin(d, axis=1)]
    return out


def unitize(df: pd.DataFrame, admin_of: dict[str, str | None]) -> pd.DataFrame:
    """Relabel events so each province plays the role of a country (see vintage.to_units).

    ``df`` needs country_id, country, latitude, longitude, where_prec. ``admin_of`` maps a
    UCDP country name to its Natural Earth ``admin`` name.
    """
    out = df.copy()
    uid = np.zeros(len(out), dtype=np.int64)
    precise = pd.to_numeric(out["where_prec"], errors="coerce").fillna(99).to_numpy() <= MAX_WHERE_PREC
    for country, idx in out.groupby("country").groups.items():
        pos = out.index.get_indexer(idx)
        # assign on unique coordinates only
        sub = out.iloc[pos]
        key = sub["longitude"].round(4).astype(str) + "," + sub["latitude"].round(4).astype(str) + "," + precise[pos].astype(str)
        uniq = ~key.duplicated()
        u_pos = pos[uniq.to_numpy()]
        res = assign(out["longitude"].to_numpy()[u_pos], out["latitude"].to_numpy()[u_pos],
                     admin_of.get(country), precise[u_pos])
        lookup = dict(zip(key[uniq].to_numpy(), res))
        uid[pos] = key.map(lookup).to_numpy()
    units = admin1()
    unassigned = uid == 0
    uid[unassigned] = UNASSIGNED_BASE + out["country_id"].to_numpy()[unassigned]
    names = np.where(unassigned, out["country"].astype(str) + ": province not recorded",
                     [units[u]["name"] if u in units else "" for u in uid])
    out["region"] = out["country"]
    out["country"] = names
    out["country_id"] = uid
    return out.drop(columns=["where_prec"])
