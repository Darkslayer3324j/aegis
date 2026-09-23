"""Render the terminal interface headlessly and save SVG screenshots to docs/.

    python scripts/tui_screenshot.py [name-filter] [scope]
"""

import asyncio
import sys
from pathlib import Path

from aegis import live
from aegis.tui.app import AegisApp

DOCS = Path(__file__).resolve().parents[1] / "docs"


async def main(country: str, scope: str = "world") -> None:
    DOCS.mkdir(exist_ok=True)
    app = AegisApp(live.load(scope), scope)
    prefix = "tui" if scope == "world" else f"tui_{scope}"
    async with app.run_test(size=(190, 56)) as pilot:
        await pilot.pause(0.5)
        app.save_screenshot(str(DOCS / f"{prefix}.svg"))
        await pilot.press("slash", *country, "enter")
        await pilot.pause(0.5)
        app.save_screenshot(str(DOCS / f"{prefix}_{country}.svg"))
        await pilot.press("e")
        await pilot.pause(0.5)
        app.save_screenshot(str(DOCS / f"{prefix}_{country}_evidence.svg"))
        await pilot.press("q")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "ukraine",
                     sys.argv[2] if len(sys.argv) > 2 else "world"))
