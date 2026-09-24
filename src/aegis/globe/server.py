"""`aegis globe`: a local map of the same forecasts the terminal interface shows.

Zoomed out it is a 3D globe of countries. Zoom in and it shows every country's provinces;
zoom further and the base map shows terrain and 3D buildings (OpenFreeMap / OpenStreetMap
and open terrain tiles, fetched by the browser). Offline, the base map falls back to AEGIS's
own country shapes.

Served from this machine only (127.0.0.1). What the browser receives from AEGIS follows
SCOPE.md:

* forecasts and visibility per country and per province (first-level unit), nothing finer;
* recorded events **aggregated into roughly 0.5° cells** (about 55 km). Individual event
  coordinates, sources and actors never leave the server;
* the same template-generated evidence summaries as `aegis explain` (no actors named).

The detailed base map (streets, buildings, terrain) is public map data, not AEGIS data.
"""

from __future__ import annotations

import gzip
import json
import re
import threading
import webbrowser
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

from .. import config, evidence, live

STATIC = Path(__file__).resolve().parent / "static"
STATIC_TYPES = {"maplibre-gl.js": "text/javascript", "maplibre-gl.css": "text/css"}
CELL_DEG = 0.5
WORLD_POLYGONS = "ne_110m_admin_0_countries.geojson"
NATURAL_EARTH_COUNTRIES = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
    "ne_110m_admin_0_countries.geojson"
)
MAP_SCOPES = ("world", "provinces")  # what the map shows; national scopes remain for the CLI/TUI
# UCDP names that the normaliser below cannot match to Natural Earth on its own.
ALIASES = {
    "drcongo": "Democratic Republic of the Congo",
    "bosniaherzegovina": "Bosnia and Herzegovina",
    "antiguabarbuda": "Antigua and Barbuda",
}
PAK_ALIASES = {"Islamabad": "Islamabad Capital Territory"}


# --------------------------------------------------------------------------- geometry
def _signed_area(ring) -> float:
    return sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1)) / 2


def rewind(geojson: dict, clockwise: bool = False) -> dict:
    """Make ring orientation consistent: outer rings counter-clockwise and holes clockwise
    (RFC 7946, which MapLibre uses), or the reverse when ``clockwise`` is set (d3-geo)."""
    def fix(poly):
        out = []
        for i, ring in enumerate(poly):
            cw = _signed_area(ring) < 0
            want_cw = clockwise if i == 0 else not clockwise
            out.append(ring if cw == want_cw else ring[::-1])
        return out
    for f in geojson["features"]:
        g = f.get("geometry") or {}
        if g.get("type") == "Polygon":
            g["coordinates"] = fix(g["coordinates"])
        elif g.get("type") == "MultiPolygon":
            g["coordinates"] = [fix(p) for p in g["coordinates"]]
    return geojson


@lru_cache(maxsize=8)
def geo_bytes(name: str) -> bytes:
    if name == WORLD_POLYGONS:
        ensure_polygons()
    elif name == config.SCOPES["provinces"]["boundaries"]:
        from .. import geo
        geo.admin1()  # writes the simplified file on first use
    return gzip.compress(json.dumps(rewind(json.loads((config.GEO / name).read_text(encoding="utf-8")))).encode(), 6)


def _norm(name: str) -> str:
    return re.sub(r"[^a-z]", "", re.sub(r"\(.*?\)", "", str(name)).lower())


def ensure_polygons() -> Path:
    path = config.GEO / WORLD_POLYGONS
    if not path.exists():
        import httpx

        r = httpx.get(NATURAL_EARTH_COUNTRIES, timeout=120, follow_redirects=True)
        r.raise_for_status()
        config.GEO.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
    return path


@lru_cache(maxsize=4)
def _world_name_index() -> dict[str, str]:
    g = json.loads(ensure_polygons().read_text(encoding="utf-8"))
    idx: dict[str, str] = {}
    for f in g["features"]:
        p = f["properties"]
        for key in ("ADMIN", "NAME", "NAME_LONG", "SOVEREIGNT", "FORMAL_EN"):
            if p.get(key):
                idx.setdefault(_norm(p[key]), p["ADMIN"])
    return idx


def geo_key(scope: str, name: str, unit_id: int | None = None):
    """The polygon a unit is drawn with, or None if the map has no shape for it."""
    if scope == "world":
        n = _norm(name)
        return ALIASES.get(n) or _world_name_index().get(n)
    if scope == "pakistan":
        return PAK_ALIASES.get(name, name)
    if scope == "provinces":
        from ..geo import UNASSIGNED_BASE
        return int(unit_id) if unit_id is not None and unit_id < UNASSIGNED_BASE else None
    return None


# --------------------------------------------------------------------------- data
def _cells(events: pd.DataFrame) -> list[dict]:
    """Recorded events aggregated to CELL_DEG cells: centre and count."""
    e = events.dropna(subset=["latitude", "longitude"])
    if e.empty:
        return []
    lat = (np.floor(e["latitude"] / CELL_DEG) + 0.5) * CELL_DEG
    lng = (np.floor(e["longitude"] / CELL_DEG) + 0.5) * CELL_DEG
    out = e.assign(lat=lat.round(3), lng=lng.round(3)).groupby(["lat", "lng"]).size().rename("n").reset_index()
    return [{"lat": float(r.lat), "lng": float(r.lng), "n": int(r.n)} for r in out.itertuples()]


def _state(scope: str) -> live.LiveState:
    stamp = (live.live_dir(scope) / "meta.json").stat().st_mtime_ns
    return _state_cached(scope, stamp)


@lru_cache(maxsize=8)
def _state_cached(scope: str, stamp: int) -> live.LiveState:
    return live.load(scope)


def _forecast(r) -> list[dict]:
    abstain = r["status"] == "ABSTAIN"
    return [{"h": h,
             "aegis": None if abstain else round(float(r[f"aegis_h{h}"]), 2),
             "lo": None if abstain else int(r[f"aegis_h{h}_lo"]),
             "hi": None if abstain else int(r[f"aegis_h{h}_hi"]),
             "base": round(float(r[f"base_h{h}"]), 2)} for h in (1, 2, 3)]


def payload(scope: str) -> dict:
    """Light summary of every unit, plus aggregated event cells and the backtest verdict."""
    state = _state(scope)
    spec = config.SCOPES[scope]
    units = []
    for _, r in state.countries.iterrows():
        cid = int(r["country_id"])
        units.append({
            "id": cid, "name": r["country"], "region": r["region"], "geo": geo_key(scope, r["country"], cid),
            "status": r["status"], "C1": round(float(r["C1"]), 3), "dark": bool(r["dark"]),
            "activity12": round(float(r["activity12"]), 2), "obs_last": int(r["obs_last"]),
            "forecast": _forecast(r),
        })
    bt = None
    if state.backtest:
        p2 = state.backtest["paper2_visibility"]
        d = p2["primary_active_crps"]
        bt = {"diff": d.get("mean_diff"), "ci": d.get("ci95"),
              "selected_candidate": state.backtest.get("candidates", {}).get("selected"),
              "origins": state.backtest["meta"].get("origins_scored")}
    return {
        "scope": scope, "title": spec["title"], "unit": spec["unit"],
        "polygons": f"/geo/{spec.get('boundaries', WORLD_POLYGONS)}",
        "polygon_key": spec.get("polygon_key", "ADMIN" if scope == "world" else "shapeName"),
        "meta": state.meta, "backtest": bt, "units": units,
        "cells": _cells(state.events) if scope == "world" else [], "cell_deg": CELL_DEG,
        "footer": evidence.FOOTER,
    }


def detail(scope: str, unit_id: int) -> dict | None:
    """Everything the side panel shows for one unit."""
    state = _state(scope)
    hit = state.countries[state.countries["country_id"] == unit_id]
    if hit.empty:
        return None
    r = hit.iloc[0]
    s = state.series[state.series["country_id"] == unit_id]
    track = None
    if state.backtest_by_country is not None and unit_id in state.backtest_by_country.index:
        track = state.backtest_by_country.loc[unit_id]
    comp = None
    if "type_of_violence" in state.events:
        e = state.events[state.events["country_id"] == unit_id]
        comp = e["type_of_violence"].value_counts().astype(int).to_dict()
    ev = evidence.build(r, s, track, comp)
    return {
        "id": unit_id, "scope": scope, "name": r["country"], "region": r["region"], "status": r["status"],
        "C1": round(float(r["C1"]), 3), "activity12": round(float(r["activity12"]), 2),
        "forecast": _forecast(r),
        "series": [{"m": x.m, "obs": x.observed, "exp": round(x.nowcast, 2), "final": bool(x.is_final)}
                   for x in s.itertuples()],
        "evidence": {"headline": ev.headline, "points": ev.points, "footer": ev.footer,
                     "shows_number": ev.shows_number},
    }


# --------------------------------------------------------------------------- server
class Handler(BaseHTTPRequestHandler):
    server_version = "aegis-globe"

    def log_message(self, fmt, *args):  # quiet
        pass

    def _send(self, status: int, body: bytes, ctype: str, gzipped: bool = False) -> None:
        if gzipped and "gzip" not in (self.headers.get("Accept-Encoding") or ""):
            body, gzipped = gzip.decompress(body), False
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if gzipped:
            self.send_header("Content-Encoding", "gzip")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj) -> None:
        self._send(status, json.dumps(obj, default=float).encode(), "application/json")

    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        q = parse_qs(url.query)
        try:
            if url.path in ("/", "/index.html"):
                return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            if url.path.startswith("/static/"):
                name = url.path.rsplit("/", 1)[1]
                if name not in STATIC_TYPES:  # only the bundled assets
                    return self._send(404, b"not found", "text/plain")
                return self._send(200, (STATIC / name).read_bytes(), STATIC_TYPES[name])
            if url.path in ("/api/state", "/api/unit"):
                scope = q.get("scope", ["world"])[0]
                if scope not in config.SCOPES:
                    return self._json(400, {"error": "unknown scope"})
                try:
                    if url.path == "/api/state":
                        return self._json(200, payload(scope))
                    try:
                        uid = int(q.get("id", [""])[0])
                    except ValueError:
                        return self._json(400, {"error": "bad id"})
                    d = detail(scope, uid)
                    return self._json(200, d) if d else self._json(404, {"error": "no such unit"})
                except FileNotFoundError:
                    return self._json(404, {"error": f"no forecast for {scope}: run "
                                                     f"`aegis forecast --scope {scope}`"})
            if url.path.startswith("/geo/"):
                name = url.path.rsplit("/", 1)[1]
                allowed = {WORLD_POLYGONS} | {s["boundaries"] for s in config.SCOPES.values() if "boundaries" in s}
                if name not in allowed:  # no path traversal: only known files
                    return self._send(404, b"not found", "text/plain")
                return self._send(200, geo_bytes(name), "application/geo+json", gzipped=True)
            return self._send(404, b"not found", "text/plain")
        except Exception as exc:  # keep the server alive, report the error
            return self._json(500, {"error": str(exc)})


def serve(scope: str = "world", port: int = 8765, open_browser: bool = True,
          background: bool = False) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    if open_browser:
        webbrowser.open(url)
    if background:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
    else:
        print(f"AEGIS globe at {url}  (Ctrl+C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            httpd.server_close()
    return httpd
