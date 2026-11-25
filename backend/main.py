
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from market_data import (
    get_market_status,
    get_market_quote,
    get_historical_candles,
)
from indicators import calculate_indicators
from signals import generate_signal

app = FastAPI(title="NIFTY SENSEX Trading API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

FRONTEND_FILE = Path(__file__).resolve().parent.parent / "index.html"


@app.get("/", include_in_schema=False)
def home():
    if FRONTEND_FILE.exists():
        return FileResponse(FRONTEND_FILE)
    return {"message": "NIFTY SENSEX API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/status")
def status():
    result = get_market_status()
    return {
        "mode": result.get("mode", "DEMO"),
        "message": result.get("message", "Connection check failed"),
        "nifty": result.get("mode", "DEMO"),
        "sensex": result.get("mode", "DEMO"),
        "live_data": False,
        "broker_connected": result.get("connected", False),
    }


@app.get("/api/market/overview")
def market_overview():
    markets = {}

    for symbol in ["NIFTY", "SENSEX"]:
        result = get_market_quote(symbol)

        if result.get("connected"):
            data = result.get("data") or {}
            markets[symbol] = {
                "price": data.get("ltp"),
                "mode": "BROKER_CONNECTED",
            }
        else:
            markets[symbol] = {
                "price": None,
                "mode": "DATA UNAVAILABLE",
            }

    return {"markets": markets}


@app.get("/api/market/analysis")
def market_analysis(
    symbol: str = "NIFTY",
    timeframe: str = "15m"
):
    symbol = symbol.upper()

    labels = {
        "15m": "15 Minute",
        "1h": "1 Hour",
        "1d": "Daily",
    }

    if symbol not in ["NIFTY", "SENSEX"]:
        raise HTTPException(status_code=400, detail="Invalid symbol")

    if timeframe not in labels:
        raise HTTPException(status_code=400, detail="Invalid timeframe")

    try:
        candles = get_historical_candles(symbol, timeframe)

        indicators = calculate_indicators(candles)

        if "error" in indicators:
            raise RuntimeError(indicators["error"])

        price = indicators["close"]

        signal = generate_signal(
            price,
            indicators["ema_20"],
            indicators["ema_50"],
            indicators["rsi"],
        )

        signal_name = signal.get("signal", "WAIT")

        direction = (
            "BULLISH" if signal_name == "CALL BIAS"
            else "BEARISH" if signal_name == "PUT BIAS"
            else "NEUTRAL"
        )

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "timeframe_label": labels[timeframe],
            "price": price,
            "indicators": {
                "ema_20": indicators["ema_20"],
                "ema_50": indicators["ema_50"],
                "rsi": indicators["rsi"],
            },
            "signal": {
                **signal,
                "direction": direction,
                "note": "Index levels only; not option premium. Verify before trading.",
            },
            "updated_at": datetime.now(
                ZoneInfo("Asia/Kolkata")
            ).isoformat(),
        }

    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Market data unavailable: {str(error)}",
        )
