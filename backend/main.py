
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
from institutional_data import get_institutional_data

IST = ZoneInfo("Asia/Kolkata")

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
                "error": result.get("error"),
            }

    return {"markets": markets}


def analyze_timeframe(symbol, timeframe):
    candles = get_historical_candles(symbol, timeframe)
    indicators = calculate_indicators(candles)

    if "error" in indicators:
        raise RuntimeError(indicators["error"])

    price = indicators["close"]
    ema20 = indicators["ema_20"]
    ema50 = indicators["ema_50"]
    rsi = indicators["rsi"]

    signal = generate_signal(price, ema20, ema50, rsi)

    if price > ema20 and ema20 > ema50:
        direction = "BULLISH"
    elif price < ema20 and ema20 < ema50:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    return {
        "timeframe": timeframe,
        "direction": direction,
        "price": price,
        "indicators": {
            "ema_20": ema20,
            "ema_50": ema50,
            "rsi": rsi,
        },
        "signal": signal,
    }


def get_institutional_summary():
    try:
        data = get_institutional_data()
        rows = data.get("fii_dii", {}).get("data", [])

        fii_net = None
        dii_net = None
        report_date = None

        for row in rows:
            category = str(row.get("category", "")).upper()
            net = float(row.get("net_value_cr") or 0)

            if "FII" in category or "FPI" in category:
                fii_net = net
                report_date = row.get("date") or report_date

            elif "DII" in category:
                dii_net = net
                report_date = row.get("date") or report_date

        if fii_net is None or dii_net is None:
            bias = "UNKNOWN"
        elif fii_net > 0 and dii_net > 0:
            bias = "POSITIVE"
        elif fii_net < 0 and dii_net < 0:
            bias = "NEGATIVE"
        else:
            bias = "MIXED"

        return {
            "status": data.get("fii_dii", {}).get(
                "status", "UNAVAILABLE"
            ),
            "date": report_date,
            "fii_net_cr": fii_net,
            "dii_net_cr": dii_net,
            "bias": bias,
            "pcr": data.get("angel_one", {}).get("pcr", {}),
            "pcr_status": data.get("angel_one", {}).get(
                "status", "UNAVAILABLE"
            ),
            "note": (
                "FII/DII figures are daily cash-market data. "
                "PCR is a separate market-wide indicator."
            ),
        }

    except Exception as error:
        return {
            "status": "UNAVAILABLE",
            "bias": "UNKNOWN",
            "error": str(error),
        }


@app.get("/api/market/analysis")
def market_analysis(
    symbol: str = "NIFTY",
    timeframe: str = "15m",
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
        result = analyze_timeframe(symbol, timeframe)

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "timeframe_label": labels[timeframe],
            **result,
            "updated_at": datetime.now(IST).isoformat(),
        }

    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Market data unavailable: {str(error)}",
        )


@app.get("/api/market/combined")
def combined_market_analysis(symbol: str = "NIFTY"):
    symbol = symbol.upper()

    if symbol not in ["NIFTY", "SENSEX"]:
        raise HTTPException(status_code=400, detail="Invalid symbol")

    try:
        daily = analyze_timeframe(symbol, "1d")
        hourly = analyze_timeframe(symbol, "1h")
        fifteen = analyze_timeframe(symbol, "15m")

        institutional = get_institutional_summary()

        daily_direction = daily["direction"]
        hourly_direction = hourly["direction"]

        daily_signal = daily["signal"].get("signal", "WAIT")
        hourly_signal = hourly["signal"].get("signal", "WAIT")
        fifteen_signal = fifteen["signal"].get("signal", "WAIT")

        final_signal = "WAIT"
        reason = (
            "Daily, 1-hour aur 15-minute teeno ki "
            "confirmation abhi poori nahi hai."
        )

        # CALL: all three timeframes must confirm
        if (
            daily_direction == "BULLISH"
            and daily_signal == "CALL BIAS"
            and hourly_direction == "BULLISH"
            and hourly_signal == "CALL BIAS"
            and fifteen_signal == "CALL BIAS"
        ):
            final_signal = "CALL BIAS"
            reason = (
                "Daily, 1-hour aur 15-minute teeno "
                "CALL direction confirm kar rahe hain."
            )

        # PUT: all three timeframes must confirm
        elif (
            daily_direction == "BEARISH"
            and daily_signal == "PUT BIAS"
            and hourly_direction == "BEARISH"
            and hourly_signal == "PUT BIAS"
            and fifteen_signal == "PUT BIAS"
        ):
            final_signal = "PUT BIAS"
            reason = (
                "Daily, 1-hour aur 15-minute teeno "
                "PUT direction confirm kar rahe hain."
            )

        entry = None
        stop_loss = None
        target = None

        # Entry levels are taken from 15-minute analysis only
        if final_signal in ["CALL BIAS", "PUT BIAS"]:
            entry = fifteen["signal"].get("entry")
            stop_loss = fifteen["signal"].get("stop_loss")
            target = fifteen["signal"].get("target")

        return {
            "symbol": symbol,
            "signal": final_signal,
            "direction": (
                "BULLISH" if final_signal == "CALL BIAS"
                else "BEARISH" if final_signal == "PUT BIAS"
                else "NEUTRAL"
            ),
            "entry": entry,
            "stop_loss": stop_loss,
            "target": target,
            "reason": reason,
            "confirmation": {
                "daily": {
                    "direction": daily_direction,
                    "signal": daily_signal,
                    "confirmed": (
                        daily_direction == "BULLISH"
                        and daily_signal == "CALL BIAS"
                    ) or (
                        daily_direction == "BEARISH"
                        and daily_signal == "PUT BIAS"
                    ),
                },
                "one_hour": {
                    "direction": hourly_direction,
                    "signal": hourly_signal,
                },
                "fifteen_minute": {
                    "direction": fifteen["direction"],
                    "signal": fifteen_signal,
                },
            },
            "timeframes": {
                "daily": daily,
                "one_hour": hourly,
                "fifteen_minute": fifteen,
            },
            "institutional": institutional,
            "risk_note": (
                "Index levels only, not option premium. "
                "Signals are preliminary. Verify live data "
                "and risk before trading."
            ),
            "updated_at": datetime.now(IST).isoformat(),
        }

    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Combined analysis unavailable: {str(error)}",
        )


@app.get("/api/market/institutional")
def institutional_data():
    try:
        return get_institutional_data()

    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Institutional data unavailable: {str(error)}",
        )
