from datetime import datetime, timedelta
from smartapi_client import connect_angel

# Angel One index tokens; confirm they match the instruments enabled in your account.
INSTRUMENTS = {"NIFTY": {"exchange": "NSE", "token": "99926000"}, "SENSEX": {"exchange": "BSE", "token": "99919000"}}
INTERVALS = {"15m": ("FIFTEEN_MINUTE", 7), "1h": ("ONE_HOUR", 45), "1d": ("ONE_DAY", 220)}

def get_market_status():
    from config import ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_PASSWORD, ANGEL_TOTP_SECRET
    if not all([ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_PASSWORD, ANGEL_TOTP_SECRET]):
        return {"mode": "DEMO", "live_data": False, "connected": False, "message": "Angel One credentials are not configured in Render environment variables."}
    try:
        connect_angel()
        return {"mode": "LIVE", "live_data": True, "connected": True, "message": "Angel One login successful."}
    except Exception as error:
        return {"mode": "UNAVAILABLE", "live_data": False, "connected": False, "message": str(error)}

def get_analysis_data(symbol, timeframe):
    if symbol not in INSTRUMENTS or timeframe not in INTERVALS:
        raise ValueError("Unsupported symbol or timeframe")
    instrument = INSTRUMENTS[symbol]
    interval, days = INTERVALS[timeframe]
    api = connect_angel()
    now = datetime.now()
    response = api.getCandleData({"exchange": instrument["exchange"], "symboltoken": instrument["token"], "interval": interval, "fromdate": (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M"), "todate": now.strftime("%Y-%m-%d %H:%M")})
    if not response or not response.get("status"):
        raise RuntimeError((response or {}).get("message", "Angel One candle request failed"))
    candles = []
    for row in response.get("data") or []:
        if len(row) >= 5:
            candles.append({"time": row[0], "open": float(row[1]), "high": float(row[2]), "low": float(row[3]), "close": float(row[4]), "volume": float(row[5]) if len(row) > 5 and row[5] is not None else 0})
    if not candles:
        raise RuntimeError("Broker returned no candles")
    return {"candles": candles, "exchange": instrument["exchange"]}
