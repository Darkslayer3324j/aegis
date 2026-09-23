"""AEGIS terminal interface.

The map shows reported events from the last three months, coloured by how well AEGIS can
see each country. The panels show, for the selected country, what was reported, what
AEGIS expects the count to become once reporting catches up, the forecast, and whether
the baseline model or AEGIS has actually been more accurate there.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Input, Static, TabbedContent, TabPane

from .. import config
from .. import evidence
from ..live import LiveState
from .braille import BrailleCanvas, load_land

STATUS_STYLE = {"OK": "#3fc1b0", "WARN": "#e6b450", "ABSTAIN": "#ff5f56"}
LAND_STYLE = "#34475a"
SELECTED_STYLE = "bold #ffffff"
ACCENT = "#7aa2f7"
DIM = "#6b7a8c"
SPARK = "▁▂▃▄▅▆▇█"


def bar(value: float, vmax: float, width: int = 14, style: str = ACCENT) -> Text:
    n = 0 if vmax <= 0 else int(round(min(value / vmax, 1.0) * width))
    t = Text("█" * n, style=style)
    t.append("░" * (width - n), style=DIM)
    return t


def spark(values: np.ndarray, vmax: float) -> str:
    if vmax <= 0:
        return SPARK[0] * len(values)
    idx = np.clip((values / vmax * (len(SPARK) - 1)).round().astype(int), 0, len(SPARK) - 1)
    return "".join(SPARK[i] for i in idx)


class WorldMap(Static):
    def __init__(self, state: LiveState, **kw):
        super().__init__(**kw)
        self.state = state
        self.selected: int | None = None
        self.rings = load_land(config.GEO / "ne_110m_land.geojson")
        status = state.countries.set_index("country_id")["status"]
        ev = state.events.dropna(subset=["latitude", "longitude"])
        self.ev = ev.assign(status=ev["country_id"].map(status).fillna("OK"))

    def on_resize(self) -> None:
        self.redraw()

    def select(self, country_id: int | None) -> None:
        self.selected = country_id
        self.redraw()

    def redraw(self) -> None:
        w, h = self.size.width, self.size.height
        if w < 10 or h < 4:
            return
        cv = BrailleCanvas(w, h)
        for ring in self.rings:
            x, y = cv.project(ring[:, 0], ring[:, 1])
            cv.polyline(x, y, LAND_STYLE, 0)
        for prio, status in ((1, "OK"), (2, "WARN"), (3, "ABSTAIN")):
            e = self.ev[self.ev["status"] == status]
            x, y = cv.project(e["longitude"].to_numpy(), e["latitude"].to_numpy())
            cv.dots(x, y, STATUS_STYLE[status], prio)
        if self.selected is not None:
            e = self.ev[self.ev["country_id"] == self.selected]
            x, y = cv.project(e["longitude"].to_numpy(), e["latitude"].to_numpy())
            cv.dots(x, y, SELECTED_STYLE, 4)
        self.update(cv.render())


class CountryPanel(Static):
    def show(self, state: LiveState, row: pd.Series) -> None:
        c = int(row["country_id"])
        status = row["status"]
        sstyle = STATUS_STYLE[status]
        title = Text(f" {row['country'].upper()} ", style=f"bold reverse {sstyle}")
        title.append(f"  {row['region']}", style=DIM)

        grid = Table.grid(padding=(0, 3))
        for _ in range(3):
            grid.add_column()
        vis = row["C1"]
        f1 = row["aegis_h1"]
        vmax = max(f1, row["base_h1"], row["nowcast_last"], 1.0) * 1.25
        grid.add_row(Text("FORECAST (next month)", style=DIM), Text("VISIBILITY (newest month)", style=DIM),
                     Text("DECISION", style=DIM))
        abstain = status == "ABSTAIN"
        grid.add_row(Text("not estimated" if abstain else f"{f1:,.1f} events", style="bold"),
                     Text(f"{vis:.0%}", style=f"bold {sstyle}"), Text(status, style=f"bold {sstyle}"))
        grid.add_row(Text("reporting impaired", style=sstyle) if abstain else bar(f1, vmax),
                     bar(min(vis, 1.0), 1.0, style=sstyle),
                     Text("" if abstain else f"80%: {int(row['aegis_h1_lo'])}–{int(row['aegis_h1_hi'])}",
                          style=DIM))

        facts = Table.grid(padding=(0, 2))
        facts.add_column(style=DIM)
        facts.add_column()
        facts.add_row("Reported so far (newest month)", f"{int(row['obs_last'])}")
        facts.add_row("Expected once reporting catches up",
                      f"{row['nowcast_last']:.1f}  [{int(row['nowcast_lo'])}–{int(row['nowcast_hi'])}]")
        facts.add_row("Est. completeness at age 1 / 2 / 3",
                      f"{row['C1']:.0%} / {row['C2']:.0%} / {row['C3']:.0%}")
        facts.add_row("Revision volatility (age 1)", f"{row['volatility']:.2f}")
        if status != "ABSTAIN":
            facts.add_row("P(any event) next month", f"{row['aegis_h1_ppos']:.0%}")
            facts.add_row("Horizons 1 / 2 / 3 (AEGIS)",
                          f"{row['aegis_h1']:.1f} / {row['aegis_h2']:.1f} / {row['aegis_h3']:.1f}")
            facts.add_row("Horizons 1 / 2 / 3 (baseline)",
                          f"{row['base_h1']:.1f} / {row['base_h2']:.1f} / {row['base_h3']:.1f}")

        s = state.series[state.series["country_id"] == c]
        obs, now = s["observed"].to_numpy(), s["nowcast"].to_numpy()
        top = max(obs.max(initial=0), now.max(initial=0))
        spark_obs = Text("reported ", style=DIM)
        spark_now = Text("expected ", style=DIM)
        for o, n, fin in zip(obs, now, s["is_final"].to_numpy()):
            spark_obs.append(spark(np.array([o]), top), style="#9aa5b1" if fin else "#c0caf5")
            spark_now.append(spark(np.array([n]), top), style="#9aa5b1" if fin else sstyle)
        span = Text(f"          {s['m'].iloc[0]} … {s['m'].iloc[-1]}  (grey = final data)", style=DIM)

        notes = []
        if status == "ABSTAIN":
            notes.append(Text("⚠ ABSTAINING: the reporting channel is impaired (low completeness or a "
                              "silent feed after recent activity), so AEGIS gives no number. "
                              "Press e for the evidence.", style=sstyle))
        elif status == "WARN":
            notes.append(Text("⚠ VISIBILITY WARNING: recent observations are likely incomplete or "
                              "heavily revised.", style=sstyle))
        if row["dark"]:
            notes.append(Text("◌ Silent channel: active in the last 12 months, nothing reported in the "
                              "newest release. Quiet feed ≠ quiet world.", style=sstyle))
        self.update(Group(title, Text(""), grid, Text(""), facts, Text(""), spark_obs, spark_now, span,
                          Text(""), *notes))


class EvidencePanel(Static):
    """Plain-language 'why' summary. Wording rules: SCOPE.md; generator: aegis.evidence."""

    def show(self, state: LiveState, row: pd.Series) -> None:
        c = int(row["country_id"])
        s = state.series[state.series["country_id"] == c]
        track = None
        if state.backtest_by_country is not None and c in state.backtest_by_country.index:
            track = state.backtest_by_country.loc[c]
        ev = evidence.build(row, s, track)
        sstyle = STATUS_STYLE[ev.status]
        parts = [Text(f" WHY: {ev.country.upper()} ", style=f"bold reverse {sstyle}"), Text(""),
                 Text(ev.headline, style="bold"), Text("")]
        for label, sentence in ev.points:
            t = Text(f"{label}: ", style=f"bold {sstyle if label in ('Visibility', 'Silent feed') else ACCENT}")
            t.append(sentence[0].upper() + sentence[1:])
            parts.append(t)
        parts += [Text(""), Text(ev.footer, style=f"italic {DIM}")]
        self.update(Group(*parts))


class HealthPanel(Static):
    def show(self, state: LiveState, row: pd.Series | None) -> None:
        m = state.meta
        parts: list = [Text("SYSTEM", style=f"bold {ACCENT}")]
        t = Table.grid(padding=(0, 1))
        t.add_column(style=DIM)
        t.add_column()
        t.add_row("Forecast origin", m["origin"])
        t.add_row("Data through", m["data_through"])
        t.add_row("Newest release", f"{m['latest_candidate']} ({m['latest_candidate_available']})")
        t.add_row("Final release", m["final_release"])
        t.add_row("Revision pairs", f"{m['observation_pairs']:,}")
        gc = m["global_completeness"]
        t.add_row("Global completeness", " ".join(f"{gc.get(str(a), gc.get(a, 1)):.0%}" for a in (1, 2, 3)))
        parts.append(t)

        bt = state.backtest
        parts.append(Text(""))
        parts.append(Text("BASELINE vs AEGIS (backtest, CRPS ↓)", style=f"bold {ACCENT}"))
        if bt is None:
            parts.append(Text("No backtest yet: run `aegis backtest`.", style=DIM))
        else:
            mv = bt["paper2_visibility"]["models_vintage_active"]
            b, a = mv["nbar"]["crps"], mv["nbar+vis"]["crps"]
            top = max(a, b)
            g = Table.grid(padding=(0, 1))
            g.add_column(style=DIM)
            g.add_column()
            g.add_column()
            g.add_row("baseline AR", bar(b, top, 12, "#9aa5b1"), f"{b:.2f}")
            g.add_row("AEGIS", bar(a, top, 12, ACCENT), f"{a:.2f}")
            if row is not None and state.backtest_by_country is not None and \
                    int(row["country_id"]) in state.backtest_by_country.index:
                cb = state.backtest_by_country.loc[int(row["country_id"])]
                top_c = max(cb.max(), 1e-9)
                g.add_row("", "", "")
                g.add_row("here: baseline", bar(cb["nbar"], top_c, 12, "#9aa5b1"), f"{cb['nbar']:.2f}")
                g.add_row("here: AEGIS", bar(cb["nbar+vis"], top_c, 12, ACCENT), f"{cb['nbar+vis']:.2f}")
            parts.append(g)
            d = bt["paper2_visibility"]["primary_active_crps"]
            if d.get("n"):
                lo, hi = d["ci95"]
                verdict = ("AEGIS better" if hi < 0 else "baseline better" if lo > 0
                           else "no significant difference")
                parts.append(Text(f"Δ {d['mean_diff']:+.3f}  95% CI [{lo:+.3f}, {hi:+.3f}] (6-mo blocks) → {verdict}",
                                  style=DIM))
            nc = bt.get("nowcast", {}).get("1") or bt.get("nowcast", {}).get(1)
            if nc:
                parts.append(Text(""))
                parts.append(Text("NOWCAST vs RAW COUNT (age 1)", style=f"bold {ACCENT}"))
                top = max(nc["crps_raw"], nc["crps_nowcast"])
                g2 = Table.grid(padding=(0, 1))
                g2.add_column(style=DIM)
                g2.add_column()
                g2.add_column()
                g2.add_row("raw as final", bar(nc["crps_raw"], top, 12, "#9aa5b1"), f"{nc['crps_raw']:.2f}")
                g2.add_row("nowcast", bar(nc["crps_nowcast"], top, 12, ACCENT), f"{nc['crps_nowcast']:.2f}")
                parts.append(g2)
            p1 = bt["paper1_measurement"]["active"]
            parts.append(Text(""))
            parts.append(Text("RANKING DEPENDS ON THE DATA VIEW", style=f"bold {ACCENT}"))
            parts.append(Text("final:   " + " < ".join(p1["final"]["_rank_crps"]), style=DIM))
            parts.append(Text("vintage: " + " < ".join(p1["vintage"]["_rank_crps"]), style=DIM))
        self.update(Group(*parts))


SORTS = ("forecast", "visibility", "status")


class AegisApp(App):
    TITLE = "AEGIS"
    CSS = """
    Screen { background: #0b0f14; color: #c0caf5; }
    #topbar { height: 1; background: #111823; color: #7aa2f7; padding: 0 1; }
    #map { height: 1fr; min-height: 12; background: #0b0f14; padding: 0 1; }
    #bottom { height: 27; }
    #left { width: 56; border: round #243042; }
    #filter { height: 3; border: none; background: #111823; }
    #watch { height: 1fr; background: #0b0f14; }
    #tabs { width: 1fr; border: round #243042; }
    #country, #evidence { padding: 0 1; }
    #health { width: 46; border: round #243042; padding: 0 1; overflow-y: auto; }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("slash", "focus_filter", "Search"),
        Binding("s", "cycle_sort", "Sort"),
        Binding("a", "toggle_active", "Active only"),
        Binding("e", "tab('tab-evidence')", "Why"),
        Binding("o", "tab('tab-overview')", "Overview"),
        Binding("g", "globe", "Globe"),
        Binding("escape", "focus_table", "Table", show=False),
    ]

    def __init__(self, state: LiveState):
        super().__init__()
        self.state = state
        self.sort = "forecast"
        self.active_only = True
        self.query_text = ""

    def compose(self) -> ComposeResult:
        m = self.state.meta
        counts = self.state.countries["status"].value_counts()
        yield Static(
            Text.assemble(
                ("◉ AEGIS ", "bold #7aa2f7"), ("visibility-aware conflict forecasting", DIM),
                (f"   origin {m['origin']} · data through {m['data_through']} · {m['latest_candidate']}   ", DIM),
                (f"OK {counts.get('OK', 0)} ", STATUS_STYLE["OK"]),
                (f"WARN {counts.get('WARN', 0)} ", STATUS_STYLE["WARN"]),
                (f"ABSTAIN {counts.get('ABSTAIN', 0)}", STATUS_STYLE["ABSTAIN"]),
            ), id="topbar")
        yield WorldMap(self.state, id="map")
        with Horizontal(id="bottom"):
            with Vertical(id="left"):
                yield Input(placeholder="/ filter countries", id="filter")
                yield DataTable(id="watch", cursor_type="row", zebra_stripes=False)
            with TabbedContent(id="tabs", initial="tab-overview"):
                with TabPane("Overview", id="tab-overview"):
                    yield CountryPanel(id="country")
                with TabPane("Why (evidence)", id="tab-evidence"):
                    yield EvidencePanel(id="evidence")
            yield HealthPanel(id="health")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#watch", DataTable)
        table.add_columns("Country", "Rep", "Exp", "Vis", "Next", "Status")
        self.fill_table()
        table.focus()

    def rows(self) -> pd.DataFrame:
        df = self.state.countries
        if self.active_only:
            df = df[(df["activity12"] > 0) | (df["obs_last"] > 0)]
        if self.query_text:
            df = df[df["country"].str.contains(self.query_text, case=False, regex=False)]
        if self.sort == "forecast":
            df = df.sort_values("aegis_h1", ascending=False)
        elif self.sort == "visibility":
            df = df.sort_values("C1")
        else:
            order = {"ABSTAIN": 0, "WARN": 1, "OK": 2}
            df = df.assign(_o=df["status"].map(order)).sort_values(["_o", "aegis_h1"], ascending=[True, False])
        return df

    def fill_table(self) -> None:
        table = self.query_one("#watch", DataTable)
        table.clear()
        for _, r in self.rows().iterrows():
            style = STATUS_STYLE[r["status"]]
            table.add_row(
                Text(str(r["country"])[:16]),
                Text(f"{int(r['obs_last'])}", justify="right"),
                Text(f"{r['nowcast_last']:.0f}", justify="right"),
                Text(f"{r['C1']:.0%}", style=style, justify="right"),
                Text("—" if r["status"] == "ABSTAIN" else f"{r['aegis_h1']:.0f}", justify="right"),
                Text(r["status"], style=style),
                key=str(int(r["country_id"])),
            )
        if table.row_count:
            table.move_cursor(row=0)
            self.select(int(table.coordinate_to_cell_key((0, 0)).row_key.value))

    def select(self, country_id: int) -> None:
        row = self.state.countries.set_index("country_id").loc[country_id]
        row = row.copy()
        row["country_id"] = country_id
        self.query_one("#country", CountryPanel).show(self.state, row)
        self.query_one("#evidence", EvidencePanel).show(self.state, row)
        self.query_one("#health", HealthPanel).show(self.state, row)
        self.query_one("#map", WorldMap).select(country_id)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is not None and event.row_key.value is not None:
            self.select(int(event.row_key.value))

    def on_input_changed(self, event: Input.Changed) -> None:
        self.query_text = event.value.strip()
        self.fill_table()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.query_one("#watch", DataTable).focus()

    def action_focus_filter(self) -> None:
        self.query_one("#filter", Input).focus()

    def action_focus_table(self) -> None:
        self.query_one("#watch", DataTable).focus()

    def action_cycle_sort(self) -> None:
        self.sort = SORTS[(SORTS.index(self.sort) + 1) % len(SORTS)]
        self.notify(f"sorted by {self.sort}")
        self.fill_table()

    def action_toggle_active(self) -> None:
        self.active_only = not self.active_only
        self.notify("active countries only" if self.active_only else "all countries")
        self.fill_table()

    def action_tab(self, tab_id: str) -> None:
        self.query_one("#tabs", TabbedContent).active = tab_id

    def action_globe(self) -> None:
        self.notify("The 3D globe comes after the research results hold up (see README roadmap).",
                    title="Not in v0.1")


def run(state: LiveState) -> None:
    AegisApp(state).run()
