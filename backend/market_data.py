
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from threading import Lock
import time

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

_api = None
_api_time = 0
_api_lock = Lock()
_request_lock = Lock()
_last_request = 0
_blocked_until = 0

_cache = {}


def get_api():
    global _api, _api_time

    with _api_lock:
        now = time.time()

        if _api is not None and now - _api_time < 1200:
            return _api

        _api = connect_angel()
        _api_time = now
        return _api


def api_request(function):
    global _last_request, _blocked_until

    with _request_lock:
        now = time.time()

        if now < _blocked_until:
            raise RuntimeError(
                "Angel One rate limit active. Please wait before retrying."
            )

        wait = 1.5 - (now - _last_request)
        if wait > 0:
            time.sleep(wait)

        try:
            result = function()
            _last_request = time.time()

            if not result or not result.get("status"):
                raise RuntimeError("Angel One request failed")

            return result

        except Exception as error:
            _last_request = time.time()
            message = str(error).lower()

            if "access denied" in message or "rate" in message:
                _blocked_until = time.time() + 60

            raise


def get_market_status():
    try:
        get_api()
        return {
            "connected": True,
            "mode": "BROKER_CONNECTED",
            "message": "Angel One login successful"
        }
    except Exception as error:
        return {
            "connected": False,
            "mode": "DEMO",
            "message": str(error)
        }


def get_market_quote(symbol="NIFTY"):
    symbol = symbol.upper()

    if symbol not in SYMBOLS:
        return {"connected": False, "error": "Unsupported symbol"}

    cache_key = ("quote", symbol)
    now = time.time()

    cached = _cache.get(cache_key)
    if cached and now - cached["time"] < 15:
        return cached["data"]

    try:
        item = SYMBOLS[symbol]
        api = get_api()

        result = api_request(
            lambda: api.ltpData(
                item["exchange"],
                item["tradingsymbol"],
                item["token"]
            )
        )

        data = {
            "connected": True,
            "symbol": symbol,
            "data": result.get("data")
        }

        _cache[cache_key] = {
            "time": time.time(),
            "data": data
        }

        return data

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

    cache_key = ("candles", symbol, timeframe)
    now = time.time()

    cached = _cache.get(cache_key)
    if cached and now - cached["time"] < 60:
        return cached["data"]

    item = SYMBOLS[symbol]
    api = get_api()
    now_ist = datetime.now(IST)

    days = {
        "15m": 30,
        "1h": 60,
        "1d": 365
    }[timeframe]

    params = {
        "exchange": item["exchange"],
        "symboltoken": item["token"],
        "interval": INTERVALS[timeframe],
        "fromdate": (
            now_ist - timedelta(days=days)
        ).strftime("%Y-%m-%d 09:00"),
        "todate": now_ist.strftime("%Y-%m-%d 15:30")
    }

    result = api_request(
        lambda: api.getCandleData(params)
    )

    candles = result.get("data") or []

    data = [
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

    _cache[cache_key] = {
        "time": time.time(),
        "data": data
    }

    return data
