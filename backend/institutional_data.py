
from datetime import datetime
from zoneinfo import ZoneInfo
import time
import requests

from market_data import get_api, api_request

IST = ZoneInfo("Asia/Kolkata")

NSE_HOME = "https://www.nseindia.com"
NSE_REPORT = "https://www.nseindia.com/reports/fii-dii"
NSE_API = "https://www.nseindia.com/api/fiidiiTradeReact"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": NSE_REPORT,
}

OI_BUILDUP_TYPES = {
    "LONG_BUILT_UP": "Long Built Up",
    "SHORT_BUILT_UP": "Short Built Up",
    "SHORT_COVERING": "Short Covering",
    "LONG_UNWINDING": "Long Unwinding",
}

_cache = {"time": 0, "data": None}


def _number(value):
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def fetch_fii_dii():
    session = requests.Session()
    session.headers.update(HEADERS)

    session.get(NSE_HOME, timeout=15)
    session.get(NSE_REPORT, timeout=15)

    response = session.get(NSE_API, timeout=15)
    response.raise_for_status()

    rows = response.json()
    result = []

    for row in rows:
        category = str(row.get("category", "")).upper()

        if "FII" not in category and "DII" not in category:
            continue

        result.append({
            "category": category,
            "date": row.get("date"),
            "buy_value_cr": _number(row.get("buyValue")) or 0,
            "sell_value_cr": _number(row.get("sellValue")) or 0,
            "net_value_cr": _number(row.get("netValue")) or 0,
        })

    return result


def _fetch_oi_buildup(api):
    buildup = {}
    errors = {}
    diagnostics = {}

    for key, datatype in OI_BUILDUP_TYPES.items():
        try:
            response = api_request(
                lambda datatype=datatype: api.oIBuildup({
                    "expirytype": "NEAR",
                    "datatype": datatype,
                })
            )

            rows = response.get("data") or []

            diagnostics[key] = {
                "api_rows_count": len(rows),
                "sample_symbols": [
                    str(row.get("tradingSymbol", "")).upper()
                    for row in rows[:5]
                ],
            }

            buildup[key] = []

            for row in rows:
                symbol = str(
                    row.get("tradingSymbol", "")
                ).upper()

                buildup[key].append({
                    "symbol": symbol,
                    "ltp": _number(row.get("ltp")),
                    "price_change": _number(row.get("netChange")),
                    "price_change_pct": _number(
                        row.get("percentChange")
                    ),
                    "open_interest": _number(
                        row.get("opnInterest")
                    ),
                    "oi_change": _number(
                        row.get("netChangeOpnInterest")
                    ),
                })

        except Exception as error:
            buildup[key] = []
            errors[key] = str(error)

    return buildup, errors, diagnostics


def fetch_angel_data():
    result = {
        "status": "UNAVAILABLE",
        "pcr": {},
        "pcr_status": "UNAVAILABLE",
        "pcr_error": None,
        "oi_buildup": {},
        "oi_buildup_status": "UNAVAILABLE",
        "oi_buildup_errors": {},
        "oi_buildup_diagnostics": {},
        "supported_underlyings": ["NIFTY"],
        "note": (
            "PCR is mapped to available futures symbols. "
            "OI Buildup includes all contracts returned by Angel One."
        ),
    }

    try:
        api = get_api()

        # PCR DATA
        try:
            response = api_request(
                lambda: api.putCallRatio()
            )

            for row in response.get("data") or []:
                symbol = str(
                    row.get("tradingSymbol", "")
                ).upper()

                pcr = _number(row.get("pcr"))

                if symbol and pcr is not None:
                    result["pcr"][symbol] = pcr

            result["pcr_status"] = (
                "CONNECTED"
                if result["pcr"]
                else "NO_DATA"
            )

        except Exception as error:
            result["pcr_status"] = "ERROR"
            result["pcr_error"] = str(error)

        # ALL OI BUILDUP CONTRACTS
        buildup, errors, diagnostics = _fetch_oi_buildup(api)

        result["oi_buildup"] = buildup
        result["oi_buildup_errors"] = errors
        result["oi_buildup_diagnostics"] = diagnostics

        successful_types = sum(
            1 for key in OI_BUILDUP_TYPES
            if key in buildup and key not in errors
        )

        available_types = sum(
            1 for key in OI_BUILDUP_TYPES
            if buildup.get(key)
        )

        if available_types == len(OI_BUILDUP_TYPES):
            result["oi_buildup_status"] = "CONNECTED"
        elif available_types > 0:
            result["oi_buildup_status"] = "PARTIALLY_CONNECTED"
        elif successful_types == len(OI_BUILDUP_TYPES):
            result["oi_buildup_status"] = "NO_DATA"
        elif successful_types > 0:
            result["oi_buildup_status"] = "PARTIALLY_CONNECTED"
        else:
            result["oi_buildup_status"] = "ERROR"

        if result["pcr"] or available_types:
            result["status"] = "PARTIALLY_CONNECTED"

        elif result["pcr_status"] == "CONNECTED":
            result["status"] = "PARTIALLY_CONNECTED"

    except Exception as error:
        result["error"] = str(error)

    return result


def get_institutional_data():
    now = time.time()

    if _cache["data"] and now - _cache["time"] < 300:
        return _cache["data"]

    result = {
        "updated_at": datetime.now(IST).isoformat(),

        "fii_dii": {
            "status": "UNAVAILABLE",
            "source": "NSE India",
            "frequency": "DAILY",
            "data": [],
            "note": (
                "Daily cash-market figures, "
                "not minute-by-minute."
            ),
        },

        "angel_one": {},

        "participant_positions": {
            "status": "NOT_CONNECTED",
            "note": (
                "FII participant-wise Futures/Options "
                "data is not connected."
            ),
        },

        "note": (
            "FII/DII values are daily cash-market data. "
            "PCR and OI Buildup are separate market indicators. "
            "Stock futures OI is not the same as NIFTY index OI."
        ),
    }

    try:
        rows = fetch_fii_dii()

        if rows:
            result["fii_dii"]["status"] = "CONNECTED"
            result["fii_dii"]["data"] = rows

    except Exception as error:
        result["fii_dii"]["error"] = str(error)

    result["angel_one"] = fetch_angel_data()
    result["updated_at"] = datetime.now(IST).isoformat()

    _cache["time"] = time.time()
    _cache["data"] = result

    return result
