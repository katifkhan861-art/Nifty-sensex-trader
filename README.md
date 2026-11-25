# NIFTY × SENSEX Trading Desk
Hindi-first NIFTY 50 and SENSEX analysis dashboard.

Features: 15-minute, 1-hour and Daily candle analysis; Angel One SmartAPI; EMA 20, EMA 50 and RSI; rule-based CALL BIAS / PUT BIAS / WAIT; DEMO / LIVE / UNAVAILABLE status.

## Render environment variables
Set in Render Dashboard → Web Service → Environment: `ANGEL_API_KEY`, `ANGEL_CLIENT_CODE`, `ANGEL_PASSWORD`, `ANGEL_TOTP_SECRET`. Never commit real credentials. Without all four values, the service remains in DEMO mode.

## API routes
`GET /`, `GET /health`, `GET /api/status`, `GET /api/market/analysis?symbol=NIFTY&timeframe=15m`, `GET /api/market/analysis?symbol=SENSEX&timeframe=1h`, `GET /api/market/overview`. Timeframes: `15m`, `1h`, `1d`.

Signals are technical bias on the underlying index, not option-premium entry/SL/target. The app does not place orders. Confirm Angel One instrument tokens and candle responses against your broker account. Paper-trade first; options carry substantial risk.
