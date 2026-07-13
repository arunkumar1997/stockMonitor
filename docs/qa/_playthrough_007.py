"""
QA Playthrough for Issue #007 — Scheduler SSE migration.

Structured 1:1 to Remy's watch-points:

  T1  Zero polling in steady state — 0 GET /api/scheduler/status, 0 GET
      /api/logs during 15 s idle; exactly 1 GET /api/scheduler/events.
  T2  #001 regression — clean 5 s idle CDP trace: 0 UpdateLayoutTree.
  T3  Per-card refresh completes via SSE (no polling) within ≤ 1 s of
      backend "Done in Ns" log.
  T4  Duplicate-fire — 5 clicks on a spinning card = 1 POST.
  T5  Two-tab test — second tab reflects first tab's refresh via SSE.
  T6  SSE auto-reconnect after backend restart.
  T7  LogsPanel Clear/Pause/Resume semantics + backfill-once.
  T8  Global "Refresh now" cycles the header chip via fetch_started; no
      polling; no spurious per-card spinners.

Forked from _playthrough_002.py — do NOT modify that file or
_playthrough_001_v2.py or _diagnose.py.

Local artefacts (screenshots, traces, raw JSON) land in
docs/qa/screenshots/007/ and are NOT meant to be committed (covered by
chore/qa-artifacts .gitignore).

Run modes:
  python _playthrough_007.py                  # all tests except T6
  python _playthrough_007.py --with-reconnect # includes T6 (kills backend!)
"""
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/qa/screenshots/007"
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT.parent.parent / "007-perf-raw.json"
CONSOLE_LOG = OUT.parent.parent / "007-console.log"

WITH_RECONNECT = "--with-reconnect" in sys.argv

results = {
    "console_errors": [],
    "console_warnings": [],
    "page_errors": [],
    "network_failures": [],
    "network_log": [],   # main tab requests
    "network_log_tab2": [],  # T5 second tab requests
    "tests": {},
}


def stamp(name):
    return str(OUT / f"{name}.png")


def register_capture(page, net_bucket_key="network_log"):
    page.on("console", lambda m: (
        results["console_errors"].append({"type": m.type, "text": m.text})
        if m.type == "error" else
        results["console_warnings"].append({"type": m.type, "text": m.text})
        if m.type == "warning" else None
    ))
    page.on("pageerror", lambda e: results["page_errors"].append(str(e)))
    page.on("requestfailed", lambda r: results["network_failures"].append(
        {"url": r.url, "failure": r.failure}
    ))
    page.on("request", lambda r: results[net_bucket_key].append(
        {"method": r.method, "url": r.url, "t": time.time()}
    ))


async def cdp_idle_trace(cdp, page, seconds, tag):
    cats = (
        "devtools.timeline,"
        "disabled-by-default-devtools.timeline,"
        "disabled-by-default-devtools.timeline.frame,"
        "blink.user_timing"
    )
    await cdp.send("Tracing.start", {
        "categories": cats,
        "transferMode": "ReturnAsStream",
    })
    await page.wait_for_timeout(seconds * 1000)
    handle = None
    done = asyncio.Event()

    def on_c(params):
        nonlocal handle
        handle = params.get("stream")
        done.set()

    cdp.on("Tracing.tracingComplete", on_c)
    await cdp.send("Tracing.end")
    await asyncio.wait_for(done.wait(), timeout=30)
    events = []
    if handle:
        parts = []
        while True:
            ch = await cdp.send("IO.read", {"handle": handle, "size": 1024 * 1024})
            parts.append(ch.get("data", ""))
            if ch.get("eof"):
                break
        await cdp.send("IO.close", {"handle": handle})
        raw = "".join(parts)
        (OUT / f"{tag}-trace.json").write_text(raw)
        try:
            events = json.loads(raw).get("traceEvents", [])
        except Exception:
            events = []
    interesting = ["UpdateLayoutTree", "Layout", "Paint",
                   "ScheduleStyleRecalculation", "FunctionCall",
                   "TimerFire", "EventDispatch"]
    counts = {n: 0 for n in interesting}
    for e in events:
        n = e.get("name")
        if n in counts:
            counts[n] += 1
    # Long tasks
    long_tasks = 0
    for e in events:
        if e.get("name") == "RunTask" and e.get("dur", 0) > 50000:
            long_tasks += 1
    counts["_long_tasks_gt_50ms"] = long_tasks
    return counts


async def get_card_refresh_buttons(page):
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


async def get_card_symbol(page, idx):
    return await page.evaluate(f"""
        () => {{
          const cards = [...document.querySelectorAll('[class*=MuiCard-root]')];
          const c = cards[{idx}];
          const h = c && c.querySelector('h6');
          return h ? h.textContent.trim() : null;
        }}
    """)


async def find_card_by_symbol(page, symbol):
    return await page.evaluate(f"""
        () => {{
          const cards = [...document.querySelectorAll('[class*=MuiCard-root]')];
          for (let i = 0; i < cards.length; i++) {{
            const h = cards[i].querySelector('h6');
            if (h && h.textContent.trim() === {json.dumps(symbol)}) return i;
          }}
          return -1;
        }}
    """)


async def wait_spin_end(page, sel, max_iters=650):
    for _ in range(max_iters):
        an = await page.evaluate(
            f"() => {{ const b = document.querySelector({json.dumps(sel)});"
            " return b ? getComputedStyle(b).animationName : null; }"
        )
        if an != "spin":
            return True
        await page.wait_for_timeout(100)
    return False


async def wait_queue_drain(page, max_seconds=180):
    """Wait until scheduler.status().current_symbol is empty and queued==0,
    AND no card refresh buttons show the spin animation. Poll via a direct
    fetch to /api/scheduler/status (it's a one-shot GET, not the SSE stream).
    """
    import urllib.request as _u
    import urllib.error as _e
    t0 = time.time()
    while time.time() - t0 < max_seconds:
        try:
            with _u.urlopen("http://localhost:8000/api/scheduler/status", timeout=2) as r:
                s = json.loads(r.read().decode())
            if not s.get("current_symbol") and s.get("queued", 0) == 0:
                # also wait for any client-side spinners to clear
                spinning = await page.evaluate("""
                    () => [...document.querySelectorAll('button[data-qa-refresh-card]')]
                            .filter(b => getComputedStyle(b).animationName === 'spin').length
                """)
                if spinning == 0:
                    return True
        except Exception:
            pass
        await page.wait_for_timeout(500)
    return False


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()
        register_capture(page, "network_log")
        cdp = await context.new_cdp_session(page)
        try:
            await _run_tests(page, context, cdp)
        finally:
            # Always dump partial results so we can see how far we got.
            _save_report()
            await browser.close()


def _save_report():
    results["tests"]["final_console_counts"] = {
        "errors": len(results["console_errors"]),
        "warnings": len(results["console_warnings"]),
        "page_errors": len(results["page_errors"]),
        "network_failures": len(results["network_failures"]),
    }
    REPORT.write_text(json.dumps(results, indent=2, default=str))
    CONSOLE_LOG.write_text(
        f"CONSOLE ERRORS ({len(results['console_errors'])}):\n"
        + json.dumps(results["console_errors"], indent=2)
        + f"\n\nPAGE ERRORS ({len(results['page_errors'])}):\n"
        + "\n".join(results["page_errors"])
        + f"\n\nCONSOLE WARNINGS ({len(results['console_warnings'])}):\n"
        + json.dumps(results["console_warnings"], indent=2)
        + f"\n\nNETWORK FAILURES ({len(results['network_failures'])}):\n"
        + json.dumps(results["network_failures"], indent=2, default=str)
    )


async def _run_tests(page, context, cdp):

        # ─────────────────────────────────────────────────────────────
        # LOAD
        # ─────────────────────────────────────────────────────────────
        print("[LOAD]")
        t_load_0 = time.time()
        # NOTE: 'networkidle' never fires with SSE — the /api/scheduler/events
        # connection is intentionally long-lived. Use 'domcontentloaded'.
        await page.goto("http://localhost:5173", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_selector("text=DipSense", timeout=15000)
        await page.wait_for_function(
            "document.querySelectorAll('[class*=MuiCard-root]').length > 0",
            timeout=15000,
        )
        await page.wait_for_timeout(1500)
        card_count = await page.evaluate(
            "document.querySelectorAll('[class*=MuiCard-root]').length"
        )
        print(f"  cards mounted: {card_count} (took {round(time.time()-t_load_0,2)}s)")
        results["tests"]["setup"] = {"cards_mounted": card_count}
        await page.screenshot(path=stamp("00-dashboard"))

        # ─────────────────────────────────────────────────────────────
        # T1 — Zero polling in steady state
        # ─────────────────────────────────────────────────────────────
        print("[T1] zero polling in steady state (15s idle)")
        idle_start = time.time()
        # Snapshot network log length so we only count new requests.
        n_before_t1 = len(results["network_log"])
        await page.wait_for_timeout(15000)
        idle_end = time.time()
        t1_window = results["network_log"][n_before_t1:]
        status_polls = [r for r in t1_window if "/api/scheduler/status" in r["url"]]
        log_polls = [r for r in t1_window if "/api/logs" in r["url"]]
        # Also count in the FULL network log to check if there was ever an
        # EventSource opened, and confirm exactly one.
        all_events_conns = [r for r in results["network_log"]
                            if "/api/scheduler/events" in r["url"]]
        # Check EventSource state via JS. React app doesn't expose the
        # reference — but we can inspect via the browser: if no additional
        # connect happened during 15 s idle, that's our proof.
        results["tests"]["T1_zero_polling"] = {
            "window_seconds": round(idle_end - idle_start, 2),
            "status_polls_in_window": len(status_polls),
            "log_polls_in_window": len(log_polls),
            "total_scheduler_events_connections_since_load": len(all_events_conns),
            "sample_urls_in_window": [r["url"] for r in t1_window[:15]],
        }

        # ─────────────────────────────────────────────────────────────
        # T2 — #001 regression trace (idle 5s CDP)
        # ─────────────────────────────────────────────────────────────
        print("[T2] 5s idle CDP trace (#001 regression)")
        await page.wait_for_timeout(2000)
        t2_counts = await cdp_idle_trace(cdp, page, 5, "T2-idle-5s")
        results["tests"]["T2_idle_5s"] = t2_counts

        # ─────────────────────────────────────────────────────────────
        # T3 — Per-card refresh completion via SSE
        # ─────────────────────────────────────────────────────────────
        print("[T3] per-card refresh: MOTHERSON.NS (waiting for queue drain first)")
        drained = await wait_queue_drain(page, max_seconds=180)
        print(f"      queue drained: {drained}")
        card_indices = await get_card_refresh_buttons(page)
        motherson_idx = await find_card_by_symbol(page, "MOTHERSON.NS")
        if motherson_idx == -1:
            motherson_idx = card_indices[0]
            print(f"  MOTHERSON.NS not found; using idx {motherson_idx}")
        sym = await get_card_symbol(page, motherson_idx)
        sel = f'button[data-qa-refresh-card="{motherson_idx}"]'
        n_before_t3 = len(results["network_log"])
        t_click = time.time()
        await page.click(sel)
        # Check spinner + disabled state immediately.
        await page.wait_for_timeout(80)
        state_after_click = await page.evaluate(
            f"() => {{ const b = document.querySelector({json.dumps(sel)});"
            " return b ? {disabled: b.disabled, anim: getComputedStyle(b).animationName} : null; }"
        )
        # Wait for spin to end (up to 65 s — backend fetches to yfinance can
        # legitimately take 25-35 s; app safety timeout is 60 s).
        settled = await wait_spin_end(page, sel, max_iters=650)
        t_settled = time.time()
        t3_window = results["network_log"][n_before_t3:]
        posts = [r for r in t3_window
                 if r["method"] == "POST" and f"/api/scheduler/refresh/{sym}" in r["url"]]
        status_polls_t3 = [r for r in t3_window if "/api/scheduler/status" in r["url"]]
        log_polls_t3 = [r for r in t3_window if "/api/logs" in r["url"]]
        # Check the button is re-enabled after spin
        enabled_after = await page.evaluate(
            f"() => {{ const b = document.querySelector({json.dumps(sel)});"
            " return b ? !b.disabled : null; }"
        )
        elapsed = round((t_settled - t_click) * 1000, 1)
        results["tests"]["T3_per_card_refresh"] = {
            "symbol": sym,
            "spinner_+_disabled_after_click": state_after_click,
            "post_count": len(posts),
            "status_polls_during_refresh": len(status_polls_t3),
            "log_polls_during_refresh": len(log_polls_t3),
            "spin_settled": settled,
            "click_to_button_enabled_ms": elapsed,
            "safety_timeout_ms": 60000,
            "settled_before_safety_timeout": settled and elapsed < 55000,
            "button_enabled_after": enabled_after,
            "sample_urls_in_window": [r["url"] for r in t3_window[:15]],
        }
        _save_report()

        # ─────────────────────────────────────────────────────────────
        # T4 — spam-click regression check
        # ─────────────────────────────────────────────────────────────
        print("[T4] spam-click regression: 5x rapid while card A is spinning")
        card_indices = await get_card_refresh_buttons(page)
        motherson_idx = await find_card_by_symbol(page, sym)
        sel = f'button[data-qa-refresh-card="{motherson_idx}"]'
        n_before_t4 = len(results["network_log"])
        # Fire an initial fresh click, then spam-click while it's still spinning
        await page.click(sel)
        await page.wait_for_timeout(300)
        for _ in range(5):
            await page.evaluate(f"""
                () => {{
                  const b = document.querySelector({json.dumps(sel)});
                  if (!b) return;
                  b.dispatchEvent(new MouseEvent('click', {{bubbles: true, cancelable: true}}));
                }}
            """)
            await page.wait_for_timeout(80)
        await page.wait_for_timeout(500)
        t4_window = results["network_log"][n_before_t4:]
        posts_t4 = [r for r in t4_window
                    if r["method"] == "POST" and f"/api/scheduler/refresh/{sym}" in r["url"]]
        results["tests"]["T4_spam_click"] = {
            "initial_click_+_spam": "1 real click + 5 dispatched spam clicks",
            "total_post_count": len(posts_t4),
            "expected": 1,
        }
        _save_report()
        # Let the spin finish before T5
        await wait_spin_end(page, sel, max_iters=650)

        # ─────────────────────────────────────────────────────────────
        # T5 — Two-tab test
        # ─────────────────────────────────────────────────────────────
        print("[T5] two-tab test (waiting for queue drain first)")
        await wait_queue_drain(page, max_seconds=180)
        page2 = await context.new_page()
        register_capture(page2, "network_log_tab2")
        cdp2 = await context.new_cdp_session(page2)
        await page2.goto("http://localhost:5173", wait_until="domcontentloaded", timeout=30000)
        await page2.wait_for_selector("text=DipSense", timeout=15000)
        await page2.wait_for_function(
            "document.querySelectorAll('[class*=MuiCard-root]').length > 0",
            timeout=15000,
        )
        await page2.wait_for_timeout(1500)
        # Assert tab2 opened its own SSE connection
        tab2_events_conns = [r for r in results["network_log_tab2"]
                             if "/api/scheduler/events" in r["url"]]
        # Pick a fresh symbol not used in T3/T4 to distinguish. Use a
        # card in tab1 that hasn't been driven yet.
        card_indices = await get_card_refresh_buttons(page)
        driver_idx = None
        driver_sym = None
        for idx in card_indices:
            s = await get_card_symbol(page, idx)
            if s and s != sym:
                driver_idx = idx
                driver_sym = s
                break
        if driver_idx is None:
            driver_idx = card_indices[0]
            driver_sym = await get_card_symbol(page, driver_idx)
        driver_sel = f'button[data-qa-refresh-card="{driver_idx}"]'
        # Set up marker on tab2 to detect that its fetchStatus for
        # driver_sym changed. We track the card's border color / the
        # `data-` presence of a re-render marker. Simpler: poll the
        # scheduler status chip (or absence thereof) in tab2. Actually
        # the cleanest signal: tab2 must NOT fire any network request
        # for /api/scheduler/status or /api/scheduler/refresh/*, but
        # its DOM must reflect that a fetch happened.
        # We'll observe by: in tab2, snapshot the visible "Last fetch"
        # displays for driver_sym card (border colour), fire refresh in
        # tab1, then wait and re-snapshot tab2. But StockCard doesn't
        # visibly reflect fetch_status externally.
        # Best available observable: hover over the refresh icon on the
        # driver card in tab2; the tooltip text is stable. Instead let's
        # instrument via console — the app doesn't expose the store.
        # Fallback: use tab2's DOM `data-qa-*` state we set + check that
        # the tab2 EventSource received the event by observing that no
        # extra network activity occurred in tab2 during the interval.
        # We'll count tab2 requests before and after the fire.
        # Ensure driver card also exists in tab2
        driver_idx_tab2 = await find_card_by_symbol(page2, driver_sym)
        await get_card_refresh_buttons(page2)  # tag them for consistency

        # Instrument tab2: inject a small watcher that listens for
        # EventSource messages by monkey-patching the constructor. Too
        # invasive. Instead we'll rely on the network log: tab2's SSE
        # stream is one long-running response. We can't easily observe
        # SSE message arrival at the network log level (Playwright's
        # network log records requests, not chunks). So we'll instead
        # observe tab2 via the OWN status chip in Dashboard: the
        # useSchedulerStatus() hook updates current_symbol during
        # fetch_started, and clears it on fetch_finished. Poll the
        # `⟳ fetching` chip in tab2.

        # Fire refresh in tab1
        n_tab2_before = len(results["network_log_tab2"])
        t_fire = time.time()
        await page.click(driver_sel)
        # Poll tab2 for the header chip appearance/disappearance.
        # Header chip renders as: `⟳ fetching {symbol}` when
        # current_symbol is set. Track its transition.
        tab2_chip_saw_fetching = False
        tab2_chip_saw_cleared_after = False
        # We give the chip time to appear (may be quick for cached data).
        for i in range(30):  # up to 3s
            chip_text = await page2.evaluate("""
                () => {
                  const spans = [...document.querySelectorAll('span, div')];
                  const hit = spans.find(s => s.textContent && s.textContent.startsWith('⟳ fetching '));
                  return hit ? hit.textContent.trim() : null;
                }
            """)
            if chip_text and driver_sym in chip_text:
                tab2_chip_saw_fetching = True
                break
            await page2.wait_for_timeout(100)
        # Wait for spin to end in tab1
        settled_t5 = await wait_spin_end(page, driver_sel, max_iters=650)
        # After completion the chip should disappear on tab2 within 2 s
        for i in range(20):
            chip_text = await page2.evaluate("""
                () => {
                  const spans = [...document.querySelectorAll('span, div')];
                  const hit = spans.find(s => s.textContent && s.textContent.startsWith('⟳ fetching '));
                  return hit ? hit.textContent.trim() : null;
                }
            """)
            if not chip_text:
                tab2_chip_saw_cleared_after = True
                break
            await page2.wait_for_timeout(100)

        t5_window_tab2 = results["network_log_tab2"][n_tab2_before:]
        tab2_status_polls = [r for r in t5_window_tab2
                             if "/api/scheduler/status" in r["url"]]
        tab2_refresh_posts = [r for r in t5_window_tab2
                              if r["method"] == "POST"
                              and "/api/scheduler/refresh/" in r["url"]]
        results["tests"]["T5_two_tab"] = {
            "tab2_scheduler_events_connections": len(tab2_events_conns),
            "driver_symbol": driver_sym,
            "tab1_spin_settled": settled_t5,
            "tab2_saw_fetching_chip": tab2_chip_saw_fetching,
            "tab2_saw_chip_clear_after_completion": tab2_chip_saw_cleared_after,
            "tab2_status_polls_during_flow": len(tab2_status_polls),
            "tab2_refresh_posts_during_flow": len(tab2_refresh_posts),
            "tab2_elapsed_ms": round((time.time() - t_fire) * 1000, 1),
        }
        # Close tab2
        await page2.close()
        # Sanity: tab1 still responsive after tab2 closed
        tab1_alive = await page.evaluate(
            "document.querySelectorAll('[class*=MuiCard-root]').length"
        )
        results["tests"]["T5_two_tab"]["tab1_still_alive_after_tab2_close"] = tab1_alive > 0
        _save_report()

        # ─────────────────────────────────────────────────────────────
        # T7 — LogsPanel Clear/Pause/Resume semantics
        # ─────────────────────────────────────────────────────────────
        print("[T7] LogsPanel Clear/Pause/Resume (waiting for queue drain first)")
        await wait_queue_drain(page, max_seconds=180)
        # Open the LogsPanel via the ArticleIcon button in HeaderActions
        n_before_t7 = len(results["network_log"])
        await page.evaluate("""
            () => {
              const svg = document.querySelector('svg[data-testid="ArticleIcon"]');
              const btn = svg && svg.closest('button');
              if (btn) btn.click();
            }
        """)
        await page.wait_for_timeout(1500)
        t7_window = results["network_log"][n_before_t7:]
        backfill_hits = [r for r in t7_window if "/api/logs" in r["url"]]
        # Wait for entries to render
        entries_after_open = await page.evaluate("""
            () => document.querySelectorAll('[class*=MuiDrawer-paper] [class*=MuiTypography-caption]').length
        """)
        # Count log entry rows more specifically — LogsPanel renders each
        # entry as a Box containing an "ts" caption. Approximate via any
        # div inside the drawer that has text like "INFO"|"SUCCESS"|"ERROR".
        row_count_initial = await page.evaluate("""
            () => {
              const drawer = document.querySelector('[class*=MuiDrawer-paper]');
              if (!drawer) return 0;
              return [...drawer.querySelectorAll('*')].filter(el =>
                el.childNodes.length === 1 &&
                el.textContent &&
                /^(INFO|SUCCESS|ERROR|WARN)$/.test(el.textContent.trim())
              ).length;
            }
        """)

        # Trigger a refresh via a card (still in tab1). NOTE: the Drawer
        # has a MUI backdrop that intercepts pointer events, so we can't
        # use page.click() here - dispatch via JS on the underlying button.
        card_indices = await get_card_refresh_buttons(page)
        refresh_idx = card_indices[0]
        refresh_sym = await get_card_symbol(page, refresh_idx)
        refresh_sel = f'button[data-qa-refresh-card="{refresh_idx}"]'
        n_before_live = len(results["network_log"])
        await page.evaluate(f"""
            () => {{
              const b = document.querySelector({json.dumps(refresh_sel)});
              if (b) b.dispatchEvent(new MouseEvent('click', {{bubbles: true, cancelable: true}}));
            }}
        """)
        await wait_spin_end(page, refresh_sel, max_iters=650)
        await page.wait_for_timeout(1500)
        live_window = results["network_log"][n_before_live:]
        live_log_polls = [r for r in live_window if "/api/logs" in r["url"]]
        row_count_after_refresh = await page.evaluate("""
            () => {
              const drawer = document.querySelector('[class*=MuiDrawer-paper]');
              if (!drawer) return 0;
              return [...drawer.querySelectorAll('*')].filter(el =>
                el.childNodes.length === 1 &&
                el.textContent &&
                /^(INFO|SUCCESS|ERROR|WARN)$/.test(el.textContent.trim())
              ).length;
            }
        """)

        # Pause
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
        await page.wait_for_timeout(300)
        row_count_paused_start = await page.evaluate("""
            () => {
              const drawer = document.querySelector('[class*=MuiDrawer-paper]');
              if (!drawer) return 0;
              return [...drawer.querySelectorAll('*')].filter(el =>
                el.childNodes.length === 1 &&
                el.textContent &&
                /^(INFO|SUCCESS|ERROR|WARN)$/.test(el.textContent.trim())
              ).length;
            }
        """)
        # Trigger another refresh while paused (via JS — backdrop)
        card_indices = await get_card_refresh_buttons(page)
        # Pick a different card if possible
        second_idx = card_indices[1] if len(card_indices) > 1 else card_indices[0]
        second_sym = await get_card_symbol(page, second_idx)
        second_sel = f'button[data-qa-refresh-card="{second_idx}"]'
        await page.evaluate(f"""
            () => {{
              const b = document.querySelector({json.dumps(second_sel)});
              if (b) b.dispatchEvent(new MouseEvent('click', {{bubbles: true, cancelable: true}}));
            }}
        """)
        await wait_spin_end(page, second_sel, max_iters=650)
        await page.wait_for_timeout(1500)
        row_count_paused_end = await page.evaluate("""
            () => {
              const drawer = document.querySelector('[class*=MuiDrawer-paper]');
              if (!drawer) return 0;
              return [...drawer.querySelectorAll('*')].filter(el =>
                el.childNodes.length === 1 &&
                el.textContent &&
                /^(INFO|SUCCESS|ERROR|WARN)$/.test(el.textContent.trim())
              ).length;
            }
        """)
        # Resume
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
        await page.wait_for_timeout(600)
        row_count_after_resume = await page.evaluate("""
            () => {
              const drawer = document.querySelector('[class*=MuiDrawer-paper]');
              if (!drawer) return 0;
              return [...drawer.querySelectorAll('*')].filter(el =>
                el.childNodes.length === 1 &&
                el.textContent &&
                /^(INFO|SUCCESS|ERROR|WARN)$/.test(el.textContent.trim())
              ).length;
            }
        """)
        # Clear
        await page.evaluate("""
            () => {
              const btns = [...document.querySelectorAll('button')];
              const clear = btns.find(b => {
                const svg = b.querySelector('svg[data-testid="ClearAllIcon"], svg[data-testid="DeleteSweepIcon"], svg[data-testid="ClearIcon"]');
                return svg && b.closest('[class*=MuiDrawer-paper]');
              });
              if (clear) clear.click();
              window.__clearedBtnFound = !!clear;
            }
        """)
        cleared_found = await page.evaluate("() => window.__clearedBtnFound")
        await page.wait_for_timeout(400)
        row_count_after_clear = await page.evaluate("""
            () => {
              const drawer = document.querySelector('[class*=MuiDrawer-paper]');
              if (!drawer) return 0;
              return [...drawer.querySelectorAll('*')].filter(el =>
                el.childNodes.length === 1 &&
                el.textContent &&
                /^(INFO|SUCCESS|ERROR|WARN)$/.test(el.textContent.trim())
              ).length;
            }
        """)
        # Trigger one more refresh AFTER clear (via JS — backdrop)
        card_indices = await get_card_refresh_buttons(page)
        third_idx = card_indices[2] if len(card_indices) > 2 else card_indices[0]
        third_sel = f'button[data-qa-refresh-card="{third_idx}"]'
        await page.evaluate(f"""
            () => {{
              const b = document.querySelector({json.dumps(third_sel)});
              if (b) b.dispatchEvent(new MouseEvent('click', {{bubbles: true, cancelable: true}}));
            }}
        """)
        await wait_spin_end(page, third_sel, max_iters=650)
        await page.wait_for_timeout(1500)
        row_count_after_post_clear_refresh = await page.evaluate("""
            () => {
              const drawer = document.querySelector('[class*=MuiDrawer-paper]');
              if (!drawer) return 0;
              return [...drawer.querySelectorAll('*')].filter(el =>
                el.childNodes.length === 1 &&
                el.textContent &&
                /^(INFO|SUCCESS|ERROR|WARN)$/.test(el.textContent.trim())
              ).length;
            }
        """)
        results["tests"]["T7_logs_panel"] = {
            "backfill_get_logs_count_on_open": len(backfill_hits),
            "row_count_initial": row_count_initial,
            "row_count_after_live_refresh": row_count_after_refresh,
            "live_log_extra_get_polls": len(live_log_polls),
            "row_count_at_pause_start": row_count_paused_start,
            "row_count_at_pause_end_before_resume": row_count_paused_end,
            "row_count_after_resume": row_count_after_resume,
            "clear_button_found": cleared_found,
            "row_count_after_clear": row_count_after_clear,
            "row_count_after_post_clear_refresh": row_count_after_post_clear_refresh,
        }
        # Close drawer
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
        _save_report()

        # ─────────────────────────────────────────────────────────────
        # T8 — Global refresh
        # ─────────────────────────────────────────────────────────────
        print("[T8] global refresh: header chip cycles, no polling (waiting for drain)")
        await wait_queue_drain(page, max_seconds=180)
        # Tag global refresh button
        global_found = await page.evaluate("""
            () => {
              const svgs = [...document.querySelectorAll('svg[data-testid="RefreshIcon"]')];
              const global = svgs.find(s => !s.closest('[class*=MuiCard-root]'));
              if (!global) return false;
              const btn = global.closest('button');
              if (!btn) return false;
              btn.setAttribute('data-qa-global-refresh', '1');
              return true;
            }
        """)
        n_before_t8 = len(results["network_log"])
        # Note pre-click spinner state on all cards
        pre_spinning = await page.evaluate("""
            () => [...document.querySelectorAll('button[data-qa-refresh-card]')].filter(b =>
              getComputedStyle(b).animationName === 'spin'
            ).length
        """)
        await page.click('button[data-qa-global-refresh="1"]')
        # Poll for header chip cycling and cap concurrent per-card spinners.
        # Cap the observation window at 90 s regardless of queue depth (we
        # only need enough time to see the chip cycle through a few symbols).
        max_concurrent_card_spinners = 0
        chip_symbols_seen = set()
        t_t8_start = time.time()
        for _ in range(450):  # up to 90 s
            info = await page.evaluate("""
                () => {
                  const spinners = [...document.querySelectorAll('button[data-qa-refresh-card]')]
                    .filter(b => getComputedStyle(b).animationName === 'spin').length;
                  const spans = [...document.querySelectorAll('span, div')];
                  const chip = spans.find(s => s.textContent && s.textContent.trim().startsWith('⟳ fetching '));
                  const chipText = chip ? chip.textContent.trim() : null;
                  return {spinners, chipText};
                }
            """)
            max_concurrent_card_spinners = max(max_concurrent_card_spinners, info["spinners"])
            if info["chipText"]:
                chip_symbols_seen.add(info["chipText"].replace("⟳ fetching ", "").strip())
            elapsed_t8 = time.time() - t_t8_start
            # Stop once queue drained AND we've observed at least one full
            # cycle (chip appeared then cleared) OR after 90 s.
            if not info["chipText"] and elapsed_t8 > 3 and len(chip_symbols_seen) >= 2:
                break
            await page.wait_for_timeout(200)
        t8_elapsed = round(time.time() - t_t8_start, 1)
        t8_window = results["network_log"][n_before_t8:]
        status_polls_t8 = [r for r in t8_window if "/api/scheduler/status" in r["url"]]
        log_polls_t8 = [r for r in t8_window if "/api/logs" in r["url"]]
        dashboard_refreshes_t8 = [r for r in t8_window if r["url"].endswith("/api/dashboard")]
        results["tests"]["T8_global_refresh"] = {
            "global_button_found": global_found,
            "pre_click_card_spinners": pre_spinning,
            "max_concurrent_card_spinners_during_flow": max_concurrent_card_spinners,
            "chip_symbols_seen_count": len(chip_symbols_seen),
            "chip_symbols_seen_sample": list(chip_symbols_seen)[:8],
            "status_polls_during_flow": len(status_polls_t8),
            "log_polls_during_flow": len(log_polls_t8),
            "dashboard_refreshes_during_flow": len(dashboard_refreshes_t8),
            "elapsed_seconds": t8_elapsed,
        }

        # ─────────────────────────────────────────────────────────────
        # T6 — SSE auto-reconnect after backend restart
        # ─────────────────────────────────────────────────────────────
        if WITH_RECONNECT:
            print("[T6] SSE auto-reconnect after backend restart")
            # Kill backend
            print("  killing backend...")
            subprocess.run(["pkill", "-f", "uvicorn main:app"], check=False)
            await page.wait_for_timeout(3000)
            n_before_t6 = len(results["network_log"])
            # Restart backend
            print("  restarting backend...")
            backend_proc = subprocess.Popen(
                ["bash", "-c", "cd /home/arun/stockMonitor && bash start_backend.sh"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid,
            )
            # Wait for backend up (poll /api/scheduler/status)
            import urllib.request
            up = False
            for _ in range(30):
                try:
                    urllib.request.urlopen("http://localhost:8000/api/scheduler/status", timeout=1)
                    up = True
                    break
                except Exception:
                    await page.wait_for_timeout(1000)
            # Give browser some time to reconnect
            reconnect_seen = False
            reconnect_time = None
            for _ in range(15):
                await page.wait_for_timeout(1000)
                # Check for a NEW /api/scheduler/events request after restart
                t6_window = results["network_log"][n_before_t6:]
                if any("/api/scheduler/events" in r["url"] for r in t6_window):
                    reconnect_seen = True
                    reconnect_time = round(time.time() - t_click, 1)
                    break
            # Confirm UI is functional by clicking a card refresh
            card_indices = await get_card_refresh_buttons(page)
            functional_sel = f'button[data-qa-refresh-card="{card_indices[0]}"]'
            await page.click(functional_sel)
            spin_after_restart = await wait_spin_end(page, functional_sel, max_iters=650)
            results["tests"]["T6_reconnect"] = {
                "backend_up_after_restart": up,
                "eventsource_reconnect_seen": reconnect_seen,
                "post_restart_refresh_settled": spin_after_restart,
            }
        else:
            results["tests"]["T6_reconnect"] = {
                "skipped": True,
                "reason": "run with --with-reconnect to include the backend restart test",
            }

        # ─────────────────────────────────────────────────────────────
        # Wrap up
        # ─────────────────────────────────────────────────────────────

        # ---- Summary ---------------------------------------------------
        def h(t): print("\n" + "=" * 60 + f"\n{t}\n" + "=" * 60)
        h("QA PLAYTHROUGH #007 SUMMARY")
        print(f"Console errors: {len(results['console_errors'])}")
        print(f"Console warnings: {len(results['console_warnings'])}")
        print(f"Page errors: {len(results['page_errors'])}")
        print(f"Network failures: {len(results['network_failures'])}")
        for k, v in results["tests"].items():
            print(f"\n{k}: {json.dumps(v, indent=2, default=str)}")



asyncio.run(main())
