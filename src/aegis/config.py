"""Paths and source URLs. Override the data root with the AEGIS_HOME environment variable."""

from __future__ import annotations

import os
from pathlib import Path

HOME = Path(os.environ.get("AEGIS_HOME", Path(__file__).resolve().parents[2] / "data"))
RAW = HOME / "raw"          # downloaded files, never modified after download
STORE = HOME / "store"      # parquet copies of the raw files, one per release
MANIFEST = HOME / "manifest.json"
RESULTS = HOME.parent / "results"
GEO = HOME / "geo"

UCDP_BASE = "https://ucdp.uu.se/downloads/"
UCDP_INDEX_PAGES = ["https://ucdp.uu.se/downloads/", "https://ucdp.uu.se/downloads/olddw.html"]
NATURAL_EARTH_LAND = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_land.geojson"
)

# Candidate data became global with the 20.0.10 release; earlier releases are Africa-only.
FIRST_GLOBAL_CANDIDATE_YEAR = 21
FIRST_FINAL_VERSION = 221

EVENT_COLUMNS = [
    "id", "date_start", "date_end", "date_prec", "country_id", "country", "region",
    "type_of_violence", "best", "latitude", "longitude",
]


def ensure_dirs() -> None:
    for p in (RAW, STORE, RESULTS, GEO):
        p.mkdir(parents=True, exist_ok=True)
