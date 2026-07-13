"""
QA Playthrough v2 — corrected detection + isolated clean idle trace.

Runs 2 idle traces:
  * clean_idle: right after page load, no interaction — this is the *ticket's*
    acceptance-criteria evidence for "Dashboard rendering at most 1x over 5s".
  * post_interaction_idle: after clicking through UI, to check nothing left
    a timer running.

Then runs the full A/B checklist.
"""
import asyncio
import json
import time
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/qa/screenshots/001"
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT.parent.parent / "001-perf-raw.json"
CONSOLE_LOG = OUT.parent.parent / "001-console.log"

results = {
    "console_errors": [],
    "console_warnings": [],
    "page_errors": [],
    "network_failures": [],
    "steps": {},
    "perf": {},
}


def stamp(name):
    return str(OUT / f"{name}.png")


async def run_cdp_trace(cdp, page, seconds, tag, categories=None):
    """Start a CDP trace, wait N seconds, stop, save to file, return parsed events."""
    cats = categories or (
        "devtools.timeline,"
        "disabled-by-default-devtools.timeline,"
        "disabled-by-default-devtools.timeline.frame,"
        "blink.user_timing,latencyInfo"
    )
    await cdp.send("Tracing.start", {
        "categories": cats,
        "transferMode": "ReturnAsStream",
    })
    # Install probes
    await page.evaluate("""
        () => {
          window.__raf = 0;
          window.__lt = [];
          const t = () => { window.__raf++; requestAnimationFrame(t); };
          requestAnimationFrame(t);
          try {
            const po = new PerformanceObserver(list => {
              for (const e of list.getEntries()) {
                window.__lt.push({name: e.name, duration: e.duration, startTime: e.startTime});
              }
            });
            po.observe({entryTypes: ['longtask']});
          } catch (e) {}
          window.__t0 = performance.now();
        }
    """)
    await page.wait_for_timeout(seconds * 1000)
    probe = await page.evaluate(
        "() => ({raf: window.__raf, lt: window.__lt, ms: performance.now() - window.__t0})"
    )
    stream_handle = None
    done = asyncio.Event()

    def on_complete(params):
        nonlocal stream_handle
        stream_handle = params.get("stream")
        done.set()

    cdp.on("Tracing.tracingComplete", on_complete)
    await cdp.send("Tracing.end")
    await asyncio.wait_for(done.wait(), timeout=20)
    events = []
    if stream_handle:
        parts = []
        while True:
            ch = await cdp.send("IO.read", {"handle": stream_handle, "size": 1024 * 1024})
            parts.append(ch.get("data", ""))
            if ch.get("eof"):
                break
        await cdp.send("IO.close", {"handle": stream_handle})
        raw = "".join(parts)
        (OUT / f"{tag}-trace.json").write_text(raw)
        try:
            events = json.loads(raw).get("traceEvents", [])
        except Exception:
            events = []
    # Summarize
    interesting = ["UpdateLayoutTree", "Layout", "Paint", "FunctionCall",
                   "TimerFire", "TimerInstall", "TimerRemove",
                   "MinorGC", "MajorGC", "RunTask", "EventDispatch",
                   "ScheduleStyleRecalculation", "ParseHTML"]
    by_name = {}
    for e in events:
        n = e.get("name")
        if n in interesting:
            by_name.setdefault(n, []).append(e)
    summary = {}
    for n, evs in by_name.items():
        tss = sorted(e.get("ts", 0) for e in evs)
        gaps = [tss[i + 1] - tss[i] for i in range(len(tss) - 1)]
        durs = [e.get("dur", 0) / 1000.0 for e in evs if e.get("dur")]
        summary[n] = {
            "count": len(tss),
            "median_gap_ms": round(sorted(gaps)[len(gaps) // 2] / 1000, 3) if gaps else None,
            "total_dur_ms": round(sum(durs), 2) if durs else 0,
            "max_dur_ms": round(max(durs), 2) if durs else 0,
        }
    return {
        "trace_file": str((OUT / f"{tag}-trace.json").relative_to(ROOT)),
        "total_events": len(events),
        "by_name": summary,
        "raf_count": probe["raf"],
        "elapsed_ms": round(probe["ms"], 1),
        "long_tasks_via_PO": probe["lt"],
    }, events


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

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

        cdp = await context.new_cdp_session(page)

        # ---- A1 load ------------------------------------------------------
        print("[A1] load")
        t0 = time.time()
        await page.goto("http://localhost:5173", wait_until="networkidle", timeout=30000)
        await page.wait_for_selector("text=DipSense", timeout=15000)
        # Wait for at least one StockCard or the empty-state to be rendered
        try:
            await page.wait_for_function(
                "document.querySelectorAll('[class*=MuiCard-root]').length > 0",
                timeout=10000,
            )
        except Exception:
            pass
        await page.wait_for_timeout(1500)
        await page.screenshot(path=stamp("01-dashboard"), full_page=False)
        results["steps"]["A1_load_time_s"] = round(time.time() - t0, 2)
        card_count = await page.evaluate(
            "document.querySelectorAll('[class*=MuiCard-root]').length"
        )
        results["steps"]["A1_card_count"] = card_count

        # ---- B (primary): CLEAN idle trace right after load ---------------
        # This is the ticket's actual acceptance criterion. Do it BEFORE any
        # UI interaction so we're not measuring lingering transitions.
        print("[B-clean] 5s clean idle trace")
        # 2s settle
        await page.wait_for_timeout(2000)
        clean_summary, _ = await run_cdp_trace(cdp, page, 5, "clean-idle")
        results["perf"]["clean_idle"] = clean_summary
        # Ticket criterion: at most 1× Dashboard render → the ONLY 1Hz work
        # should be the CountdownBadge (isolated Typography). Verify:
        #   - TimerFire count ~= 5 (1Hz)
        #   - Layout count is small (<= 10; each tick paints only badge text)
        #   - No long tasks over 50ms
        tf = clean_summary["by_name"].get("TimerFire", {}).get("count", 0)
        lay = clean_summary["by_name"].get("Layout", {}).get("count", 0)
        long_ct = len(clean_summary["long_tasks_via_PO"])
        results["perf"]["clean_idle_verdict_ok"] = (
            4 <= tf <= 8 and lay <= 12 and long_ct == 0
        )
        results["perf"]["clean_idle_note"] = (
            f"TimerFire={tf} (expect ~5 for 1Hz CountdownBadge), "
            f"Layout={lay}, long_tasks>50ms={long_ct}"
        )

        # ---- A2 countdown --------------------------------------------------
        import re
        print("[A2] countdown")
        c_samples = []
        for _ in range(6):
            txt_el = await page.query_selector('text=/Updated .* · \\d+s/')
            if txt_el:
                m = re.search(r"·\s*(\d+)s", await txt_el.inner_text())
                c_samples.append(int(m.group(1)) if m else None)
            else:
                c_samples.append(None)
            await page.wait_for_timeout(1000)
        results["steps"]["A2_countdown_samples"] = c_samples
        results["steps"]["A2_countdown_ticks_ok"] = len({v for v in c_samples if v is not None}) >= 3

        # ---- A3 tooltips ---------------------------------------------------
        print("[A3] tooltips")
        icon_map = {
            "Refresh now": "RefreshIcon",
            "Trash (deleted stocks)": "DeleteSweepIcon",
            "Refresh Logs": "ArticleIcon",
            "Settings": "SettingsIcon",
        }
        tt_res = {}
        for label, icon in icon_map.items():
            btn = await page.query_selector(f'button:has(svg[data-testid="{icon}"])')
            if not btn:
                tt_res[label] = "not_found"
                continue
            t_hover = time.time()
            await btn.hover()
            appeared = False
            for _ in range(30):
                el = await page.query_selector(f'div[role="tooltip"]:has-text("{label}")')
                if el:
                    appeared = True
                    break
                await page.wait_for_timeout(50)
            tt_res[label] = {"appeared": appeared, "ms": int((time.time() - t_hover) * 1000)}
            await page.mouse.move(5, 5)
            await page.wait_for_timeout(200)
        results["steps"]["A3_tooltips"] = tt_res

        # ---- A4 refresh + spin --------------------------------------------
        print("[A4] refresh + spin")
        refresh_btn = await page.query_selector('button:has(svg[data-testid="RefreshIcon"])')
        # Hook: capture animationName immediately after click via requestAnimationFrame
        await page.evaluate("""
            () => {
              window.__spin_samples = [];
              const btn = document.querySelector('button svg[data-testid="RefreshIcon"]')?.closest('button');
              if (!btn) return;
              btn.addEventListener('click', () => {
                let n = 0;
                const sample = () => {
                  const an = getComputedStyle(btn).animationName;
                  window.__spin_samples.push({n: n++, an, t: performance.now()});
                  if (n < 40) requestAnimationFrame(sample);
                };
                requestAnimationFrame(sample);
              }, {capture: true, once: true});
            }
        """)
        t_click = time.time()
        await refresh_btn.click()
        # Wait a few frames to collect samples then screenshot
        await page.wait_for_timeout(200)
        await page.screenshot(path=stamp("02-refresh-spinning"), full_page=False)
        spin_samples = await page.evaluate("() => window.__spin_samples")
        spin_seen = any("spin" in (s.get("an") or "") for s in spin_samples)
        results["steps"]["A4_spin_seen_during_click"] = spin_seen
        results["steps"]["A4_first_spin_sample_ms"] = next(
            (round(s["t"] - spin_samples[0]["t"], 2)
             for s in spin_samples if "spin" in (s.get("an") or "")),
            None,
        )
        # Wait for spin to finish
        for _ in range(80):
            an = await refresh_btn.evaluate("el => getComputedStyle(el).animationName")
            if "spin" not in (an or ""):
                break
            await page.wait_for_timeout(100)
        results["steps"]["A4_refresh_complete_ms"] = int((time.time() - t_click) * 1000)
        # fetching chip probably won't appear (no scheduler fetch), just note it
        chip = await page.query_selector('div.MuiChip-root:has-text("fetching")')
        results["steps"]["A4_fetching_chip_seen"] = chip is not None

        # ---- A5 theme -----------------------------------------------------
        print("[A5] theme toggle")
        pre = await page.evaluate("getComputedStyle(document.body).backgroundColor")
        for icon in ["DarkModeIcon", "LightModeIcon", "BrightnessAutoIcon"]:
            tb = await page.query_selector(f'button:has(svg[data-testid="{icon}"])')
            if tb:
                await tb.click()
                break
        await page.wait_for_timeout(500)
        post = await page.evaluate("getComputedStyle(document.body).backgroundColor")
        results["steps"]["A5_pre_bg"] = pre
        results["steps"]["A5_post_bg"] = post
        results["steps"]["A5_theme_changed"] = pre != post
        await page.screenshot(path=stamp("03-after-theme-toggle"), full_page=False)
        # cycle back to dark
        for _ in range(2):
            for icon in ["DarkModeIcon", "LightModeIcon", "BrightnessAutoIcon"]:
                tb = await page.query_selector(f'button:has(svg[data-testid="{icon}"])')
                if tb:
                    await tb.click()
                    break
            await page.wait_for_timeout(400)

        # ---- Helper: detect open Drawer/Dialog properly -------------------
        async def open_drawer_visible():
            return await page.evaluate("""
                () => {
                  const nodes = [
                    ...document.querySelectorAll('.MuiDrawer-paper'),
                    ...document.querySelectorAll('.MuiDialog-paper'),
                    ...document.querySelectorAll('[role=dialog]'),
                  ];
                  return nodes.some(n => {
                    const r = n.getBoundingClientRect();
                    return r.width > 20 && r.height > 20;
                  });
                }
            """)

        # ---- A6 logs ------------------------------------------------------
        print("[A6] logs panel")
        logs_btn = await page.query_selector('button:has(svg[data-testid="ArticleIcon"])')
        await logs_btn.click()
        await page.wait_for_timeout(700)
        results["steps"]["A6_logs_panel_visible"] = await open_drawer_visible()
        await page.screenshot(path=stamp("04-logs-panel"), full_page=False)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)

        # ---- A7 settings --------------------------------------------------
        print("[A7] settings")
        sb = await page.query_selector('button:has(svg[data-testid="SettingsIcon"])')
        await sb.click()
        await page.wait_for_timeout(700)
        results["steps"]["A7_settings_visible"] = await open_drawer_visible()
        await page.screenshot(path=stamp("05-settings"), full_page=False)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)

        # ---- A8 trash -----------------------------------------------------
        print("[A8] trash")
        tb = await page.query_selector('button:has(svg[data-testid="DeleteSweepIcon"])')
        await tb.click()
        await page.wait_for_timeout(700)
        results["steps"]["A8_trash_visible"] = await open_drawer_visible()
        await page.screenshot(path=stamp("06-trash"), full_page=False)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)

        # ---- A9 sector expand/collapse ------------------------------------
        print("[A9] sector toggle")
        # The clickable row is the parent Box of the h6+chip+expand-icon. It
        # has cursor:pointer. Click via the Box wrapping the ExpandMore/Less
        # icon which is easier to locate.
        toggle_before = await page.evaluate("""
            () => document.querySelectorAll('[class*=MuiCollapse-entered], [class*=MuiCollapse-hidden]').length
        """)
        # click via first expand button (each SectorSection has one)
        expand_btns = await page.query_selector_all(
            'button:has(svg[data-testid="ExpandLessIcon"]), '
            'button:has(svg[data-testid="ExpandMoreIcon"])'
        )
        sector_ok = False
        if expand_btns:
            # click the *parent Box* (which has the onClick); do it by clicking
            # the button and letting the event bubble
            first = expand_btns[0]
            # Get initial collapse state of the sibling Collapse element
            state_before = await page.evaluate("""
                () => {
                  const cols = document.querySelectorAll('.MuiCollapse-root');
                  return [...cols].map(c => c.className);
                }
            """)
            # Click the parent box (the row with cursor:pointer)
            await first.evaluate(
                "el => { const box = el.closest('div[class*=MuiBox-root]'); box && box.click(); }"
            )
            await page.wait_for_timeout(700)
            await page.screenshot(path=stamp("07-sector-collapsed"), full_page=False)
            state_mid = await page.evaluate("""
                () => [...document.querySelectorAll('.MuiCollapse-root')].map(c => c.className)
            """)
            # click again to re-expand
            await first.evaluate(
                "el => { const box = el.closest('div[class*=MuiBox-root]'); box && box.click(); }"
            )
            await page.wait_for_timeout(700)
            await page.screenshot(path=stamp("08-sector-reexpanded"), full_page=False)
            state_after = await page.evaluate("""
                () => [...document.querySelectorAll('.MuiCollapse-root')].map(c => c.className)
            """)
            sector_ok = (state_before != state_mid) and (state_mid != state_after)
        results["steps"]["A9_sector_toggled"] = sector_ok

        # ---- B (secondary): post-interaction idle trace -------------------
        print("[B-post] 5s post-interaction idle trace")
        await page.wait_for_timeout(2000)
        post_summary, _ = await run_cdp_trace(cdp, page, 5, "post-interaction-idle")
        results["perf"]["post_interaction_idle"] = post_summary

        # ---- B4 click latency ---------------------------------------------
        print("[B4] click latency")
        # Fresh probe
        await page.evaluate("""
            () => {
              window.__clk = [];
              const el = document.querySelector('button svg[data-testid="RefreshIcon"]')?.closest('button');
              el?.addEventListener('click', () => {
                window.__clk.push({e: 'click', t: performance.now()});
                requestAnimationFrame(() => window.__clk.push({e: 'raf1', t: performance.now()}));
                requestAnimationFrame(() => requestAnimationFrame(() => window.__clk.push({e: 'raf2', t: performance.now()})));
              }, {capture: true, once: true});
            }
        """)
        # Start CDP trace, click, stop
        await cdp.send("Tracing.start", {
            "categories": "devtools.timeline,disabled-by-default-devtools.timeline,latencyInfo",
            "transferMode": "ReturnAsStream",
        })
        rb = await page.query_selector('button:has(svg[data-testid="RefreshIcon"])')
        await rb.click()
        await page.wait_for_timeout(400)
        stream = None
        done = asyncio.Event()
        cdp.on("Tracing.tracingComplete", lambda p: (setattr(main, "_s", p.get("stream")), done.set()))

        async def _stop_and_capture():
            handle = None

            def on_c(params):
                nonlocal handle
                handle = params.get("stream")
                done.set()

            cdp.on("Tracing.tracingComplete", on_c)
            await cdp.send("Tracing.end")
            await asyncio.wait_for(done.wait(), timeout=10)
            if handle:
                parts = []
                while True:
                    ch = await cdp.send("IO.read", {"handle": handle, "size": 1024 * 1024})
                    parts.append(ch.get("data", ""))
                    if ch.get("eof"):
                        break
                await cdp.send("IO.close", {"handle": handle})
                (OUT / "click-trace.json").write_text("".join(parts))

        await _stop_and_capture()
        marks = await page.evaluate("() => window.__clk")
        latency = None
        if len(marks) >= 2:
            latency = round(marks[1]["t"] - marks[0]["t"], 2)
        results["perf"]["click"] = {
            "marks": marks,
            "click_to_raf1_ms": latency,
            "trace_file": "docs/qa/screenshots/001/click-trace.json",
        }
        results["perf"]["click_verdict_ok"] = latency is not None and latency < 50

        # Wait for spin to complete before closing
        for _ in range(60):
            an = await rb.evaluate("el => getComputedStyle(el).animationName")
            if "spin" not in (an or ""):
                break
            await page.wait_for_timeout(100)

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

        # ---- Summary print ------------------------------------------------
        def h(t): print("\n" + "=" * 60 + f"\n{t}\n" + "=" * 60)
        h("QA PLAYTHROUGH v2 SUMMARY")
        print(f"Console errors: {len(results['console_errors'])}")
        print(f"Page errors:    {len(results['page_errors'])}")
        print(f"Console warnings: {len(results['console_warnings'])}")
        print(f"Network failures: {len(results['network_failures'])}")
        h("Test A")
        for k, v in results["steps"].items():
            print(f"  {k}: {v}")
        h("Test B — CLEAN idle 5s (primary criterion)")
        print(json.dumps(results["perf"]["clean_idle"]["by_name"], indent=2))
        print(f"  raf_count={results['perf']['clean_idle']['raf_count']} "
              f"long_tasks(PO)={len(results['perf']['clean_idle']['long_tasks_via_PO'])}")
        print(f"  VERDICT: {results['perf']['clean_idle_verdict_ok']}  "
              f"({results['perf']['clean_idle_note']})")
        h("Test B — POST-INTERACTION idle 5s")
        print(json.dumps(results["perf"]["post_interaction_idle"]["by_name"], indent=2))
        print(f"  raf_count={results['perf']['post_interaction_idle']['raf_count']}")
        h("Test B — Click latency")
        print(json.dumps(results["perf"]["click"], indent=2))

        await browser.close()


asyncio.run(main())
