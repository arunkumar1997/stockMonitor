"""
Targeted follow-up: verify sector toggle and diagnose 60Hz post-interaction churn.
"""
import asyncio, json, time
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/qa/screenshots/001"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        await page.goto("http://localhost:5173", wait_until="networkidle", timeout=30000)
        await page.wait_for_selector("text=DipSense")
        await page.wait_for_function(
            "document.querySelectorAll('.MuiCard-root').length > 0",
            timeout=20000,
        )
        await page.wait_for_timeout(1500)

        # ---------- A1 card count sanity ----------
        card_count = await page.evaluate("document.querySelectorAll('.MuiCard-root').length")
        print(f"MuiCard-root count: {card_count}")
        sector_count = await page.evaluate("document.querySelectorAll('h6').length")
        print(f"h6 count: {sector_count}")

        # ---------- A9 focused sector toggle ----------
        # Find the actual clickable row (has cursor:pointer and onClick)
        # The row wraps the h6 sector title. Click via its bounding box.
        rows = await page.query_selector_all(
            'h6:has-text("Pharma"), h6:has-text("Defence"), h6:has-text("Electronics"), '
            'h6:has-text("IT"), h6:has-text("ETF"), h6:has-text("Autos"), h6:has-text("Banks"), '
            'h6:has-text("Infra")'
        )
        print(f"Sector h6 candidates: {len(rows)}")
        if rows:
            # Screenshot before
            await page.screenshot(path=str(OUT / "09a-before-collapse.png"))
            # get collapse elements state
            before = await page.evaluate(
                "() => [...document.querySelectorAll('.MuiCollapse-root')].map(c=>({cls:c.className, h:c.getBoundingClientRect().height}))"
            )
            # click via bounding box of h6
            box = await rows[0].bounding_box()
            # click a little to the left to hit the parent row rather than the text
            await page.mouse.click(box["x"] + 10, box["y"] + box["height"] / 2)
            await page.wait_for_timeout(800)
            await page.screenshot(path=str(OUT / "09b-after-first-click.png"))
            mid = await page.evaluate(
                "() => [...document.querySelectorAll('.MuiCollapse-root')].map(c=>({cls:c.className, h:c.getBoundingClientRect().height}))"
            )
            # click again
            await page.mouse.click(box["x"] + 10, box["y"] + box["height"] / 2)
            await page.wait_for_timeout(800)
            await page.screenshot(path=str(OUT / "09c-after-second-click.png"))
            after = await page.evaluate(
                "() => [...document.querySelectorAll('.MuiCollapse-root')].map(c=>({cls:c.className, h:c.getBoundingClientRect().height}))"
            )
            # Detect a change in any collapse's height between before/mid/after
            changed_1 = any(b["h"] != m["h"] for b, m in zip(before, mid))
            changed_2 = any(m["h"] != a["h"] for m, a in zip(mid, after))
            print(f"toggle collapse height changed 1st: {changed_1}, 2nd: {changed_2}")
            print(f"first collapse heights before/mid/after: {before[0]['h']} / {mid[0]['h']} / {after[0]['h']}")

        # ---------- Diagnose 60Hz post-interaction churn ----------
        # Trigger a theme toggle only, then measure.
        print("\n--- diagnosing post-theme-toggle churn ---")
        cdp = await ctx.new_cdp_session(page)

        async def trace(seconds, tag):
            await cdp.send("Tracing.start", {
                "categories": "devtools.timeline,disabled-by-default-devtools.timeline,latencyInfo",
                "transferMode": "ReturnAsStream",
            })
            await page.wait_for_timeout(seconds * 1000)
            done = asyncio.Event()
            handle = None

            def onc(pp):
                nonlocal handle
                handle = pp.get("stream")
                done.set()

            cdp.on("Tracing.tracingComplete", onc)
            await cdp.send("Tracing.end")
            await asyncio.wait_for(done.wait(), timeout=10)
            parts = []
            if handle:
                while True:
                    ch = await cdp.send("IO.read", {"handle": handle, "size": 1024 * 1024})
                    parts.append(ch.get("data", ""))
                    if ch.get("eof"):
                        break
                await cdp.send("IO.close", {"handle": handle})
            raw = "".join(parts)
            (OUT / f"diag-{tag}.json").write_text(raw)
            try:
                evs = json.loads(raw).get("traceEvents", [])
            except Exception:
                evs = []
            names = ["UpdateLayoutTree", "ScheduleStyleRecalculation", "Layout",
                     "Paint", "TimerFire", "FunctionCall"]
            out = {}
            for n in names:
                c = sum(1 for e in evs if e.get("name") == n)
                out[n] = c
            return out

        # Baseline (right now, before touching anything else)
        print("baseline 5s:", await trace(5, "baseline"))

        # Toggle theme once
        for icon in ["DarkModeIcon", "LightModeIcon", "BrightnessAutoIcon"]:
            b = await page.query_selector(f'button:has(svg[data-testid="{icon}"])')
            if b:
                await b.click()
                break
        await page.wait_for_timeout(2000)
        print("after 1 theme toggle 5s:", await trace(5, "after-theme"))

        # Toggle to auto mode specifically (cycle from wherever we are to auto)
        # Track what mode we're in by icon presence
        for step in range(3):
            for icon in ["DarkModeIcon", "LightModeIcon", "BrightnessAutoIcon"]:
                b = await page.query_selector(f'button:has(svg[data-testid="{icon}"])')
                if b:
                    await b.click()
                    break
            await page.wait_for_timeout(400)
            # Check which icon is now shown
            for icon in ["DarkModeIcon", "LightModeIcon", "BrightnessAutoIcon"]:
                b = await page.query_selector(f'button:has(svg[data-testid="{icon}"])')
                if b:
                    print(f"  step {step}: now showing {icon}")
                    break
        await page.wait_for_timeout(2000)
        print("after cycling to+past auto 5s:", await trace(5, "after-cycle"))

        # Open + close logs panel
        b = await page.query_selector('button:has(svg[data-testid="ArticleIcon"])')
        await b.click()
        await page.wait_for_timeout(700)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(2000)
        print("after logs open/close 5s:", await trace(5, "after-logs"))

        # Open + close trash
        b = await page.query_selector('button:has(svg[data-testid="DeleteSweepIcon"])')
        await b.click()
        await page.wait_for_timeout(700)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(2000)
        print("after trash open/close 5s:", await trace(5, "after-trash"))

        await browser.close()


asyncio.run(main())
