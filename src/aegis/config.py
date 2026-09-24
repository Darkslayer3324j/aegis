"""Paths and source URLs.

Where AEGIS keeps its data (``data/``) and results (``results/``):

1. ``AEGIS_HOME``, if set;
2. the source checkout, when running from a clone (``pyproject.toml`` next to ``src/``);
3. otherwise the per-user data folder of the operating system:
   ``%LOCALAPPDATA%\\aegis`` on Windows, ``~/Library/Application Support/aegis`` on macOS,
   ``$XDG_DATA_HOME/aegis`` or ``~/.local/share/aegis`` elsewhere.

Never inside the installed package: an installed copy must not write into site-packages.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _base() -> Path:
    if os.environ.get("AEGIS_HOME"):
        return Path(os.environ["AEGIS_HOME"]).expanduser()
    checkout = Path(__file__).resolve().parents[2]
    if (checkout / "pyproject.toml").exists() and (checkout / "src" / "aegis").is_dir():
        return checkout
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "aegis"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "aegis"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "aegis"


BASE = _base()
HOME = BASE / "data"
RAW = HOME / "raw"          # downloaded files, never modified after download
STORE = HOME / "store"      # parquet copies of the raw files, one per release
MANIFEST = HOME / "manifest.json"
RESULTS = BASE / "results"
GEO = HOME / "geo"
FIRST_SYNC_MB = 450         # shown to the user before the first download

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
