"""Download UCDP releases into an immutable vintage store.

Every release is kept exactly as published (``data/raw``), hashed, and converted to a
parquet copy (``data/store``). Nothing is ever overwritten: a release that is already on
disk is skipped. The manifest records, for every release, the date from which AEGIS
treats it as *available*; the vintage engine uses that date to decide what was known at
any forecast origin.
"""

from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import io
import json
import re
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

import httpx
import pandas as pd

from . import config

MONTHLY_RE = re.compile(r"candidateged/GEDEvent_v(\d{2})_0_(\d{1,2})\.csv")
CUMULATIVE_RE = re.compile(r"candidateged/GEDEvent_v(\d{2})_01_\d{2}_(\d{2})\.csv")
FINAL_RE = re.compile(r"ged/ged(\d{3})-csv\.zip")

# If Last-Modified is more than this long after the nominal release date, the file was
# probably re-uploaded. The release is still dated by Last-Modified (never backdated),
# but flagged "last-modified-late" so reports can say which vintages were lost.
REUPLOAD_TOLERANCE = dt.timedelta(days=60)


@dataclass
class Release:
    name: str            # e.g. "cand-m-25.03", "cand-c-25.01-25.06", "final-26.1"
    kind: str            # "monthly" | "cumulative" | "final"
    url: str
    cover_start: str     # first month covered (YYYY-MM)
    cover_end: str       # last month covered (YYYY-MM)
    nominal: str         # rule-based availability date (YYYY-MM-DD)
    available: str = ""  # date AEGIS treats the release as known from
    date_source: str = ""  # see resolve_available()
    last_modified: str = ""
    sha256: str = ""
    bytes: int = 0
    rows: int = 0
    fetched_at: str = ""
    raw_file: str = ""
    store_file: str = ""
    notes: str = ""


def _month_add(year: int, month: int, k: int) -> tuple[int, int]:
    idx = year * 12 + (month - 1) + k
    return idx // 12, idx % 12 + 1


def parse_release(path: str) -> Release | None:
    """Turn a UCDP download path into a Release with its coverage and nominal date."""
    url = config.UCDP_BASE + path
    if m := MONTHLY_RE.fullmatch(path):
        yy, mm = int(m[1]), int(m[2])
        year = 2000 + yy
        ny, nm = _month_add(year, mm, 1)
        return Release(
            name=f"cand-m-{yy:02d}.{mm:02d}", kind="monthly", url=url,
            cover_start=f"{year}-{mm:02d}", cover_end=f"{year}-{mm:02d}",
            nominal=f"{ny}-{nm:02d}-20",
        )
    if m := CUMULATIVE_RE.fullmatch(path):
        yy, mm = int(m[1]), int(m[2])
        year = 2000 + yy
        ny, nm = _month_add(year, mm, 2)
        return Release(
            name=f"cand-c-{yy:02d}.01-{yy:02d}.{mm:02d}", kind="cumulative", url=url,
            cover_start=f"{year}-01", cover_end=f"{year}-{mm:02d}",
            nominal=f"{ny}-{nm:02d}-20",
        )
    if m := FINAL_RE.fullmatch(path):
        v = m[1]
        year = 2000 + int(v[:2])
        return Release(
            name=f"final-{v[:2]}.{v[2]}", kind="final", url=url,
            cover_start="1989-01", cover_end=f"{year - 1}-12",
            nominal=f"{year}-06-15",
        )
    return None


def wanted(rel: Release) -> bool:
    """Releases AEGIS uses: global candidate data and the finals the backtest can see."""
    if rel.kind == "final":
        v = int(rel.name.split("-")[1].replace(".", ""))
        return v >= config.FIRST_FINAL_VERSION
    return int(rel.cover_start[2:4]) >= config.FIRST_GLOBAL_CANDIDATE_YEAR


def discover(client: httpx.Client) -> list[Release]:
    paths: set[str] = set()
    pattern = re.compile(r"(candidateged/GEDEvent_v[0-9_]+\.csv|ged/ged[0-9]+-csv\.zip)")
    for page in config.UCDP_INDEX_PAGES:
        r = client.get(page)
        r.raise_for_status()
        paths.update(pattern.findall(r.text))
    releases = [rel for p in sorted(paths) if (rel := parse_release(p)) and wanted(rel)]
    return sorted(releases, key=lambda r: (r.nominal, r.name))


def resolve_available(rel: Release, last_modified: dt.datetime | None) -> tuple[str, str]:
    """Pick the date from which a release's *content as downloaded* counts as known.

    Changed content is never backdated. Last-Modified is when the bytes we hold were
    last written, so the content is treated as available from then, even when UCDP
    probably published an earlier version of the same file sooner. A late Last-Modified
    therefore costs vintages (the release appears later than it really did) but can never
    leak a revision into an earlier origin.

    Returns (date, source) where source is:
      "last-modified"         Last-Modified is close to the nominal release date
      "last-modified-late"    Last-Modified is well after it: probably a re-upload
      "rule-unverified"       no Last-Modified header; nominal date used and flagged
    """
    nominal = dt.date.fromisoformat(rel.nominal)
    cover_end_y, cover_end_m = map(int, rel.cover_end.split("-"))
    ey, em = _month_add(cover_end_y, cover_end_m, 1)
    earliest = dt.date(ey, em, 1)  # cannot be published before its coverage ends
    if last_modified is not None:
        lm = max(last_modified.date(), earliest)
        late = lm > nominal + REUPLOAD_TOLERANCE
        return lm.isoformat(), "last-modified-late" if late else "last-modified"
    return max(nominal, earliest).isoformat(), "rule-unverified"


def redate(manifest: dict[str, dict]) -> int:
    """Re-apply the availability policy to every release already in the manifest.

    Availability is derived from recorded metadata, so a policy change must not require
    re-downloading. Returns how many releases changed date.
    """
    changed = 0
    for row in manifest.values():
        rel = Release(**{k: row.get(k, "") for k in Release.__dataclass_fields__})
        lm = dt.datetime.fromisoformat(row["last_modified"]) if row.get("last_modified") else None
        available, source = resolve_available(rel, lm)
        if (available, source) != (row["available"], row["date_source"]):
            row["available"], row["date_source"] = available, source
            changed += 1
    return changed


def load_manifest() -> dict[str, dict]:
    if config.MANIFEST.exists():
        return {r["name"]: r for r in json.loads(config.MANIFEST.read_text(encoding="utf-8"))}
    return {}


def save_manifest(entries: dict[str, dict]) -> None:
    rows = sorted(entries.values(), key=lambda r: (r["available"], r["name"]))
    config.MANIFEST.write_text(json.dumps(rows, indent=1), encoding="utf-8")


# The standard 49-column GED layout. Some releases (e.g. Candidate 24.0.1) were
# published without a header row; they are read with these names instead.
GED_COLUMNS = (
    "id,relid,year,active_year,code_status,type_of_violence,conflict_dset_id,conflict_new_id,"
    "conflict_name,dyad_dset_id,dyad_new_id,dyad_name,side_a_dset_id,side_a_new_id,side_a,"
    "side_b_dset_id,side_b_new_id,side_b,number_of_sources,source_article,source_office,"
    "source_date,source_headline,source_original,where_prec,where_coordinates,"
    "where_description,adm_1,adm_2,latitude,longitude,geom_wkt,priogrid_gid,country,"
    "country_id,region,event_clarity,date_prec,date_start,date_end,deaths_a,deaths_b,"
    "deaths_civilians,deaths_unknown,best,high,low,gwnoa,gwnob"
).split(",")


def _read_ged_csv(fh) -> tuple[pd.DataFrame, bool]:
    """Read a GED csv, tolerating a missing header row. Returns (frame, had_header)."""
    head = pd.read_csv(fh, nrows=0)
    fh.seek(0)
    if "id" in head.columns and "date_start" in head.columns:
        return pd.read_csv(fh, usecols=config.EVENT_COLUMNS, low_memory=False), True
    if len(head.columns) != len(GED_COLUMNS):
        raise ValueError(f"unrecognised GED layout with {len(head.columns)} columns")
    df = pd.read_csv(fh, header=None, names=GED_COLUMNS, low_memory=False)
    return df[config.EVENT_COLUMNS], False


def _to_parquet(raw: Path, kind: str, dest: Path) -> tuple[int, bool]:
    if kind == "final":
        with zipfile.ZipFile(raw) as z:
            member = next(n for n in z.namelist() if n.lower().endswith(".csv"))
            data = io.BytesIO(z.read(member))
        df, had_header = _read_ged_csv(data)
    else:
        with raw.open("rb") as fh:
            df, had_header = _read_ged_csv(fh)
    for col in ("date_start", "date_end"):
        df[col] = pd.to_datetime(df[col], errors="coerce")
    df = df.dropna(subset=["date_start", "country_id"])
    df["country_id"] = df["country_id"].astype(int)
    df["best"] = pd.to_numeric(df["best"], errors="coerce").fillna(0).astype(int)
    df.to_parquet(dest, index=False)
    return len(df), had_header


def sync(progress: Callable[[str], None] = print, only: Iterable[str] | None = None) -> list[dict]:
    """Fetch every wanted release not already in the store. Returns manifest rows."""
    config.ensure_dirs()
    manifest = load_manifest()
    if n := redate(manifest):
        save_manifest(manifest)
        progress(f"availability policy re-applied: {n} releases re-dated")
    with httpx.Client(timeout=httpx.Timeout(30.0, read=300.0), follow_redirects=True) as client:
        releases = discover(client)
        if only:
            keep = set(only)
            releases = [r for r in releases if r.name in keep]
        todo = [r for r in releases if r.name not in manifest]
        progress(f"{len(releases)} releases in catalogue, {len(todo)} new")
        for i, rel in enumerate(todo, 1):
            fname = rel.url.rsplit("/", 1)[1]
            raw = config.RAW / fname
            sha = hashlib.sha256()
            size = 0
            lm_header = None
            if raw.exists():
                data = raw.read_bytes()
                sha.update(data)
                size = len(data)
                lm_header = client.head(rel.url).headers.get("last-modified")
            else:
                tmp = raw.with_suffix(raw.suffix + ".part")
                with client.stream("GET", rel.url) as r:
                    if r.status_code == 404:
                        progress(f"[{i}/{len(todo)}] {rel.name}: 404, skipped")
                        continue
                    r.raise_for_status()
                    lm_header = r.headers.get("last-modified")
                    with tmp.open("wb") as fh:
                        for chunk in r.iter_bytes(1 << 20):
                            fh.write(chunk)
                            sha.update(chunk)
                            size += len(chunk)
                tmp.replace(raw)
            lm = email.utils.parsedate_to_datetime(lm_header) if lm_header else None
            rel.last_modified = lm.isoformat() if lm else ""
            rel.available, rel.date_source = resolve_available(rel, lm)
            rel.sha256 = sha.hexdigest()
            rel.bytes = size
            rel.fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            rel.raw_file = fname
            store_file = config.STORE / f"{rel.name}.parquet"
            rel.rows, had_header = _to_parquet(raw, rel.kind, store_file)
            rel.store_file = store_file.name
            if not had_header:
                rel.notes = "published without a header row; standard GED columns assumed"
            manifest[rel.name] = asdict(rel)
            save_manifest(manifest)  # after every file, so an interrupted sync keeps progress
            progress(f"[{i}/{len(todo)}] {rel.name}: {rel.rows} events, available {rel.available} ({rel.date_source})")
    return list(manifest.values())


def verify() -> list[str]:
    """Re-hash every raw file against the manifest. Returns the names that fail."""
    bad = []
    for name, row in load_manifest().items():
        p = config.RAW / row["raw_file"]
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != row["sha256"]:
            bad.append(name)
    return bad


def fetch_land(progress: Callable[[str], None] = print) -> Path:
    """Natural Earth 1:110m land polygons (public domain), used only for the map outline."""
    config.ensure_dirs()
    dest = config.GEO / "ne_110m_land.geojson"
    if not dest.exists():
        r = httpx.get(config.NATURAL_EARTH_LAND, timeout=60, follow_redirects=True)
        r.raise_for_status()
        dest.write_bytes(r.content)
        progress("fetched Natural Earth land outline")
    return dest
