"""A small braille canvas: each terminal cell holds a 2x4 grid of dots."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from rich.text import Text

# dot (dx, dy) -> bit in the braille code point
_BITS = np.array([[0x01, 0x08], [0x02, 0x10], [0x04, 0x20], [0x40, 0x80]], dtype=np.uint8)

LAT_TOP, LAT_BOTTOM = 84.0, -58.0


class BrailleCanvas:
    def __init__(self, cols: int, rows: int):
        self.cols, self.rows = max(cols, 1), max(rows, 1)
        self.w, self.h = self.cols * 2, self.rows * 4
        self.bits = np.zeros((self.rows, self.cols), dtype=np.uint8)
        self.prio = np.full((self.rows, self.cols), -1, dtype=np.int8)
        self.style = np.full((self.rows, self.cols), "", dtype=object)

    def project(self, lon, lat):
        x = (np.asarray(lon) + 180.0) / 360.0 * (self.w - 1)
        y = (LAT_TOP - np.asarray(lat)) / (LAT_TOP - LAT_BOTTOM) * (self.h - 1)
        return x, y

    def dots(self, x, y, style: str, prio: int) -> None:
        x = np.rint(np.asarray(x, dtype=float)).astype(int)
        y = np.rint(np.asarray(y, dtype=float)).astype(int)
        ok = (x >= 0) & (x < self.w) & (y >= 0) & (y < self.h)
        x, y = x[ok], y[ok]
        cx, cy = x // 2, y // 4
        np.bitwise_or.at(self.bits, (cy, cx), _BITS[y % 4, x % 2])
        upd = self.prio[cy, cx] < prio
        self.prio[cy[upd], cx[upd]] = prio
        self.style[cy[upd], cx[upd]] = style

    def polyline(self, x, y, style: str, prio: int) -> None:
        """Rasterise a line through the points by sampling each segment densely."""
        x, y = np.asarray(x, float), np.asarray(y, float)
        if len(x) < 2:
            return
        xs, ys = [], []
        for i in range(len(x) - 1):
            if abs(x[i + 1] - x[i]) > self.w / 2:  # antimeridian wrap: skip the jump
                continue
            n = int(max(abs(x[i + 1] - x[i]), abs(y[i + 1] - y[i]))) + 1
            t = np.linspace(0, 1, n + 1)
            xs.append(x[i] + (x[i + 1] - x[i]) * t)
            ys.append(y[i] + (y[i + 1] - y[i]) * t)
        if xs:
            self.dots(np.concatenate(xs), np.concatenate(ys), style, prio)

    def render(self) -> Text:
        out = Text(no_wrap=True, overflow="crop")
        for r in range(self.rows):
            row_bits, row_style = self.bits[r], self.style[r]
            start = 0
            for c in range(1, self.cols + 1):
                if c == self.cols or row_style[c] != row_style[start]:
                    chunk = "".join(chr(0x2800 + int(b)) for b in row_bits[start:c])
                    out.append(chunk, style=row_style[start] or None)
                    start = c
            if r < self.rows - 1:
                out.append("\n")
        return out


def load_land(path: Path) -> list[np.ndarray]:
    """Natural Earth land polygons as a list of (n, 2) lon/lat rings."""
    if not path.exists():
        return []
    gj = json.loads(path.read_text(encoding="utf-8"))
    rings = []
    for feat in gj["features"]:
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly in polys:
            for ring in poly:
                rings.append(np.asarray(ring, dtype=float))
    return rings
