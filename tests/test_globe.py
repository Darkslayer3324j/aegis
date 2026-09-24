"""The globe server: geometry orientation, name matching, aggregation, and what it serves."""

import json
import urllib.error
import urllib.request

import pandas as pd
import pytest

from aegis.globe import server


def ring(cw: bool):
    r = [[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]  # clockwise in lon/lat
    return r if cw else r[::-1]


def test_rewind_makes_outer_rings_clockwise_and_holes_counterclockwise():
    g = {"features": [
        {"geometry": {"type": "Polygon", "coordinates": [ring(False), ring(True)]}},
        {"geometry": {"type": "MultiPolygon", "coordinates": [[ring(False)], [ring(True)]]}},
    ]}
    out = server.rewind(g)
    poly = out["features"][0]["geometry"]["coordinates"]
    assert server._signed_area(poly[0]) < 0 and server._signed_area(poly[1]) > 0
    for p in out["features"][1]["geometry"]["coordinates"]:
        assert server._signed_area(p[0]) < 0


def test_events_leave_the_server_only_as_aggregated_cells():
    ev = pd.DataFrame({"latitude": [33.61, 33.62, 33.9, -1.2], "longitude": [71.44, 71.49, 71.1, 30.0],
                       "country_id": [1, 1, 1, 2]})
    cells = server._cells(ev)
    assert sum(c["n"] for c in cells) == 4
    for c in cells:  # every coordinate sent is a cell centre, never a raw event location
        assert (c["lat"] / server.CELL_DEG - 0.5) % 1 == pytest.approx(0) or \
               (c["lat"] / server.CELL_DEG + 0.5) % 1 == pytest.approx(0)
        assert c["lat"] not in ev["latitude"].tolist()
    assert sorted(c["n"] for c in cells) == [1, 3]  # the three nearby events share one ~55 km cell


@pytest.mark.skipif(not (server.config.GEO / server.WORLD_POLYGONS).exists(), reason="no polygons")
def test_ucdp_names_match_map_shapes():
    for name, shape in [("DR Congo (Zaire)", "Democratic Republic of the Congo"),
                        ("Myanmar (Burma)", "Myanmar"), ("Russia (Soviet Union)", "Russia"),
                        ("Bosnia-Herzegovina", "Bosnia and Herzegovina"), ("Pakistan", "Pakistan")]:
        assert server.geo_key("world", name) == shape
    assert server.geo_key("pakistan", "Islamabad") == "Islamabad Capital Territory"


def test_server_serves_only_known_files_on_localhost():
    httpd = server.serve("world", port=0, open_browser=False, background=True)
    try:
        host, port = httpd.server_address
        assert host == "127.0.0.1"
        base = f"http://127.0.0.1:{port}"
        assert b"AEGIS Globe" in urllib.request.urlopen(base + "/").read()
        for bad in ("/geo/..%2F..%2Fmanifest.json", "/geo/manifest.json", "/../data/manifest.json"):
            with pytest.raises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(base + bad)
            assert e.value.code == 404
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/api/state?scope=nowhere")
        assert e.value.code == 400
    finally:
        httpd.shutdown()


@pytest.mark.skipif(not (server.config.RESULTS / "live" / "meta.json").exists(), reason="no live forecast")
def test_payload_obeys_scope_rules():
    p = server.payload("world")
    text = json.dumps(p)
    assert "side_a" not in text and "side_b" not in text and "source_" not in text  # no actors or sources
    for u in p["units"]:
        if u["status"] == "ABSTAIN":
            assert all(f["aegis"] is None and f["lo"] is None for f in u["forecast"])
