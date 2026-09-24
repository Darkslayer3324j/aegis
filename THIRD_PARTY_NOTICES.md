# Third-party notices

AEGIS bundles, downloads, or has the browser fetch the following. Their licences and
terms apply to those parts.

## Bundled

| Component | Where | Licence |
|---|---|---|
| MapLibre GL JS 5.24.0 | `src/aegis/globe/static/maplibre-gl.js`, `maplibre-gl.css` | BSD-3-Clause, Copyright (c) 2023 MapLibre contributors |

## Downloaded by AEGIS (into the data folder)

| Data | Licence |
|---|---|
| UCDP GED and Candidate releases | CC BY 4.0: cite Sundberg & Melander (2013) and Hegre et al. (2020) |
| Natural Earth 1:110m land and countries; 1:10m admin-1 states and provinces | Public domain |
| geoBoundaries gbOpen PAK ADM1 | Public domain |

## Fetched by the browser while `aegis globe` is open (online only)

| Service | Used for | Terms |
|---|---|---|
| OpenFreeMap (tiles.openfreemap.org) | Base map: streets, labels, 3D buildings | Free, no key. Map data © OpenStreetMap contributors (ODbL), OpenMapTiles schema; attribution shown on the map |
| AWS Terrain Tiles (Terrarium, s3.amazonaws.com/elevation-tiles-prod) | Terrain relief and 3D elevation | Open data; sources include SRTM, GMTED, ETOPO1, NRCan and others (attribution shown on the map) |
| OpenStreetMap Nominatim | "Go to a place" search only, when you press Go | Nominatim usage policy: occasional interactive use only; your search text is sent to it |

Offline, the map falls back to AEGIS's own country shapes, and none of these services is
contacted.

## Optional extras

`aegis-forecast[baselines]` installs StatsForecast (Apache-2.0) from PyPI. Nothing from it
is bundled.
