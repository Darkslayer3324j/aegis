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


# Scopes: "world" is country-level for every country. A national scope forecasts one
# country's first-level administrative units (provinces), aggregated exactly like
# countries are in the world scope. See SCOPE.md for the dual-use review.
SCOPES = {
    "world": {"title": "World", "unit": "country"},
    "pakistan": {
        "title": "Pakistan", "unit": "province", "country_id": 770,
        "bbox": (60.5, 78.2, 23.4, 37.3),   # lon min, lon max, lat min, lat max
        "boundaries": "pak_adm1.geojson",   # geoBoundaries gbOpen PAK ADM1 (public domain)
        # UCDP adm_1 spellings -> province. FATA merged into Khyber Pakhtunkhwa in 2018.
        "units": [
            (1, "Khyber Pakhtunkhwa", ("khyber", "fata", "federally administered tribal")),
            (2, "Balochistan", ("baloch",)),
            (3, "Punjab", ("punjab",)),
            (4, "Sindh", ("sindh",)),
            (5, "Islamabad", ("islamabad",)),
            (6, "Gilgit-Baltistan", ("gilgit", "northern areas")),
            (7, "Azad Kashmir", ("azad",)),
        ],
        "unassigned": (9, "Province not recorded"),
    },
}


def scope_store(scope: str) -> Path:
    return STORE if scope == "world" else HOME / "scopes" / scope


def scope_results(scope: str) -> Path:
    return RESULTS if scope == "world" else RESULTS / scope


def ensure_dirs() -> None:
    for p in (RAW, STORE, RESULTS, GEO):
        p.mkdir(parents=True, exist_ok=True)
