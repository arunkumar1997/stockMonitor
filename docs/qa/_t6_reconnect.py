"""
Focused T6 for #007 — SSE auto-reconnect after backend restart.

Steps:
  1. Open browser; confirm 1 EventSource connection to /api/scheduler/events.
  2. Kill the backend (uvicorn).
  3. Wait ~3s; observe the browser sees the connection error (readyState != 1
     for a moment).
  4. Restart the backend.
  5. Wait up to 15s; observe browser reconnects (a NEW GET /api/scheduler/events
     request appears in the network log).
  6. Verify UI functional: trigger a per-card refresh and confirm the spinner
     eventually clears via SSE (not the 60s safety timeout).
"""
import asyncio
import json
import os
import subprocess
import time
import urllib.request
from playwright.async_api import async_playwright


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


async def wait_backend_up(seconds=30):
    t0 = time.time()
    while time.time() - t0 < seconds:
        try:
            urllib.request.urlopen("http://localhost:8000/api/scheduler/status", timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


results = {"console_errors": [], "network_log": [], "steps": {}}


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()
        page.on("console", lambda m: results["console_errors"].append({"t": m.type, "text": m.text}) if m.type in ("error", "warning") else None)
        page.on("request", lambda r: results["network_log"].append({"m": r.method, "u": r.url, "t": time.time()}))
        try:
            await page.goto("http://localhost:5173", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_selector("text=DipSense", timeout=15000)
            await page.wait_for_function(
                "document.querySelectorAll('[class*=MuiCard-root]').length > 0",
                timeout=15000,
            )
            await page.wait_for_timeout(2000)

            n_before_kill = len(results["network_log"])
            sse_connects_before = [r for r in results["network_log"]
                                   if "/api/scheduler/events" in r["u"]]
            results["steps"]["1_initial_state"] = {
                "sse_connections_after_load": len(sse_connects_before),
            }

            # STEP 2: kill backend cleanly (kill everything on port 8000)
            print("[T6] killing backend...")
            t_kill = time.time()
            # fuser -k kills all processes with the port open; -TERM first,
            # then -KILL for anything that survives.
            subprocess.run(["fuser", "-k", "-TERM", "8000/tcp"], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            await page.wait_for_timeout(1500)
            subprocess.run(["fuser", "-k", "-KILL", "8000/tcp"], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["pkill", "-9", "-f", "uvicorn main:app"], check=False)
            subprocess.run(["pkill", "-9", "-f", "start_backend.sh"], check=False)
            # Wait for port 8000 to actually free up
            for _ in range(20):
                await page.wait_for_timeout(500)
                try:
                    urllib.request.urlopen("http://localhost:8000/api/scheduler/status", timeout=1)
                    # still up — keep waiting
                except Exception:
                    break

            # STEP 3: confirm dead
            try:
                urllib.request.urlopen("http://localhost:8000/api/scheduler/status", timeout=1)
                backend_actually_dead = False
            except Exception:
                backend_actually_dead = True
            results["steps"]["2_kill_backend"] = {
                "backend_dead_confirmed": backend_actually_dead,
                "seconds_from_kill_to_dead": round(time.time() - t_kill, 2),
            }

            # STEP 4: restart backend as a fully detached daemon.
            print("[T6] restarting backend...")
            t_restart = time.time()
            backend_proc = subprocess.Popen(
                "cd /home/arun/stockMonitor && bash start_backend.sh > /tmp/backend_t6.log 2>&1",
                shell=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            up = await wait_backend_up(30)
            print(f"[T6] backend up after restart: {up}")
            results["steps"]["3_restart_backend"] = {
                "backend_reachable_after_restart": up,
                "seconds_to_reachable": round(time.time() - t_restart, 2),
            }

            # STEP 5: wait for browser SSE reconnect (new /api/scheduler/events request)
            reconnect_seen = False
            reconnect_wait_start = time.time()
            for _ in range(20):
                await page.wait_for_timeout(1000)
                new_sse = [r for r in results["network_log"][n_before_kill:]
                           if "/api/scheduler/events" in r["u"]]
                if new_sse:
                    reconnect_seen = True
                    break
            reconnect_time = round(time.time() - reconnect_wait_start, 2)
            results["steps"]["4_sse_reconnect"] = {
                "reconnected": reconnect_seen,
                "seconds_from_backend_up_to_reconnect": reconnect_time,
            }

            # STEP 6: functional test — click a per-card refresh, wait for spin to end
            if reconnect_seen:
                cards = await page.evaluate("""
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
                if cards:
                    idx = cards[0]
                    sel = f'button[data-qa-refresh-card="{idx}"]'
                    t_click = time.time()
                    await page.click(sel)
                    settled = await spin_end(page, sel, max_iters=650)
                    elapsed = round((time.time() - t_click) * 1000, 1)
                    results["steps"]["5_functional_post_reconnect"] = {
                        "spin_settled": settled,
                        "elapsed_ms": elapsed,
                        "cleared_via_sse_not_safety_timeout": settled and elapsed < 55000,
                    }

            # Check for the header "fetching X" chip is empty (no in-flight after restart)
            chip = await page.evaluate("""
                () => {
                  const spans = [...document.querySelectorAll('span, div')];
                  const hit = spans.find(s => s.textContent && s.textContent.trim().startsWith('⟳ fetching '));
                  return hit ? hit.textContent.trim() : null;
                }
            """)
            results["steps"]["6_header_chip_after_restart"] = {
                "chip_text": chip,
                "empty_as_expected": chip is None,
            }
        finally:
            results["console_error_count"] = len(results["console_errors"])
            print(json.dumps({k: v for k, v in results.items() if k != "network_log"}, indent=2, default=str))
            await browser.close()


asyncio.run(main())
