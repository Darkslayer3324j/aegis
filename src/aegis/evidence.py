"""Plain-language evidence summaries: why AEGIS says what it says about a country.

Every sentence is a fixed template filled from numbers the model actually used. There is
no free-text generation. The wording rules in SCOPE.md are enforced by
``tests/test_evidence.py``:

* describe evidence, never "danger" or "safety", and give no advice;
* visibility comes first; at ABSTAIN no forecast number is shown;
* low counts are always paired with their visibility (a quiet feed is not a quiet world);
* every summary carries the same footer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

FOOTER = ("Counts of past recorded events and a statistical estimate of future ones. "
          "Not a statement about personal safety. Not travel or security advice. "
          "Source: UCDP (CC BY 4.0), organised violence with at least one death.")

# Words the summary must never use (SCOPE.md). Checked by the tests.
BANNED = re.compile(r"\b(dangerous|danger|safe|unsafe|threat|threats|risk level|avoid|evacuate|flee)\b",
                    re.IGNORECASE)


@dataclass
class Evidence:
    country: str
    status: str
    headline: str
    points: list[tuple[str, str]] = field(default_factory=list)  # (label, sentence)
    footer: str = FOOTER
    shows_number: bool = True

    def text(self) -> str:
        lines = [self.headline, ""]
        lines += [f"- {label}: {s}" for label, s in self.points]
        return "\n".join(lines + ["", self.footer])


def _events(x: float) -> str:
    n = int(round(x))
    return f"{n} event" if n == 1 else f"{n} events"


def _pct(x: float) -> str:
    return f"{x:.0%}"


# UCDP type_of_violence, described without naming any actor.
VIOLENCE_TYPES = {
    1: "fighting between the state and armed groups",
    2: "fighting between non-state armed groups",
    3: "armed groups or the state attacking civilians",
}


def composition_sentence(counts: dict[int, int]) -> str | None:
    total = sum(counts.values())
    if total == 0:
        return None
    parts = [f"{n} were {VIOLENCE_TYPES[t]}" for t, n in sorted(counts.items(), key=lambda kv: -kv[1])
             if n and t in VIOLENCE_TYPES]
    if len(parts) > 1:
        parts[-1] = "and " + parts[-1]
    return f"of {total} recorded events in the last 3 months, " + ", ".join(parts) + "."


def build(row: pd.Series, series: pd.DataFrame, track: pd.Series | None = None,
          composition: dict[int, int] | None = None) -> Evidence:
    """Summary for one country (or province, in a national scope).

    ``row``: one row of the live countries table. ``series``: that country's last 24 months
    (columns m, observed, nowcast, is_final). ``track``: optional backtest record with
    ``miss`` (share outside the 80% range), ``n``, ``nbar`` and ``nbar+vis`` (mean CRPS).
    """
    name, status = str(row["country"]), str(row["status"])
    c1 = float(row["C1"])
    month = str(series["m"].iloc[-1]) if len(series) else "the newest month"
    obs = series["observed"].to_numpy(float)
    ma3 = float(obs[-3:].mean()) if len(obs) else 0.0
    ma12 = float(obs[-12:].mean()) if len(obs) else 0.0
    ev = Evidence(country=name, status=status, headline="")

    # Headline: a range, never a verdict. No number at all when abstaining.
    if status == "ABSTAIN":
        ev.shows_number = False
        ev.headline = (f"AEGIS does not estimate {name} for next month: the reporting from here is "
                       f"too incomplete, or has gone silent, to support a reliable number.")
    else:
        ev.headline = (f"AEGIS expects roughly {int(row['aegis_h1_lo'])}–{int(row['aegis_h1_hi'])} "
                       f"recorded violent events in {name} next month (80% range; central estimate "
                       f"{row['aegis_h1']:.0f}).")

    # 1. Visibility first.
    if c1 > 1.05:
        vis = (f"first releases from here have historically contained more events than the final "
               f"record (about {_pct(c1)} of it), because some early reports are later removed. "
               f"AEGIS scales recent counts down accordingly.")
    elif status == "OK":
        vis = (f"reporting looks reasonably complete. First releases from here have historically "
               f"captured about {_pct(c1)} of the events eventually recorded.")
    else:
        vis = (f"reporting from here looks incomplete, so real activity may be higher than shown. "
               f"First releases have historically captured only about {_pct(c1)} of the events "
               f"eventually recorded.")
    if float(row["volatility"]) > 1.0:
        vis += " Counts here are often heavily revised after first release."
    ev.points.append(("Visibility", vis))

    if bool(row["dark"]):
        ev.points.append(("Silent feed", (
            f"nothing has been reported for {month}, although {name} averaged "
            f"{row['activity12']:.1f} recorded events a month over the past year. A quiet feed is "
            f"not a quiet world: an empty report can mean events have not surfaced yet.")))

    # 2. What the newest data says, and what it is expected to become.
    if status != "ABSTAIN":
        ev.points.append(("Newest month", (
            f"{_events(row['obs_last'])} reported so far for {month}; AEGIS expects about "
            f"{row['nowcast_last']:.0f} once reporting catches up (80% range "
            f"{int(row['nowcast_lo'])}–{int(row['nowcast_hi'])}).")))

    # 3. Recent trend in the recorded data.
    if ma12 > 0 or ma3 > 0:
        if ma3 > 1.15 * ma12 + 0.5:
            direction = "above"
        elif ma3 < 0.87 * ma12 - 0.5:
            direction = "below"
        else:
            direction = "in line with"
        ev.points.append(("Recent trend", (
            f"recorded activity over the last 3 months averaged {ma3:.1f} events a month, "
            f"{direction} the 12-month average of {ma12:.1f}.")))
    else:
        ev.points.append(("Recent trend", (
            "no recorded events in the last 12 months. That is a statement about the record, not "
            "evidence that nothing is happening.")))

    if composition and (sentence := composition_sentence(composition)):
        ev.points.append(("Kind of violence", sentence))

    # 4. Why AEGIS differs from a simple model, and what lies further ahead.
    if status != "ABSTAIN":
        base, aeg = float(row["base_h1"]), float(row["aegis_h1"])
        if abs(aeg - base) > max(0.1 * base, 1.0):
            word = "higher" if aeg > base else "lower"
            ev.points.append(("Correction", (
                f"a simple model that takes recent counts at face value expects about {base:.0f}; "
                f"AEGIS's estimate is {word} because it adjusts recent months for incomplete or "
                f"over-complete reporting.")))
        else:
            ev.points.append(("Correction", (
                f"a simple model that takes recent counts at face value expects about {base:.0f}, "
                f"close to AEGIS's estimate, so the reporting adjustment matters little here.")))
        ev.points.append(("Further ahead", (
            f"about {row['aegis_h2']:.0f} recorded events in two months and {row['aegis_h3']:.0f} "
            f"in three, with wider uncertainty.")))
        if float(row["aegis_h1"]) < 1:
            ev.points.append(("Low count", (
                "few or no recorded events are expected. This reflects the record only, not "
                "evidence that nothing is happening.")))

    # 5. Track record: how often AEGIS has been wrong here.
    if track is not None and int(track.get("n", 0)) > 0:
        line = (f"in backtests, the outcome fell outside AEGIS's 80% range "
                f"{_pct(float(track['miss']))} of the time here ({int(track['n'])} forecasts; a "
                f"well-calibrated range misses about 20%).")
        b, a = track.get("nbar"), track.get("nbar+vis")
        if b is not None and a is not None and pd.notna(a) and pd.notna(b):
            better = "more" if a < b else "less"
            line += f" AEGIS was {better} accurate than the simple model here (CRPS {a:.2f} vs {b:.2f})."
        ev.points.append(("Track record", line))
    else:
        ev.points.append(("Track record", "no backtest record for this country yet."))
    return ev
