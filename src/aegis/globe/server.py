"""`aegis globe`: a local 3D view of the same forecasts the terminal interface shows.

Served from this machine only (127.0.0.1), from the live forecast files. Nothing is
uploaded anywhere. What the browser receives follows SCOPE.md:

* forecasts and visibility per country, or per province in a national scope;
* recorded events **aggregated into roughly 0.5° cells** (about 55 km). Individual event
  coordinates, sources and actors never leave the server;
* the same template-generated evidence summaries as `aegis explain` (no actors named).
"""

from __future__ import annotations

import json
import re
import threading
import webbrowser
from functools import lru_cache
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

from .. import config, evidence, live

STATIC = Path(__file__).resolve().parent / "static"
CELL_DEG = 0.5
WORLD_POLYGONS = "ne_110m_admin_0_countries.geojson"
NATURAL_EARTH_COUNTRIES = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
    "ne_110m_admin_0_countries.geojson"
)
# UCDP names that the normaliser below cannot match to Natural Earth on its own.
ALIASES = {
    "drcongo": "Democratic Republic of the Congo",
    "bosniaherzegovina": "Bosnia and Herzegovina",
    "antiguabarbuda": "Antigua and Barbuda",
}
PAK_ALIASES = {"Islamabad": "Islamabad Capital Territory"}


def _signed_area(ring) -> float:
    return sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1)) / 2


def rewind(geojson: dict) -> dict:
    """Outer rings clockwise, holes counter-clockwise: the orientation the globe renderer
    (d3-geo) expects. geoBoundaries follows RFC 7946 (the opposite), and unfixed its
    provinces render inside-out, covering the whole globe except the province."""
    def fix(poly):
        out = []
        for i, ring in enumerate(poly):
            cw = _signed_area(ring) < 0
            out.append(ring if (cw if i == 0 else not cw) else ring[::-1])
        return out
    for f in geojson["features"]:
        g = f["geometry"]
        if g["type"] == "Polygon":
            g["coordinates"] = fix(g["coordinates"])
        elif g["type"] == "MultiPolygon":
            g["coordinates"] = [fix(p) for p in g["coordinates"]]
    return geojson


@lru_cache(maxsize=8)
def geo_bytes(name: str) -> bytes:
    return json.dumps(rewind(json.loads((config.GEO / name).read_text(encoding="utf-8")))).encode()


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


def geo_key(scope: str, name: str) -> str | None:
    """The polygon a unit is drawn with, or None if the map has no shape for it."""
    if scope == "world":
        n = _norm(name)
        return ALIASES.get(n) or _world_name_index().get(n)
    return PAK_ALIASES.get(name, name) if scope == "pakistan" else None


def _cells(events: pd.DataFrame) -> list[dict]:
    """Recorded events aggregated to CELL_DEG cells: centre, count, share by type."""
    e = events.dropna(subset=["latitude", "longitude"])
    if e.empty:
        return []
    lat = (np.floor(e["latitude"] / CELL_DEG) + 0.5) * CELL_DEG
    lng = (np.floor(e["longitude"] / CELL_DEG) + 0.5) * CELL_DEG
    g = e.assign(lat=lat.round(3), lng=lng.round(3)).groupby(["lat", "lng"])
    out = g.size().rename("n").reset_index()
    return [{"lat": float(r.lat), "lng": float(r.lng), "n": int(r.n)} for r in out.itertuples()]


def payload(scope: str) -> dict:
    state = live.load(scope)
    spec = config.SCOPES[scope]
    units = []
    for _, r in state.countries.iterrows():
        cid = int(r["country_id"])
        s = state.series[state.series["country_id"] == cid]
        track = None
        if state.backtest_by_country is not None and cid in state.backtest_by_country.index:
            track = state.backtest_by_country.loc[cid]
        comp = None
        if "type_of_violence" in state.events:
            e = state.events[state.events["country_id"] == cid]
            comp = e["type_of_violence"].value_counts().astype(int).to_dict()
        ev = evidence.build(r, s, track, comp)
        abstain = r["status"] == "ABSTAIN"
        fc = []
        for h in (1, 2, 3):
            fc.append({
                "h": h,
                "aegis": None if abstain else round(float(r[f"aegis_h{h}"]), 2),
                "lo": None if abstain else int(r[f"aegis_h{h}_lo"]),
                "hi": None if abstain else int(r[f"aegis_h{h}_hi"]),
                "base": round(float(r[f"base_h{h}"]), 2),
            })
        units.append({
            "id": cid, "name": r["country"], "region": r["region"], "geo": geo_key(scope, r["country"]),
            "status": r["status"], "C1": round(float(r["C1"]), 3), "volatility": round(float(r["volatility"]), 3),
            "dark": bool(r["dark"]), "activity12": round(float(r["activity12"]), 2),
            "obs_last": int(r["obs_last"]), "nowcast_last": round(float(r["nowcast_last"]), 1),
            "forecast": fc,
            "series": [{"m": x.m, "obs": x.observed, "exp": round(x.nowcast, 2), "final": bool(x.is_final)}
                       for x in s.itertuples()],
            "evidence": {"headline": ev.headline, "points": ev.points, "footer": ev.footer,
                         "shows_number": ev.shows_number},
            "track": None if track is None else {
                "miss": round(float(track["miss"]), 3), "n": int(track["n"]),
                "baseline_crps": round(float(track["nbar"]), 3), "aegis_crps": round(float(track["nbar+vis"]), 3)},
        })

    bt = None
    if state.backtest:
        p2 = state.backtest["paper2_visibility"]
        d = p2["primary_active_crps"]
        cand = state.backtest.get("candidates", {})
        bt = {"baseline_crps": p2["models_vintage_active"]["nbar"]["crps"],
              "aegis_crps": p2["models_vintage_active"]["nbar+vis"]["crps"],
              "diff": d.get("mean_diff"), "ci": d.get("ci95"),
              "selected_candidate": cand.get("selected"),
              "origins": state.backtest["meta"].get("origins_scored")}
    return {
        "scope": scope, "title": spec["title"], "unit": spec["unit"], "bbox": spec.get("bbox"),
        "polygons": f"/geo/{spec.get('boundaries', WORLD_POLYGONS)}",
        "polygon_key": "shapeName" if scope != "world" else "ADMIN",
        "context_polygons": None if scope == "world" else f"/geo/{WORLD_POLYGONS}",
        "context_exclude": spec["title"] if scope != "world" else None,
        "meta": state.meta, "backtest": bt, "units": units,
        "cells": _cells(state.events), "cell_deg": CELL_DEG,
        "footer": evidence.FOOTER,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "aegis-globe"

    def log_message(self, fmt, *args):  # quiet
        pass

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        try:
            if url.path in ("/", "/index.html"):
                return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            if url.path == "/api/state":
                scope = parse_qs(url.query).get("scope", ["world"])[0]
                if scope not in config.SCOPES:
                    return self._send(400, b'{"error":"unknown scope"}', "application/json")
                try:
                    body = json.dumps(payload(scope), default=float).encode()
                except FileNotFoundError:
                    return self._send(404, json.dumps({"error": f"no forecast for {scope}: run "
                                                        f"`aegis forecast --scope {scope}`"}).encode(),
                                      "application/json")
                return self._send(200, body, "application/json")
            if url.path.startswith("/geo/"):
                name = url.path.rsplit("/", 1)[1]
                allowed = {WORLD_POLYGONS} | {s["boundaries"] for s in config.SCOPES.values() if "boundaries" in s}
                if name not in allowed:  # no path traversal: only known files
                    return self._send(404, b"not found", "text/plain")
                if name == WORLD_POLYGONS:
                    ensure_polygons()
                return self._send(200, geo_bytes(name), "application/geo+json")
            return self._send(404, b"not found", "text/plain")
        except Exception as exc:  # keep the server alive, report the error
            return self._send(500, json.dumps({"error": str(exc)}).encode(), "application/json")


def serve(scope: str = "world", port: int = 8765, open_browser: bool = True,
          background: bool = False) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/?scope={scope}"
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
