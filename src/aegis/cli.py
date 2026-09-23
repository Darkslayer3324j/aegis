"""`aegis` command line.

    aegis                 open the terminal interface (computes today's forecast if needed)
    aegis sync            download new UCDP releases into the vintage store
    aegis forecast        run today's forecast cycle
    aegis backtest        vintage-aware walk-forward evaluation
    aegis explain <name>  the evidence behind one country's numbers
    aegis status          what is in the store
    aegis verify          re-hash every raw file against the manifest
"""

from __future__ import annotations

import json
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from . import __version__, config

# Windows consoles and pipes default to cp1252, which cannot print the interface's symbols.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

app = typer.Typer(add_completion=False, no_args_is_help=False, invoke_without_command=True,
                  help="AEGIS: visibility-aware probabilistic conflict forecasting.")
console = Console()


def _say(msg: str) -> None:
    console.print(f"[#7aa2f7]aegis[/] {msg}")


@app.callback()
def main(ctx: typer.Context,
         version: bool = typer.Option(False, "--version", help="Print the version and exit.")) -> None:
    if version:
        console.print(f"aegis {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        open_interface()


def open_interface() -> None:
    from . import live
    from .tui.app import run

    if not config.MANIFEST.exists():
        _say("no data yet: running first sync (downloads ~450 MB of UCDP releases once)")
        sync()
    try:
        state = live.load()
    except FileNotFoundError:
        _say("computing today's forecast...")
        live.compute(progress=_say)
        state = live.load()
    run(state)


@app.command()
def sync(refresh: bool = typer.Option(True, help="Recompute today's forecast afterwards.")) -> None:
    """Download new UCDP Candidate and GED releases into the immutable vintage store."""
    from . import ingest, live

    ingest.sync(progress=_say)
    ingest.fetch_land(progress=_say)
    if refresh:
        live.compute(progress=_say)


@app.command()
def forecast(asof: Optional[str] = typer.Option(None, help="Forecast as of this date (YYYY-MM-DD).")) -> None:
    """Run the forecast cycle for today (or a past date, using only what was known then)."""
    import datetime as dt

    from . import live

    live.compute(asof=dt.date.fromisoformat(asof) if asof else None, progress=_say)


@app.command()
def backtest(start: str = typer.Option("2022-06-01", help="First forecast origin."),
             end: Optional[str] = typer.Option(None, help="Last forecast origin."),
             target: str = typer.Option("events", help="events or deaths"),
             draws: int = typer.Option(40, help="Nowcast draws per forecast.")) -> None:
    """Walk-forward evaluation on historical vintages, scored against final data."""
    from . import backtest as bt

    out = bt.run(start=start, end=end, target=target, draws=draws, progress=_say)
    console.print(Markdown((out / "report.md").read_text(encoding="utf-8")))


@app.command()
def explain(country: str = typer.Argument(..., help="Country name (partial match) or UCDP country id.")) -> None:
    """Show the evidence behind a country's visibility estimate and forecast."""
    from . import live
    from .vintage import VintageStore

    state = live.load()
    df = state.countries
    if country.isdigit():
        hit = df[df["country_id"] == int(country)]
    else:
        hit = df[df["country"].str.contains(country, case=False, regex=False)]
    if hit.empty:
        _say(f"no country matches '{country}'")
        raise typer.Exit(1)
    r = hit.sort_values("activity12", ascending=False).iloc[0]
    cid = int(r["country_id"])

    console.rule(f"[bold]{r['country']}[/]  ·  {r['region']}  ·  status [bold]{r['status']}[/]")
    t = Table(show_header=False, box=None)
    t.add_column(style="#6b7a8c")
    t.add_column()
    t.add_row("Forecast origin", f"{state.meta['origin']} (data through {state.meta['data_through']})")
    t.add_row("Reported in newest month", f"{int(r['obs_last'])}")
    t.add_row("Expected once reporting catches up",
              f"{r['nowcast_last']:.1f}  (80%: {int(r['nowcast_lo'])}–{int(r['nowcast_hi'])})")
    t.add_row("Est. completeness, age 1/2/3", f"{r['C1']:.0%} / {r['C2']:.0%} / {r['C3']:.0%}")
    t.add_row("Revision volatility (age 1)", f"{r['volatility']:.2f}")
    t.add_row("Mean monthly events, last 12 months", f"{r['activity12']:.1f}")
    for h in (1, 2, 3):
        t.add_row(f"Forecast h={h}  baseline / AEGIS",
                  f"{r[f'base_h{h}']:.1f} [{int(r[f'base_h{h}_lo'])}–{int(r[f'base_h{h}_hi'])}]  /  "
                  f"{r[f'aegis_h{h}']:.1f} [{int(r[f'aegis_h{h}_lo'])}–{int(r[f'aegis_h{h}_hi'])}]")
    if state.backtest_by_country is not None and cid in state.backtest_by_country.index:
        cb = state.backtest_by_country.loc[cid]
        t.add_row("Backtest CRPS here  baseline / AEGIS", f"{cb['nbar']:.2f} / {cb['nbar+vis']:.2f}")
    console.print(t)

    console.print("\n[bold]Revision trail[/]: the count for each recent month, as it stood after each release.")
    console.print("[#6b7a8c]This is the evidence the completeness estimate is learned from.[/]")
    store = VintageStore.load()
    trail = live.revision_trail(store, cid)
    tt = Table(box=None)
    tt.add_column("month")
    for c in trail.columns:
        tt.add_column(c, justify="right", no_wrap=True, min_width=len(c))
    for m, vals in trail.iterrows():
        tt.add_row(m, *["·" if v != v else f"{int(v)}" for v in vals])
    console.print(tt)
    console.print("\n[#6b7a8c]Source: UCDP Candidate & GED (CC BY 4.0). Counts are UCDP events of organised "
                  "violence (≥1 death), aggregated to country-month.[/]")


@app.command()
def status() -> None:
    """Summarise the vintage store."""
    if not config.MANIFEST.exists():
        _say("empty store: run `aegis sync`")
        return
    rows = json.loads(config.MANIFEST.read_text(encoding="utf-8"))
    kinds = {}
    for r in rows:
        kinds.setdefault(r["kind"], []).append(r)
    t = Table(title="Vintage store")
    for col in ("kind", "releases", "first available", "last available", "rows"):
        t.add_column(col)
    for k, rs in kinds.items():
        t.add_row(k, str(len(rs)), rs[0]["available"], rs[-1]["available"], f"{sum(r['rows'] for r in rs):,}")
    console.print(t)
    flagged = [r for r in rows if r["date_source"] != "last-modified" or r.get("notes")]
    for r in flagged:
        console.print(f"[#e6b450]note[/] {r['name']}: availability {r['available']} ({r['date_source']}) "
                      f"{r.get('notes', '')}")


@app.command()
def verify() -> None:
    """Re-hash every raw download against the manifest."""
    from . import ingest

    bad = ingest.verify()
    if bad:
        _say(f"[red]{len(bad)} releases failed verification:[/] {', '.join(bad)}")
        raise typer.Exit(1)
    _say("all raw releases match their recorded SHA-256")


if __name__ == "__main__":
    app()
