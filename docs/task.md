# Stock Monitor App - Task Checklist

## Planning
- [/] Write implementation plan
- [ ] Get user approval

## Backend (Python/FastAPI)
- [ ] Project structure setup
- [ ] `stocks.json` - stock list storage
- [ ] Stock data fetcher (yfinance)
- [ ] Dip detector (% drop from recent high)
- [ ] Resistance level calculator (pivot points / recent highs)
- [ ] News scraper (negative news via NewsAPI or RSS)
- [ ] Buy/Sell signal generator
- [ ] REST API endpoints (FastAPI)

## Frontend (Node.js/Vite + Vanilla JS)
- [ ] Project scaffold (Vite)
- [ ] Dashboard UI - stock cards with dip/resistance/news/signal
- [ ] Add/Remove stocks from watchlist
- [ ] Real-time refresh / auto-poll
- [ ] Color-coded signals (Buy=green, Sell=red, Hold=yellow)
- [ ] News panel per stock

## Integration & Verification
- [ ] Connect frontend to Python API
- [ ] End-to-end test with a few real stocks
- [ ] Browser visual verification
