"""Render the terminal interface headlessly and save SVG screenshots to docs/.

    python scripts/tui_screenshot.py [country-filter]
"""

import asyncio
import sys
from pathlib import Path

from aegis import live
from aegis.tui.app import AegisApp

DOCS = Path(__file__).resolve().parents[1] / "docs"


async def main(country: str) -> None:
    DOCS.mkdir(exist_ok=True)
    app = AegisApp(live.load())
    async with app.run_test(size=(190, 56)) as pilot:
        await pilot.pause(0.5)
        app.save_screenshot(str(DOCS / "tui.svg"))
        await pilot.press("slash", *country, "enter")
        await pilot.pause(0.5)
        app.save_screenshot(str(DOCS / f"tui_{country}.svg"))
        await pilot.press("e")
        await pilot.pause(0.5)
        app.save_screenshot(str(DOCS / f"tui_{country}_evidence.svg"))
        await pilot.press("q")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "ukraine"))
