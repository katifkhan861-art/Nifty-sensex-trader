
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from smartapi_client import connect_angel

IST = ZoneInfo("Asia/Kolkata")

SYMBOLS = {
    "NIFTY": {
        "exchange": "NSE",
        "token": "99926000",
        "tradingsymbol": "Nifty 50",
    },
    "SENSEX": {
        "exchange": "BSE",
        "token": "99919000",
        "tradingsymbol": "SENSEX",
    },
}

INTERVALS = {
    "15m": "FIFTEEN_MINUTE",
    "1h": "ONE_HOUR",
    "1d": "ONE_DAY",
}


def get_market_status():
    try:
        connect_angel()
        return {
            "connected": True,
            "mode": "BROKER_CONNECTED",
            "message": "Angel One login successful. Market data check pending."
        }
    except Exception as error:
        return {
            "connected": False,
            "mode": "DEMO",
            "message": str(error)
        }


def get_market_quote(symbol="NIFTY"):
    try:
        symbol = symbol.upper()
        if symbol not in SYMBOLS:
            raise ValueError("Unsupported symbol")

        item = SYMBOLS[symbol]
        smart_api = connect_angel()

        result = smart_api.ltpData(
            item["exchange"],
            item["tradingsymbol"],
            item["token"]
        )

        if not result or not result.get("status"):
            raise RuntimeError("Angel One quote request failed")

        return {
            "connected": True,
            "symbol": symbol,
            "data": result.get("data")
        }
    except Exception as error:
        return {
            "connected": False,
            "error": str(error)
        }


def get_historical_candles(symbol="NIFTY", timeframe="15m"):
    symbol = symbol.upper()

    if symbol not in SYMBOLS:
        raise ValueError("Unsupported symbol")

    if timeframe not in INTERVALS:
        raise ValueError("Unsupported timeframe")

    item = SYMBOLS[symbol]
    smart_api = connect_angel()

    now = datetime.now(IST)

    days = {
        "15m": 30,
        "1h": 60,
        "1d": 365
    }[timeframe]

    params = {
        "exchange": item["exchange"],
        "symboltoken": item["token"],
        "interval": INTERVALS[timeframe],
        "fromdate": (now - timedelta(days=days)).strftime("%Y-%m-%d 09:00"),
        "todate": now.strftime("%Y-%m-%d 15:30")
    }

    result = smart_api.getCandleData(params)

    if not result or not result.get("status"):
        raise RuntimeError("Angel One candle data request failed")

    candles = result.get("data") or []

    return [
        {
            "time": candle[0],
            "open": float(candle[1]),
            "high": float(candle[2]),
            "low": float(candle[3]),
            "close": float(candle[4]),
            "volume": float(candle[5])
        }
        for candle in candles
    ]
