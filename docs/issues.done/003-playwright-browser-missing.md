# Issue #003 — Playwright browser missing → `refresh` returns no data

**Type:** bug
**Severity:** blocker (all data fetches fail; dashboard shows empty/stale)
**Area:** backend / setup
**Reporter:** CEO
**Triaged by:** Remy (Producer)
**Assignee:** Sage (Backend), with an assist from Dash (setup script)

---

## Symptom

Triggering a manual refresh returns HTTP 200 but no data is fetched. Backend logs:

```
[scheduler] [MOTHERSON.NS] ℹ Starting refresh …
INFO:     127.0.0.1:34848 - "POST /api/scheduler/refresh/MOTHERSON.NS HTTP/1.1" 200 OK
[scheduler] [MOTHERSON.NS] ℹ Fetching 6mo OHLCV history …
[fetcher] History error for MOTHERSON.NS: BrowserType.launch: Executable doesn't exist at /home/arun/.cache/ms-playwright/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell
╔════════════════════════════════════════════════════════════╗
║ Looks like Playwright was just installed or updated.       ║
║ Please run the following command to download new browsers: ║
║                                                            ║
║     playwright install                                     ║
║                                                            ║
║ <3 Playwright Team                                         ║
╚════════════════════════════════════════════════════════════╝
[scheduler] [MOTHERSON.NS] ⚠ No price history returned — skipping
```

Reproducer:
```bash
curl -X POST http://localhost:8000/api/scheduler/refresh/MOTHERSON.NS
```

## Root cause

`backend/data/fetcher.py` uses Playwright to scrape data (per its module docstring — [backend/data/fetcher.py#L2](backend/data/fetcher.py#L2)) and `playwright==1.59.0` is in [backend/requirements.txt#L47](backend/requirements.txt#L47), but **`playwright install` was never run** on this machine, so no Chromium binary exists at `~/.cache/ms-playwright/`. The Python package is installed but its browser dependency is not.

[start_backend.sh](start_backend.sh) only runs `pip install -r requirements.txt` — it does **not** run `playwright install`.

The fetcher swallows the error and returns nothing, so the scheduler happily logs "No price history returned — skipping" and moves on. That's why the API responds 200 despite total failure.

## Fix plan

### Must-fix (unblocks the CEO's machine right now)

- [ ] **Immediate manual unblock (one-liner for the CEO to run now):**
  ```bash
  cd backend && source venv/bin/activate && playwright install chromium
  ```
  Only `chromium` is needed — no need to download firefox/webkit.

### Must-fix (permanent — Dash)

- [ ] Update [start_backend.sh](start_backend.sh) so first-time setup also installs the browser. After `pip install -r requirements.txt`, add:
  ```bash
  # Ensure Playwright's Chromium is present (no-op if already installed)
  echo "🎭 Ensuring Playwright Chromium is installed..."
  python -m playwright install chromium
  ```
  Note: use `python -m playwright install chromium` (not bare `playwright install`) so we always hit the venv's copy. `playwright install` is idempotent and cheap when the browser is already present — safe to run every start.
- [ ] If we care about Linux CI/servers: also document (or auto-run) `python -m playwright install-deps chromium` for system libs (needs sudo — do **not** silently sudo in the start script; just document it in the README).

### Should-fix (Sage — hardening)

- [ ] **The scheduler must not report success when a fetch fails.**
  - `POST /api/scheduler/refresh/{symbol}` currently returns 200 immediately because the fetch happens in a background thread ([backend/main.py#L189-L203](backend/main.py#L189-L203)). That's fine as-is (fire-and-forget), but the **scheduler status** endpoint should expose a per-symbol `last_fetch_status` (`ok` / `error` + message + timestamp) so the UI can surface failures.
  - Add a "last error" chip to `/api/scheduler/status` output for symbols whose most recent fetch raised.
- [ ] **Detect the specific "browser missing" Playwright error** in `fetcher.py` and log a clear, actionable message once at startup instead of on every fetch:
  ```
  [fetcher] Playwright Chromium is not installed. Run: python -m playwright install chromium
  ```
  Prevents log spam and gives a fix in the error itself.
- [ ] Add a `/health` check that also verifies Playwright can launch a browser once at startup (fail loudly rather than silently degrade).

### Nice-to-have

- [ ] Update [README.md](README.md) with a "Prerequisites" section calling out `playwright install chromium` and system deps for Linux.
- [ ] If we ever add CI, cache `~/.cache/ms-playwright` between runs (Dash).

## Success criteria

- Fresh clone → `./start_backend.sh` → `curl -X POST http://localhost:8000/api/scheduler/refresh/MOTHERSON.NS` → logs show `✔ Refresh complete` (or equivalent), no Playwright error.
- `GET /api/scheduler/status` exposes per-symbol last-fetch status including failures.
- Frontend can (in a future issue) show a small "!" badge on cards whose last fetch errored.

## Out of scope

- Switching away from Playwright / back to yfinance.
- Adding retry logic to the fetcher (separate issue if wanted).
- UI to surface fetch errors (file follow-up once the status endpoint is enriched).

## Branch / PR

- Branch: `fix/playwright-browser-install`
- PR title: `fix: auto-install Playwright Chromium + surface fetch errors (Fixes #003)`
- Split commits:
  1. `chore(setup): install playwright chromium in start_backend.sh`
  2. `fix(fetcher): detect missing browser and log actionable message`
  3. `feat(scheduler): expose per-symbol last_fetch_status in /api/scheduler/status`
- Priority: **do this before shipping #001/#002 to prod** — a UI perf fix on an empty dashboard is pointless.
