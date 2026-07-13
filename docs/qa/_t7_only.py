"""
Focused T7 re-run for #007 — LogsPanel Pause/Clear/Resume + backfill-once.

The main _playthrough_007.py driver's row-count DOM query is too strict and
returns 0 even when entries exist. This script uses a better selector
(LogRow entries have a monospace HH:MM:SS timestamp Typography element)
to give reliable counts.
"""
import asyncio
import json
import time
from playwright.async_api import async_playwright

ROW_QUERY = """
    () => {
      const drawer = document.querySelector('[class*=MuiDrawer-paper]');
      if (!drawer) return 0;
      // Log rows contain a monospace HH:MM:SS timestamp <span>.
      return [...drawer.querySelectorAll('span, p')].filter(el =>
        /^\\d{2}:\\d{2}:\\d{2}$/.test(el.textContent.trim())
      ).length;
    }
"""


async def rows(page):
    return await page.evaluate(ROW_QUERY)


async def spin_end(page, sel, max_iters=650):
    for _ in range(max_iters):
        an = await page.evaluate(
            f"() => {{ const b = document.querySelector({json.dumps(sel)});"
            " return b ? getComputedStyle(b).animationName : null; }"
        )
        if an != "spin":
            return True
        await page.wait_for_timeout(100)
    return False


async def drain(page):
    import urllib.request as _u
    for _ in range(360):
        try:
            with _u.urlopen("http://localhost:8000/api/scheduler/status", timeout=2) as r:
                s = json.loads(r.read().decode())
            spin = await page.evaluate("""
                () => [...document.querySelectorAll('button[data-qa-refresh-card]')]
                        .filter(b => getComputedStyle(b).animationName === 'spin').length
            """)
            if not s.get("current_symbol") and s.get("queued", 0) == 0 and spin == 0:
                return True
        except Exception:
            pass
        await page.wait_for_timeout(500)
    return False


async def tag_cards(page):
    return await page.evaluate("""
        () => {
          const cards = [...document.querySelectorAll('[class*=MuiCard-root]')];
          const out = [];
          cards.forEach((card, idx) => {
            const svg = card.querySelector('svg[data-testid="RefreshIcon"]');
            if (svg) {
              const btn = svg.closest('button');
              if (btn) {
                btn.setAttribute('data-qa-refresh-card', String(idx));
                out.push(idx);
              }
            }
          });
          return out;
        }
    """)


results = {"console_errors": [], "network_log": [], "steps": {}}


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()
        page.on("console", lambda m: results["console_errors"].append(m.text) if m.type == "error" else None)
        page.on("request", lambda r: results["network_log"].append({"m": r.method, "u": r.url, "t": time.time()}))
        try:
            await page.goto("http://localhost:5173", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_selector("text=DipSense", timeout=15000)
            await page.wait_for_function(
                "document.querySelectorAll('[class*=MuiCard-root]').length > 0",
                timeout=15000,
            )
            await page.wait_for_timeout(1500)
            await tag_cards(page)
            await drain(page)

            # STEP 1: open LogsPanel (backfill fires once)
            n_before = len(results["network_log"])
            await page.evaluate("""
                () => {
                  const svg = document.querySelector('svg[data-testid="ArticleIcon"]');
                  const btn = svg && svg.closest('button');
                  if (btn) btn.click();
                }
            """)
            await page.wait_for_timeout(2000)
            backfill_calls = [r for r in results["network_log"][n_before:] if "/api/logs" in r["u"]]
            rows_initial = await rows(page)
            results["steps"]["1_open_panel"] = {
                "backfill_get_logs_count": len(backfill_calls),
                "rows_after_open": rows_initial,
            }

            # STEP 2: trigger live refresh; log entries should appear WITHOUT new /api/logs
            card_indices = await tag_cards(page)
            first_idx = card_indices[0]
            sel = f'button[data-qa-refresh-card="{first_idx}"]'
            n_before_live = len(results["network_log"])
            await page.evaluate(f"""
                () => {{
                  const b = document.querySelector({json.dumps(sel)});
                  if (b) b.dispatchEvent(new MouseEvent('click', {{bubbles: true, cancelable: true}}));
                }}
            """)
            await spin_end(page, sel, max_iters=650)
            await page.wait_for_timeout(1500)
            live_window = results["network_log"][n_before_live:]
            live_log_get = [r for r in live_window if "/api/logs" in r["u"]]
            rows_after_live = await rows(page)
            results["steps"]["2_live_refresh"] = {
                "extra_get_logs_calls": len(live_log_get),
                "rows_after_live_refresh": rows_after_live,
                "rows_delta": rows_after_live - rows_initial,
            }

            # STEP 3: Pause
            await page.evaluate("""
                () => {
                  const btns = [...document.querySelectorAll('button')];
                  const pause = btns.find(b => {
                    const svg = b.querySelector('svg[data-testid="PauseIcon"]');
                    return svg && b.closest('[class*=MuiDrawer-paper]');
                  });
                  if (pause) pause.click();
                }
            """)
            await page.wait_for_timeout(500)
            rows_at_pause = await rows(page)
            # Trigger refresh #2 while paused
            second_idx = card_indices[1] if len(card_indices) > 1 else card_indices[0]
            sel2 = f'button[data-qa-refresh-card="{second_idx}"]'
            await page.evaluate(f"""
                () => {{
                  const b = document.querySelector({json.dumps(sel2)});
                  if (b) b.dispatchEvent(new MouseEvent('click', {{bubbles: true, cancelable: true}}));
                }}
            """)
            await spin_end(page, sel2, max_iters=650)
            await page.wait_for_timeout(1500)
            rows_at_pause_end = await rows(page)
            results["steps"]["3_pause"] = {
                "rows_when_pause_engaged": rows_at_pause,
                "rows_after_refresh_while_paused_should_equal_prev": rows_at_pause_end,
                "expected_no_change_while_paused": rows_at_pause == rows_at_pause_end,
            }

            # STEP 4: Resume — should catch up
            await page.evaluate("""
                () => {
                  const btns = [...document.querySelectorAll('button')];
                  const resume = btns.find(b => {
                    const svg = b.querySelector('svg[data-testid="PlayArrowIcon"]');
                    return svg && b.closest('[class*=MuiDrawer-paper]');
                  });
                  if (resume) resume.click();
                }
            """)
            await page.wait_for_timeout(800)
            rows_after_resume = await rows(page)
            results["steps"]["4_resume"] = {
                "rows_after_resume": rows_after_resume,
                "gained_entries_from_paused_period": rows_after_resume > rows_at_pause,
            }

            # STEP 5: Clear — should hide existing but new entries still show
            await page.evaluate("""
                () => {
                  const btns = [...document.querySelectorAll('button')];
                  const clear = btns.find(b => {
                    const svg = b.querySelector('svg[data-testid="DeleteSweepIcon"]');
                    return svg && b.closest('[class*=MuiDrawer-paper]');
                  });
                  if (clear) clear.click();
                }
            """)
            await page.wait_for_timeout(500)
            rows_after_clear = await rows(page)
            # New refresh should re-populate rows
            third_idx = card_indices[2] if len(card_indices) > 2 else card_indices[0]
            sel3 = f'button[data-qa-refresh-card="{third_idx}"]'
            await page.evaluate(f"""
                () => {{
                  const b = document.querySelector({json.dumps(sel3)});
                  if (b) b.dispatchEvent(new MouseEvent('click', {{bubbles: true, cancelable: true}}));
                }}
            """)
            await spin_end(page, sel3, max_iters=650)
            await page.wait_for_timeout(1500)
            rows_after_post_clear_refresh = await rows(page)
            results["steps"]["5_clear"] = {
                "rows_immediately_after_clear": rows_after_clear,
                "rows_after_new_refresh_post_clear": rows_after_post_clear_refresh,
                "clear_hides_existing": rows_after_clear < rows_after_resume,
                "new_entries_still_appear_after_clear": rows_after_post_clear_refresh > rows_after_clear,
            }
        finally:
            print(json.dumps(results, indent=2, default=str))
            await browser.close()


asyncio.run(main())
