from datetime import datetime
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from market_data import get_market_status, get_analysis_data
from indicators import calculate_indicators
from signals import generate_signal

app = FastAPI(title="NIFTY SENSEX Trading API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["https://katifkhan861-art.github.io", "http://localhost:3000", "http://127.0.0.1:5500"], allow_methods=["GET"], allow_headers=["*"])
TIMEFRAMES = {"15m": "15 Minutes", "1h": "1 Hour", "1d": "Daily"}

@app.get("/")
def home():
    return {"message": "NIFTY SENSEX API is running", "version": "2.0.0", "docs": "/docs"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/status")
def status():
    return get_market_status()

@app.get("/api/market/analysis")
def market_analysis(symbol: str = Query("NIFTY", pattern="^(NIFTY|SENSEX)$"), timeframe: str = Query("15m", pattern="^(15m|1h|1d)$")):
    try:
        payload = get_analysis_data(symbol, timeframe)
        candles = payload.get("candles", [])
        if not candles:
            raise HTTPException(status_code=503, detail=payload.get("message", "Live candle data unavailable"))
        indicators = calculate_indicators(candles)
        if "error" in indicators:
            raise HTTPException(status_code=422, detail=indicators["error"])
        signal = generate_signal(indicators["close"], indicators["ema_20"], indicators["ema_50"], indicators["rsi"])
        return {"symbol": symbol, "timeframe": timeframe, "timeframe_label": TIMEFRAMES[timeframe], "mode": "LIVE", "updated_at": datetime.now().astimezone().isoformat(), "price": indicators["close"], "indicators": indicators, "signal": signal, "candles": candles[-100:], "message": "Latest broker candle data. Verify all levels before trading."}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Market data unavailable: {str(exc)}")

@app.get("/api/market/overview")
def market_overview():
    markets = {}
    for symbol in ("NIFTY", "SENSEX"):
        try:
            data = get_analysis_data(symbol, "15m")
            candles = data.get("candles", [])
            markets[symbol] = {"price": candles[-1]["close"] if candles else None, "mode": "LIVE" if candles else "UNAVAILABLE"}
        except Exception:
            markets[symbol] = {"price": None, "mode": "UNAVAILABLE"}
    return {"markets": markets, "updated_at": datetime.now().astimezone().isoformat()}
