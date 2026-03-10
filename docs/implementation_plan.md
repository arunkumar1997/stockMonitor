# Stock Monitor App — Implementation Plan

A fullstack stock monitoring dashboard. The **Python/FastAPI** backend does all the heavy lifting (data fetching, technical analysis, news scraping). The **React + MUI (Material UI v6)** frontend renders a premium dark-themed dashboard showing dips, resistance levels, news sentiment, and buy/sell signals.

---

## Architecture Overview

```
stockMonitor/
├── backend/                  # Python FastAPI app
│   ├── main.py               # FastAPI entry point + all routes
│   ├── stocks.json           # Persisted watchlist [{symbol, name}]
│   ├── data/
│   │   ├── fetcher.py        # yfinance stock history fetcher
│   │   ├── analysis.py       # Dip detection, resistance, signals
│   │   └── news.py           # News scraping / sentiment
│   └── requirements.txt
│
└── frontend/                 # React + Vite + MUI v6
    ├── index.html
    ├── src/
    │   ├── main.jsx          # React entry point
    │   ├── App.jsx           # Root layout, theme provider
    │   ├── api.js            # Axios wrapper for backend
    │   ├── theme.js          # MUI dark theme config
    │   ├── components/
    │   │   ├── Dashboard.jsx     # Main grid of stock cards
    │   │   ├── StockCard.jsx     # Per-stock card with analysis
    │   │   ├── Sparkline.jsx     # Mini price chart (recharts)
    │   │   ├── SignalBadge.jsx   # BUY/SELL/HOLD chip
    │   │   ├── NewsPanel.jsx     # Collapsible news accordion
    │   │   └── AddStockModal.jsx # Dialog to add new stock
    │   └── index.css
    └── package.json
```

---

## User Review Required

> [!IMPORTANT]
> **API Keys**: Negative news checking uses [NewsAPI](https://newsapi.org). A free API key is required. You can get one at https://newsapi.org/register — I'll make it an env variable so you just set `NEWS_API_KEY=...` in a `.env` file.

> [!NOTE]
> **Stock Universe**: This app works with **any stock symbol** (NSE/BSE/US). NSE stocks use the suffix format e.g. `RELIANCE.NS`, US stocks are plain e.g. `AAPL`. I'll add a note in the UI.

---

## Proposed Changes

### Backend (Python/FastAPI)

#### [NEW] `backend/requirements.txt`
FastAPI, uvicorn, yfinance, pandas, numpy, requests, python-dotenv, feedparser, httpx

#### [NEW] `backend/stocks.json`
```json
[
  {"symbol": "AAPL", "name": "Apple Inc"},
  {"symbol": "RELIANCE.NS", "name": "Reliance Industries"}
]
```

#### [NEW] `backend/data/fetcher.py`
- Downloads 6 months of OHLCV daily data using `yfinance`
- Caches results in-memory for 15 minutes to avoid repeated API calls

#### [NEW] `backend/data/analysis.py`
Core technical analysis:
- **Dip Detection**: Current price vs 20-day high → flags if dropped >5% (configurable threshold)
- **Resistance Levels**: Identifies recent swing highs (local maxima in 20-day window) as resistance; current price is scored as % below resistance
- **52-week High/Low** context
- **Signal Generator**: Combines dip severity + position relative to resistance + news sentiment → `BUY / SELL / HOLD` with confidence score

#### [NEW] `backend/data/news.py`
- Primary: NewsAPI `/everything` endpoint filtered by stock name/symbol, last 7 days
- Fallback: RSS scrape from Yahoo Finance news feed per ticker (no key needed)
- Sentiment scoring: keyword-based negative detection (fraud, lawsuit, loss, crash, downgrade, etc.)
- Returns: headline list + negative_score (0–1)

#### [NEW] `backend/main.py`
FastAPI REST API:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/stocks` | List all tracked stocks |
| POST | `/api/stocks` | Add a stock `{symbol, name}` |
| DELETE | `/api/stocks/{symbol}` | Remove stock from watchlist |
| GET | `/api/analyze/{symbol}` | Full analysis for one stock |
| GET | `/api/dashboard` | Bulk analysis for all tracked stocks |

CORS enabled for localhost frontend.

---

### Frontend (React + Vite + MUI v6)

**Stack**: React 18, Vite, MUI v6, Recharts (for sparklines), Axios

#### [NEW] `frontend/src/theme.js`
Custom MUI dark theme:
- Background: `#0a0e1a` with `#141824` paper
- Accent: `#00b4d8` (cyan-blue)
- Signal colors: green (`#00e676`), red (`#ff5252`), amber (`#ffd740`)
- Glassmorphism card overrides with backdrop blur

#### [NEW] `frontend/src/components/StockCard.jsx`
MUI `Card` with:
- **Header**: Symbol, company name, live price, % change chip
- **Dip Badge**: MUI `Chip` in error color showing % below recent high
- **Resistance Meter**: MUI `LinearProgress` showing proximity to resistance
- **Signal Badge**: `SignalBadge` component (BUY/SELL/HOLD)
- **Sparkline**: `Sparkline.jsx` using Recharts `AreaChart`
- **News Accordion**: Expandable `Accordion` listing headlines

#### [NEW] `frontend/src/components/Dashboard.jsx`
- MUI `Grid2` responsive layout (3 cols desktop, 2 tablet, 1 mobile)
- Loading `Skeleton` cards while fetching
- Auto-refresh every 5 minutes with countdown badge
- FAB (+) button to open `AddStockModal`

#### [NEW] `frontend/src/components/AddStockModal.jsx`
MUI `Dialog` with symbol input + name input + validation

#### [NEW] `frontend/src/api.js`
Axios client pointing to `http://localhost:8000`

---

## Verification Plan

### Automated Tests
```bash
# 1. Install backend deps and start server
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 2. Test API endpoints
curl http://localhost:8000/api/stocks
curl http://localhost:8000/api/analyze/AAPL
curl http://localhost:8000/api/dashboard
```

### Browser Verification
- Open frontend dev server (`npm run dev` in `frontend/`)
- Verify stock cards load with real data
- Verify dip, resistance, signal, news panels render correctly
- Add a new stock and verify it appears
- Remove a stock and verify it disappears

### Manual Test Checklist
1. Start backend → `cd backend && uvicorn main:app --reload`
2. Start frontend → `cd frontend && npm run dev`
3. Open `http://localhost:5173` in browser
4. Confirm dashboard loads with pre-seeded stocks (AAPL, RELIANCE.NS)
5. Click a stock card to expand news
6. Add a new stock via the "+" button
7. Verify BUY/SELL/HOLD badge color matches signal
