
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

# Angel One FULL quote timestamp fields
TIMESTAMP_KEYS = {
    "exchfeedtime",
    "exchtradetime",
    "exchangetimestamp",
    "lasttradetime",
    "lasttradetimestamp",
    "timestamp",
    "tradetimestamp",
    "feedtime",
}


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
                "Angel One rate limit active. Please wait."
            )

        wait = 1.5 - (now - _last_request)

        if wait > 0:
            time.sleep(wait)

        try:
            result = function()
            _last_request = time.time()

            if not isinstance(result, dict):
                raise RuntimeError(
                    "Invalid Angel One response"
                )

            if not result.get("status"):
                raise RuntimeError(
                    result.get("message")
                    or result.get("error")
                    or "Angel One request failed"
                )

            return result

        except Exception as error:
            _last_request = time.time()

            message = str(error).lower()

            if (
                "access denied" in message
                or "rate" in message
                or "too many" in message
            ):
                _blocked_until = time.time() + 60

            raise


def normalize_timestamp(value):
    """
    Actual broker timestamp ko IST ISO format mein convert karta hai.
    Server ka current time exchange timestamp nahi banaya jata.
    """

    if value is None:
        return None

    if isinstance(value, (int, float)):
        try:
            stamp = float(value)

            # Milliseconds ko seconds mein convert karein.
            if stamp > 100000000000:
                stamp = stamp / 1000

            parsed = datetime.fromtimestamp(
                stamp,
                tz=IST
            )

            return parsed.isoformat()

        except (
            ValueError,
            OSError,
            OverflowError
        ):
            return None

    if not isinstance(value, str):
        return None

    value = value.strip()

    if not value:
        return None

    # ISO timestamp
    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)

        return parsed.astimezone(IST).isoformat()

    except ValueError:
        pass

    formats = [
        "%d-%b-%Y %H:%M:%S",
        "%d-%b-%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)

            return parsed.replace(
                tzinfo=IST
            ).isoformat()

        except ValueError:
            continue

    return None


def find_exchange_timestamp(data):
    """
    FULL quote mein exchange feed/trade timestamp dhoondhta hai.
    Feed time ko priority deta hai.
    """

    if not isinstance(data, dict):
        return None, None

    # Pehle preferred timestamp fields check karein.
    preferred_keys = [
        "exchFeedTime",
        "exchTradeTime",
        "exchangeTimestamp",
        "lastTradeTime",
        "lastTradeTimestamp",
        "timestamp",
        "tradeTimestamp",
        "feedTime",
    ]

    for preferred in preferred_keys:
        for key, value in data.items():

            if str(key).lower().replace("_", "").replace("-", "") != (
                preferred.lower()
            ):
                continue

            timestamp = normalize_timestamp(value)

            if timestamp:
                return timestamp, key

    # Nested dictionaries mein bhi search.
    for value in data.values():
        if isinstance(value, dict):
            timestamp, source = find_exchange_timestamp(value)

            if timestamp:
                return timestamp, source

    return None, None


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
        return {
            "connected": False,
            "error": "Unsupported symbol"
        }

    cache_key = ("quote", symbol)
    now = time.time()

    cached = _cache.get(cache_key)

    if cached and now - cached["time"] < 15:
        return cached["data"]

    try:
        item = SYMBOLS[symbol]
        api = get_api()

        # Angel One FULL Market Data request
        result = api_request(
            lambda: api.getMarketData(
                "FULL",
                {
                    item["exchange"]: [
                        item["token"]
                    ]
                }
            )
        )

        response_data = result.get("data") or {}

        fetched = response_data.get("fetched") or []

        if not isinstance(fetched, list):
            raise RuntimeError(
                "Invalid FULL quote response"
            )

        raw_data = None

        # Sirf requested token ka data lena hai.
        for quote in fetched:
            if not isinstance(quote, dict):
                continue

            if str(
                quote.get("symbolToken", "")
            ) == item["token"]:
                raw_data = quote
                break

        if raw_data is None:
            unfetched = response_data.get("unfetched") or []

            raise RuntimeError(
                "Requested symbol quote not found. "
                f"Unfetched: {unfetched}"
            )

        exchange_timestamp, timestamp_source = (
            find_exchange_timestamp(raw_data)
        )

        # FULL response mein ltp hota hai.
        # Main.py ke existing quote structure ke liye
        # data field mein raw quote rakha gaya hai.
        data = {
            "connected": True,
            "symbol": symbol,
            "data": raw_data,

            "exchange_timestamp": exchange_timestamp,
            "timestamp": exchange_timestamp,

            "quote_timestamp_source": timestamp_source,
            "market_data_mode": "FULL",

            "quote_received_at": datetime.now(
                IST
            ).isoformat()
        }

        _cache[cache_key] = {
            "time": time.time(),
            "data": data
        }

        return data

    except Exception as error:
        return {
            "connected": False,
            "symbol": symbol,
            "error": str(error)
        }


def get_historical_candles(
    symbol="NIFTY",
    timeframe="15m"
):
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

        "todate": now_ist.strftime(
            "%Y-%m-%d 15:30"
        )
    }

    result = api_request(
        lambda: api.getCandleData(params)
    )

    candles = result.get("data") or []

    data = []

    for candle in candles:

        if (
            not isinstance(candle, (list, tuple))
            or len(candle) < 6
        ):
            continue

        try:
            data.append({
                "time": candle[0],
                "open": float(candle[1]),
                "high": float(candle[2]),
                "low": float(candle[3]),
                "close": float(candle[4]),
                "volume": float(candle[5])
            })

        except (TypeError, ValueError):
            continue

    _cache[cache_key] = {
        "time": time.time(),
        "data": data
    }

    return data
