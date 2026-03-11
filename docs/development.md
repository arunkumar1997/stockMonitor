# DipSense — Developer Guide

This guide explains how to extend, modify, and contribute to the codebase.

---

## Adding a New Stock

### Via the UI
Click the **+** FAB button on the dashboard → enter ticker symbol + name.

### Via API
```bash
curl -X POST http://localhost:8000/api/stocks \
  -H "Content-Type: application/json" \
  -d '{"symbol": "TITAN.NS", "name": "Titan Company", "sector": "Consumer"}'
```

### Bulk via seed_db.py
Edit `backend/stocks.json` (add entries), then re-run:
```bash
cd backend && python seed_db.py   # safe to re-run, skips existing
```

---

## Adding a New Sector

Sectors are a free-text field on each watchlist entry — no enum needed. Just use the new sector name when adding a stock.

To add an **icon** for the new sector, edit `Dashboard.jsx`:
```js
// frontend/src/components/Dashboard.jsx
const SECTOR_ICONS = {
  "Pharma": "💊",
  "Defence": "🛡️",
  "Your Sector": "🆕",   // ← add here
};
```

---

## Adding a New Config Key (Settings)

All runtime parameters live in the `app_config` table. To add a new one:

**1. Add a default row** in `backend/data/store.py` → `_DEFAULT_CONFIG` list:
```python
("my_new_param", "42", "int", "My Label",
 "Tooltip description shown in the Settings UI.", "Dip Detection"),
```
Types: `"str"` | `"int"` | `"float"` | `"json_list"` (JSON array of strings)

**2. Read it in the relevant module:**
```python
# In analysis.py load_config() or news.py _get_cfg()
"my_new_param": store.config_get("my_new_param") or 42,
```

**3. Use it in your logic:**
```python
my_param = cfg.get("my_new_param", 42)
```

The Settings UI will display the new key automatically — no frontend changes needed. The key is editable via the ⚙️ Settings drawer in the dashboard.

---

## Default Config Values

| Key | Default | Type | Category |
|-----|---------|------|----------|
| `negative_keywords` | (42 keywords) | `json_list` | News & Sentiment |
| `positive_keywords` | (19 keywords) | `json_list` | News & Sentiment |
| `avoid_news_threshold` | `0.55` | `float` | News & Sentiment |
| `negative_headline_threshold` | `0.45` | `float` | News & Sentiment |
| `news_cache_ttl` | `600` | `int` | News & Sentiment |
| `dip_window` | `20` | `int` | Dip Detection |
| `dip_threshold` | `5.0` | `float` | Dip Detection |
| `buy_dip_pct` | `3.0` | `float` | Dip Detection |
| `buy_small_dip_min` | `1.0` | `float` | Dip Detection |
| `buy_small_dip_max` | `3.0` | `float` | Dip Detection |
| `rsi_oversold` | `35` | `int` | Technical Analysis |
| `rsi_overbought` | `65` | `int` | Technical Analysis |
| `volume_spike_ratio` | `1.5` | `float` | Technical Analysis |
| `sparkline_days` | `30` | `int` | Technical Analysis |
| `history_period` | `"6mo"` | `str` | Technical Analysis |


Signals are computed in `backend/data/analysis.py`. The `full_analysis()` function returns a dict including `signal: {signal, confidence, reasons}`.

1. **Add logic** in `analysis.py` inside `full_analysis()`:
```python
# Example: add a new "BREAKOUT" signal condition
if current_price > fifty_two_week_high * 0.98:
    signal = "BREAKOUT"
    confidence += 20
    reasons.append("Near 52-week high")
```

2. **Add the badge style** in `frontend/src/components/SignalBadge.jsx`:
```js
const SIGNAL_CONFIG = {
  // ...existing signals
  BREAKOUT: {
    icon: <RocketLaunchIcon fontSize="small" />,
    sx: { background: "...", border: "1px solid #b388ff", color: "#b388ff", fontWeight: 800 },
  },
};
```

3. **Add the colour** in `Dashboard.jsx`:
```js
const SIGNAL_COLORS = {
  // ...existing
  BREAKOUT: "#b388ff",
};
```

---

## Modifying the Stock Card

The card layout is in `frontend/src/components/StockCard.jsx`. Key sections:

```
Card
├── Header          ← symbol, name (with ellipsis), SignalBadge, delete button
├── Price row       ← current price + % change chip
├── Sparkline       ← 30-day mini chart
├── DipMeter        ← linear progress bar showing dip from recent high
├── ResistanceMeter ← linear progress bar showing proximity to resistance
├── Stats row       ← RSI chip, MA20 chip, 52-week range chip
├── Signal Rationale ← bullet-point reasons
└── NewsPanel       ← latest headlines + sentiment score
```

To add a new data point to the card, add it to the destructured props and render it in the appropriate section.

---

## Adding a New API Endpoint

All routes are in `backend/main.py`. Example:

```python
@app.get("/api/stocks/{symbol}/history")
def stock_history(symbol: str):
    """Return raw price history for a symbol."""
    result = store.get(symbol.upper())
    if not result:
        raise HTTPException(status_code=404, detail=f"{symbol} not cached")
    return {"symbol": symbol, "sparkline": result.get("sparkline", [])}
```

Add the corresponding frontend call in `frontend/src/api.js`:
```js
export const getStockHistory = (symbol) =>
  api.get(`/api/stocks/${symbol}/history`).then((r) => r.data);
```

---

## Modifying the Database Schema

Edit `backend/data/store.py` → `init_db()`.

**Adding a column** to `watchlist`:
```python
# In init_db(), after the CREATE TABLE:
try:
    conn.execute("ALTER TABLE watchlist ADD COLUMN notes TEXT DEFAULT ''")
    conn.commit()
except sqlite3.OperationalError:
    pass  # column already exists — safe to ignore
```

Then add corresponding read/write helpers in `store.py`.

---

## Changing the Refresh Strategy

Manual-only refresh is the current default. To re-enable scheduled background refresh, edit `backend/scheduler.py`:

```python
def start(run_now: bool = False):
    # Re-add the interval job:
    _scheduler.add_job(
        refresh_all,
        trigger=IntervalTrigger(minutes=60),   # every 60 min
        id="refresh_all",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
```

> ⚠️ Be careful with intervals shorter than 30 minutes — yfinance has soft rate limits and will return empty/stale data.

---

## Theme Customization

Edit `frontend/src/ThemeContext.jsx` → `buildTheme(mode)`:

```js
// Change brand colours
primary: { main: "#your-color" },
secondary: { main: "#your-secondary" },

// Change dark background
background: isDark
  ? { default: "#0a0e1a", paper: "#111827" }  // ← darker
  : { default: "#f5f7fa", paper: "#ffffff" },
```

---

## Running Tests

No automated test suite exists currently. To manually verify:

```bash
# Backend: try all API endpoints
curl http://localhost:8000/health
curl http://localhost:8000/api/stocks
curl http://localhost:8000/api/stocks/deleted
curl http://localhost:8000/api/dashboard | python3 -m json.tool | head -40

# Frontend: open http://localhost:5173 and use the UI
```

---

## Environment Variables

Currently all config is hardcoded. To make it configurable, create `backend/.env` and use `python-dotenv`:

```env
DB_PATH=./stock_data.db
PORT=8000
REFRESH_INTERVAL_MINUTES=60
```

```python
# In main.py / store.py
from dotenv import load_dotenv
load_dotenv()
DB_PATH = os.getenv("DB_PATH", "./stock_data.db")
```

---

## Deployment Notes

- The frontend builds to a static bundle: `cd frontend && npm run build` → `dist/`
- The backend can be served with `uvicorn main:app --host 0.0.0.0 --port 8000`
- For production, put `nginx` in front of both, serve frontend from `dist/`, and proxy `/api/*` to uvicorn
- `stock_data.db` should be on a persistent volume (not ephemeral container storage)
