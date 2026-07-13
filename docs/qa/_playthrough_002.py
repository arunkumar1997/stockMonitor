"""
QA Playthrough for Issue #002 — per-card refresh button on StockCard.

Structured 1:1 to Nova's six watch-points:

  T1  Exactly one network request per click (+ rapid-fire debounce).
  T2  Isolated re-render (proxy: layout event counts + card BBoxes stable).
  T3  Spinner minimum-visible window ≥ 3 s.
  T4a No unmount warnings after collapsing the parent sector mid-spin.
  T4b No unmount warnings after removing the card mid-spin (attempted).
  T5  Tooltip works while the button is disabled/spinning.
  T6  Global refresh still works, no cross-interference.

Forked from _playthrough_001_v2.py — do not modify that file.
Local artefacts (screenshots, traces, raw JSON) land in
docs/qa/screenshots/002/ and are NOT meant to be committed
(covered by chore/qa-artifacts .gitignore).
"""
import asyncio
import json
import re
import time
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/qa/screenshots/002"
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT.parent.parent / "002-perf-raw.json"
CONSOLE_LOG = OUT.parent.parent / "002-console.log"

results = {
    "console_errors": [],
    "console_warnings": [],
    "page_errors": [],
    "network_failures": [],
    "network_log": [],   # all requests seen during the run
    "tests": {},
}


def stamp(name):
    return str(OUT / f"{name}.png")


async def cdp_trace(cdp, page, seconds, tag):
    """Start a CDP trace, wait N seconds, stop, return summary + raw events."""
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
    await asyncio.wait_for(done.wait(), timeout=20)
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
    by_name = {}
    for e in events:
        n = e.get("name")
        if n in interesting:
            by_name.setdefault(n, []).append(e)
    summary = {}
    for n, evs in by_name.items():
        summary[n] = {"count": len(evs)}
    return summary, events


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        # --- console + network capture --------------------------------------
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
        page.on("request", lambda r: results["network_log"].append(
            {"method": r.method, "url": r.url, "t": time.time()}
        ))

        cdp = await context.new_cdp_session(page)

        # --- load ------------------------------------------------------------
        print("[LOAD]")
        await page.goto("http://localhost:5173", wait_until="networkidle", timeout=30000)
        await page.wait_for_selector("text=DipSense", timeout=15000)
        await page.wait_for_function(
            "document.querySelectorAll('[class*=MuiCard-root]').length > 0",
            timeout=15000,
        )
        # Expand all sectors to make sure per-card refresh buttons are mounted
        await page.wait_for_timeout(1500)
        # If any sector is collapsed, click to expand — but StockCards only
        # mount inside expanded sectors, so just work with whichever the user
        # left expanded by default. Seed leaves all sectors expanded.

        card_count = await page.evaluate(
            "document.querySelectorAll('[class*=MuiCard-root]').length"
        )
        print(f"  cards mounted: {card_count}")
        await page.screenshot(path=stamp("00-dashboard"), full_page=False)

        # Helper: find the first StockCard's refresh button.
        # StockCard has: header cluster with span > IconButton > svg[data-testid=RefreshIcon]
        # HeaderActions has: same but outside a MuiCard.
        # We select refresh IconButtons that are INSIDE a MuiCard-root.
        async def get_card_refresh_buttons():
            return await page.evaluate("""
                () => {
                  const cards = [...document.querySelectorAll('[class*=MuiCard-root]')];
                  const out = [];
                  cards.forEach((card, idx) => {
                    const svg = card.querySelector('svg[data-testid="RefreshIcon"]');
                    if (svg) {
                      const btn = svg.closest('button');
                      if (btn) {
                        // Give each button a stable data-qa handle
                        btn.setAttribute('data-qa-refresh-card', String(idx));
                        out.push(idx);
                      }
                    }
                  });
                  return out;
                }
            """)
        card_indices = await get_card_refresh_buttons()
        assert card_indices, "No per-card refresh buttons found — feature not implemented?"
        first_idx = card_indices[0]
        # Which symbol does that card display?
        first_symbol = await page.evaluate(f"""
            () => {{
              const cards = [...document.querySelectorAll('[class*=MuiCard-root]')];
              const c = cards[{first_idx}];
              const h = c && c.querySelector('h6');
              return h ? h.textContent.trim() : null;
            }}
        """)
        print(f"  will drive card index={first_idx} symbol={first_symbol}")
        results["tests"]["setup"] = {
            "cards_mounted": card_count,
            "per_card_refresh_buttons": len(card_indices),
            "chosen_symbol": first_symbol,
        }

        # ================================================================
        # T1 — exactly one network request per click; rapid-fire debounce
        # ================================================================
        print("[T1] one network request per click")
        # Snapshot network log length so we only count new requests.
        n_before = len(results["network_log"])
        btn_sel = f'button[data-qa-refresh-card="{first_idx}"]'
        # Single click
        await page.click(btn_sel)
        await page.wait_for_timeout(500)
        after_single = [
            r for r in results["network_log"][n_before:]
            if f"/api/scheduler/refresh/{first_symbol}" in r["url"]
        ]
        results["tests"]["T1_single_click_refresh_requests"] = len(after_single)

        # Wait for spinner to finish so the button re-enables
        for _ in range(60):
            an = await page.evaluate(
                f"() => {{ const b = document.querySelector('{btn_sel}');"
                " return b ? getComputedStyle(b).animationName : null; }"
            )
            if an != "spin":
                break
            await page.wait_for_timeout(100)

        # Rapid-fire: 5 clicks in 500 ms
        n_before2 = len(results["network_log"])
        t0 = time.time()
        for _ in range(5):
            # Click via dispatchEvent so `disabled` truly gates us — a native
            # Playwright click on a disabled button raises, and we want to
            # confirm the *disabled* attribute is what stops the requests.
            await page.evaluate(f"""
                () => {{
                  const b = document.querySelector('{btn_sel}');
                  if (!b) return;
                  b.dispatchEvent(new MouseEvent('click', {{bubbles: true, cancelable: true}}));
                }}
            """)
            await page.wait_for_timeout(80)
        rapid_elapsed = round((time.time() - t0) * 1000)
        await page.wait_for_timeout(400)
        after_rapid = [
            r for r in results["network_log"][n_before2:]
            if f"/api/scheduler/refresh/{first_symbol}" in r["url"]
        ]
        results["tests"]["T1_rapid_fire"] = {
            "clicks_dispatched": 5,
            "elapsed_ms": rapid_elapsed,
            "refresh_requests_fired": len(after_rapid),
        }
        # Wait for spin to settle
        for _ in range(60):
            an = await page.evaluate(
                f"() => {{ const b = document.querySelector('{btn_sel}');"
                " return b ? getComputedStyle(b).animationName : null; }"
            )
            if an != "spin":
                break
            await page.wait_for_timeout(100)

        # ================================================================
        # T2 — isolated re-render proxy
        # ================================================================
        print("[T2] isolated re-render (layout events + bbox stability)")
        # BBoxes for every card
        bboxes_before = await page.evaluate("""
            () => [...document.querySelectorAll('[class*=MuiCard-root]')].map(c => {
              const r = c.getBoundingClientRect();
              return {x: Math.round(r.x), y: Math.round(r.y),
                      w: Math.round(r.width), h: Math.round(r.height)};
            })
        """)
        cards_before = len(bboxes_before)
        # Start trace covering the click and first 500 ms of spin
        cats = (
            "devtools.timeline,"
            "disabled-by-default-devtools.timeline,"
            "disabled-by-default-devtools.timeline.frame"
        )
        await cdp.send("Tracing.start", {"categories": cats,
                                         "transferMode": "ReturnAsStream"})
        await page.click(btn_sel)
        await page.wait_for_timeout(500)
        handle = None
        done_t2 = asyncio.Event()

        def on_c2(params):
            nonlocal handle
            handle = params.get("stream")
            done_t2.set()

        cdp.on("Tracing.tracingComplete", on_c2)
        await cdp.send("Tracing.end")
        await asyncio.wait_for(done_t2.wait(), timeout=20)
        raw = ""
        if handle:
            parts = []
            while True:
                ch = await cdp.send("IO.read", {"handle": handle, "size": 1024 * 1024})
                parts.append(ch.get("data", ""))
                if ch.get("eof"):
                    break
            await cdp.send("IO.close", {"handle": handle})
            raw = "".join(parts)
            (OUT / "T2-click-trace.json").write_text(raw)

        counts = {"UpdateLayoutTree": 0, "Layout": 0, "Paint": 0,
                  "ScheduleStyleRecalculation": 0}
        if raw:
            try:
                for e in json.loads(raw).get("traceEvents", []):
                    n = e.get("name")
                    if n in counts:
                        counts[n] += 1
            except Exception:
                pass
        # bboxes during-spin
        await page.screenshot(path=stamp("02-during-spin"), full_page=False)
        bboxes_during = await page.evaluate("""
            () => [...document.querySelectorAll('[class*=MuiCard-root]')].map(c => {
              const r = c.getBoundingClientRect();
              return {x: Math.round(r.x), y: Math.round(r.y),
                      w: Math.round(r.width), h: Math.round(r.height)};
            })
        """)
        # Non-clicked cards should have identical bbox
        drift = []
        for i, (b, a) in enumerate(zip(bboxes_before, bboxes_during)):
            if i == first_idx:
                continue
            if b != a:
                drift.append({"idx": i, "before": b, "during": a})
        results["tests"]["T2_isolated_render"] = {
            "cards_before": cards_before,
            "cards_during": len(bboxes_during),
            "trace_event_counts": counts,
            "other_cards_bbox_drift_count": len(drift),
            "other_cards_bbox_drift_sample": drift[:3],
        }
        # Wait for spinner to settle before next test
        for _ in range(60):
            an = await page.evaluate(
                f"() => {{ const b = document.querySelector('{btn_sel}');"
                " return b ? getComputedStyle(b).animationName : null; }"
            )
            if an != "spin":
                break
            await page.wait_for_timeout(100)

        # ================================================================
        # T3 — spinner minimum-visible window ≥ 3 s (poll every 100 ms)
        # ================================================================
        print("[T3] spinner ≥ 3 s window")
        t_click = time.time()
        await page.click(btn_sel)
        # Poll animationName until it flips off "spin"
        spin_ended_ms = None
        for i in range(80):  # up to 8 s
            elapsed = (time.time() - t_click) * 1000
            an = await page.evaluate(
                f"() => {{ const b = document.querySelector('{btn_sel}');"
                " return b ? getComputedStyle(b).animationName : null; }"
            )
            if an != "spin":
                spin_ended_ms = round(elapsed, 1)
                break
            await page.wait_for_timeout(100)
        results["tests"]["T3_spin_ms"] = spin_ended_ms

        # ================================================================
        # T4a — no unmount warnings when parent sector collapses mid-spin
        # ================================================================
        print("[T4a] collapse parent sector mid-spin")
        # Snapshot warning counts before the test
        errs_before = len(results["console_errors"])
        warns_before = len(results["console_warnings"])
        # Refresh card indices in case DOM was re-created
        card_indices = await get_card_refresh_buttons()
        target_idx = card_indices[0]
        target_btn_sel = f'button[data-qa-refresh-card="{target_idx}"]'
        target_symbol = await page.evaluate(f"""
            () => {{
              const cards = [...document.querySelectorAll('[class*=MuiCard-root]')];
              const c = cards[{target_idx}];
              const h = c && c.querySelector('h6');
              return h ? h.textContent.trim() : null;
            }}
        """)
        # Find the parent SectorSection's collapse button.
        # Each SectorSection has one Expand{Less,More}Icon button.
        # The chosen card's sector is whichever expand-button is the nearest
        # preceding sibling in DOM order. We identify the sector row by
        # walking up from the card.
        await page.evaluate(f"""
            () => {{
              const cards = [...document.querySelectorAll('[class*=MuiCard-root]')];
              const c = cards[{target_idx}];
              if (!c) return;
              // Walk up to find the MuiCollapse-root wrapping this card
              let node = c;
              while (node && !(node.classList && node.classList.contains('MuiCollapse-root'))) {{
                node = node.parentElement;
              }}
              if (!node) return;
              // The sector header row is the immediately preceding sibling
              // (either the row itself or a container wrapping it).
              let prev = node.previousElementSibling;
              while (prev && !prev.querySelector('button svg[data-testid="ExpandLessIcon"], button svg[data-testid="ExpandMoreIcon"]')) {{
                prev = prev.previousElementSibling;
              }}
              const toggleBtn = prev && prev.querySelector('button');
              if (toggleBtn) {{
                // Click the parent row (has the cursor:pointer handler)
                const row = toggleBtn.closest('div[class*=MuiBox-root]');
                (row || toggleBtn).click();
                window.__t4_toggleFound = true;
              }} else {{
                window.__t4_toggleFound = false;
              }}
            }}
        """)
        # Click refresh, then within 300 ms collapse the sector
        n_before_t4a = len(results["network_log"])
        # We already toggled once above just to test the selector; re-expand
        await page.wait_for_timeout(500)
        # Re-expand if we collapsed. Re-run same logic to toggle back.
        # Simpler: re-load the app to guarantee a clean expanded state
        # Actually, let's just re-toggle since we only clicked once.
        # If sector is now collapsed, click again to re-expand.
        # After collapse the card node is destroyed → target_idx stale.
        # Re-expand:
        collapsed_state = await page.evaluate("""
            () => {
              const cols = [...document.querySelectorAll('.MuiCollapse-root')];
              return cols.map(c => c.className).join('|');
            }
        """)
        if "MuiCollapse-hidden" in collapsed_state:
            # Re-expand all
            await page.evaluate("""
                () => {
                  document.querySelectorAll('button svg[data-testid=\"ExpandMoreIcon\"]').forEach(svg => {
                    const btn = svg.closest('button');
                    const row = btn && btn.closest('div[class*=MuiBox-root]');
                    (row || btn).click();
                  });
                }
            """)
            await page.wait_for_timeout(800)

        # Now do the real T4a: click refresh, then collapse the sector 200 ms later
        card_indices = await get_card_refresh_buttons()
        target_idx = card_indices[0]
        target_btn_sel = f'button[data-qa-refresh-card="{target_idx}"]'
        await page.click(target_btn_sel)
        await page.wait_for_timeout(200)
        await page.evaluate(f"""
            () => {{
              const cards = [...document.querySelectorAll('[class*=MuiCard-root]')];
              const c = cards[{target_idx}];
              if (!c) return;
              let node = c;
              while (node && !(node.classList && node.classList.contains('MuiCollapse-root'))) {{
                node = node.parentElement;
              }}
              if (!node) return;
              let prev = node.previousElementSibling;
              while (prev && !prev.querySelector('button svg[data-testid="ExpandLessIcon"], button svg[data-testid="ExpandMoreIcon"]')) {{
                prev = prev.previousElementSibling;
              }}
              const toggleBtn = prev && prev.querySelector('button');
              if (toggleBtn) {{
                const row = toggleBtn.closest('div[class*=MuiBox-root]');
                (row || toggleBtn).click();
              }}
            }}
        """)
        await page.wait_for_timeout(5000)  # let any state update tantrum happen
        new_errs = results["console_errors"][errs_before:]
        new_warns = results["console_warnings"][warns_before:]
        unmount_hits = [
            m for m in (new_errs + new_warns)
            if "unmounted" in m.get("text", "").lower()
            or "memory leak" in m.get("text", "").lower()
        ]
        results["tests"]["T4a_collapse_mid_spin"] = {
            "new_console_errors": len(new_errs),
            "new_console_warnings": len(new_warns),
            "unmount_warnings": len(unmount_hits),
            "unmount_warning_samples": unmount_hits[:3],
        }
        # Re-expand for next tests
        await page.evaluate("""
            () => {
              document.querySelectorAll('button svg[data-testid=\"ExpandMoreIcon\"]').forEach(svg => {
                const btn = svg.closest('button');
                const row = btn && btn.closest('div[class*=MuiBox-root]');
                (row || btn).click();
              });
            }
        """)
        await page.wait_for_timeout(1000)

        # ================================================================
        # T4b — no unmount warnings after removing the card mid-spin
        # ================================================================
        # Removal requires opening a confirm dialog. Skip: risky (mutates data)
        # and complicates cleanup. Note reason.
        results["tests"]["T4b_delete_mid_spin"] = {
            "skipped": True,
            "reason": (
                "Delete requires ConfirmDialog interaction which mutates the "
                "seeded watchlist; T4a already exercises the same unmount "
                "path via the parent sector's Collapse."
            ),
        }

        # ================================================================
        # T5 — tooltip works while button is disabled/spinning
        # ================================================================
        print("[T5] tooltip while disabled")
        card_indices = await get_card_refresh_buttons()
        t5_idx = card_indices[0]
        t5_btn_sel = f'button[data-qa-refresh-card="{t5_idx}"]'
        # click, then immediately hover (button will be disabled)
        await page.click(t5_btn_sel)
        # hover the wrapping <span> (Tooltip needs an enabled event target)
        await page.evaluate(f"""
            () => {{
              const b = document.querySelector('{t5_btn_sel}');
              const span = b && b.parentElement;
              if (span) {{
                const r = span.getBoundingClientRect();
                window.__t5_target = {{x: r.x + r.width/2, y: r.y + r.height/2}};
              }}
            }}
        """)
        target_xy = await page.evaluate("() => window.__t5_target")
        if target_xy:
            await page.mouse.move(target_xy["x"], target_xy["y"])
        # Poll for tooltip up to 2 s
        tooltip_found = False
        tooltip_text = None
        for _ in range(40):
            el = await page.query_selector('div[role="tooltip"]')
            if el:
                tooltip_text = (await el.inner_text()).strip()
                if "Refresh this stock" in tooltip_text:
                    tooltip_found = True
                    break
            await page.wait_for_timeout(50)
        # Also confirm the button is actually disabled while we hover
        disabled = await page.evaluate(f"""
            () => {{
              const b = document.querySelector('{t5_btn_sel}');
              return b ? b.disabled : null;
            }}
        """)
        results["tests"]["T5_tooltip_while_disabled"] = {
            "tooltip_found": tooltip_found,
            "tooltip_text": tooltip_text,
            "button_disabled_during_hover": disabled,
        }
        if tooltip_found:
            await page.screenshot(path=stamp("05-tooltip-while-spinning"), full_page=False)
        # move away and wait for spin to end
        await page.mouse.move(5, 5)
        for _ in range(80):
            an = await page.evaluate(
                f"() => {{ const b = document.querySelector('{t5_btn_sel}');"
                " return b ? getComputedStyle(b).animationName : null; }"
            )
            if an != "spin":
                break
            await page.wait_for_timeout(100)

        # ================================================================
        # T6 — global refresh still works, no cross-interference
        # ================================================================
        print("[T6] global refresh + per-card refresh in parallel")
        card_indices = await get_card_refresh_buttons()
        t6_idx = card_indices[0]
        t6_btn_sel = f'button[data-qa-refresh-card="{t6_idx}"]'
        t6_symbol = await page.evaluate(f"""
            () => {{
              const cards = [...document.querySelectorAll('[class*=MuiCard-root]')];
              const c = cards[{t6_idx}];
              const h = c && c.querySelector('h6');
              return h ? h.textContent.trim() : null;
            }}
        """)
        # Locate the global refresh button. It's the RefreshIcon that is
        # NOT inside a MuiCard-root — i.e. the one in HeaderActions.
        global_selector_ok = await page.evaluate("""
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
        n_before_t6 = len(results["network_log"])
        t6_click_t0 = time.time()
        await page.click(t6_btn_sel)
        # Immediately click global refresh (while per-card is spinning)
        await page.wait_for_timeout(150)
        # Give global refresh a stable click via JS (it's not disabled)
        await page.click('button[data-qa-global-refresh="1"]')
        # Wait a beat for both requests to fire
        await page.wait_for_timeout(1000)
        window = [r for r in results["network_log"][n_before_t6:]]
        per_card_hits = [
            r for r in window
            if f"/api/scheduler/refresh/{t6_symbol}" in r["url"]
        ]
        dashboard_hits = [
            r for r in window if r["url"].endswith("/api/dashboard")
        ]
        # Check that per-card spin is STILL running (its 3 s window should not
        # have ended in the ~1.2 s we've waited so far).
        still_spinning = await page.evaluate(
            f"() => {{ const b = document.querySelector('{t6_btn_sel}');"
            " return b ? getComputedStyle(b).animationName : null; }"
        )
        results["tests"]["T6_global_plus_per_card"] = {
            "global_button_found": global_selector_ok,
            "chosen_symbol": t6_symbol,
            "per_card_refresh_requests": len(per_card_hits),
            "dashboard_refresh_requests": len(dashboard_hits),
            "other_requests_sample": [
                r["url"] for r in window if "/api/" in r["url"]
            ][:8],
            "per_card_still_spinning_at_1s": still_spinning == "spin",
            "elapsed_since_per_card_click_ms": round(
                (time.time() - t6_click_t0) * 1000, 1
            ),
        }
        # Wait for both to finish before shutdown
        for _ in range(80):
            an = await page.evaluate(
                f"() => {{ const b = document.querySelector('{t6_btn_sel}');"
                " return b ? getComputedStyle(b).animationName : null; }"
            )
            if an != "spin":
                break
            await page.wait_for_timeout(100)

        # ================================================================
        # Wrap up
        # ================================================================
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

        # ---- Summary ---------------------------------------------------
        def h(t): print("\n" + "=" * 60 + f"\n{t}\n" + "=" * 60)
        h("QA PLAYTHROUGH #002 SUMMARY")
        print(f"Console errors: {len(results['console_errors'])}")
        print(f"Console warnings: {len(results['console_warnings'])}")
        print(f"Page errors: {len(results['page_errors'])}")
        print(f"Network failures: {len(results['network_failures'])}")
        for k, v in results["tests"].items():
            print(f"\n{k}: {json.dumps(v, indent=2, default=str)}")

        await browser.close()


asyncio.run(main())
