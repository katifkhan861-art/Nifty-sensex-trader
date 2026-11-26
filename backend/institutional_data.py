
from datetime import datetime
from zoneinfo import ZoneInfo
import time
import requests

from smartapi_client import connect_angel

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

_cache = {"time": 0, "data": None}


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
            "buy_value_cr": float(row.get("buyValue") or 0),
            "sell_value_cr": float(row.get("sellValue") or 0),
            "net_value_cr": float(row.get("netValue") or 0),
        })

    return result


def fetch_angel_data():
    result = {
        "status": "UNAVAILABLE",
        "pcr": {},
        "oi_buildup": {},
        "error": None,
    }

    try:
        api = connect_angel()

        # PCR data
        try:
            response = api.putCallRatio()

            if response and response.get("status"):
                for row in response.get("data") or []:
                    symbol = str(
                        row.get("tradingSymbol", "")
                    ).upper()

                    if symbol.startswith(("NIFTY", "SENSEX")):
                        result["pcr"][symbol] = row.get("pcr")

        except Exception as error:
            result["pcr_error"] = str(error)

        # Open Interest buildup
        buildup_types = [
            "Long Built Up",
            "Short Built Up",
            "Long Unwinding",
            "Short Covering",
        ]

        for buildup_type in buildup_types:
            try:
                response = api.oIBuildup({
                    "expirytype": "NEAR",
                    "datatype": buildup_type,
                })

                if response and response.get("status"):
                    rows = response.get("data") or []
                    result["oi_buildup"][buildup_type] = [
                        row for row in rows
                        if any(
                            symbol in str(row).upper()
                            for symbol in ("NIFTY", "SENSEX")
                        )
                    ]
                else:
                    result["oi_buildup"][buildup_type] = []

            except Exception as error:
                result["oi_buildup"][buildup_type] = []
                result.setdefault("oi_errors", {})[
                    buildup_type
                ] = str(error)

        if result["pcr"] or any(result["oi_buildup"].values()):
            result["status"] = "PARTIALLY_CONNECTED"

    except Exception as error:
        result["error"] = str(error)

    return result


def get_institutional_data():
    now = time.time()

    # 5-minute cache
    if _cache["data"] and now - _cache["time"] < 300:
        return _cache["data"]

    result = {
        "updated_at": datetime.now(IST).isoformat(),
        "fii_dii": {
            "status": "UNAVAILABLE",
            "source": "NSE India",
            "frequency": "DAILY",
            "data": [],
            "note": "NSE daily cash-market figures; not minute-by-minute.",
        },
        "angel_one": {},
        "participant_positions": {
            "status": "NOT_CONNECTED",
            "note": (
                "FII participant-wise Futures/Options long-short "
                "data is a separate report and is not connected yet."
            ),
        },
        "note": (
            "PCR and OI are market-wide indicators. "
            "They do not identify individual FII or DII trades."
        ),
    }

    try:
        fii_rows = fetch_fii_dii()

        if fii_rows:
            result["fii_dii"]["status"] = "CONNECTED"
            result["fii_dii"]["data"] = fii_rows

    except Exception as error:
        result["fii_dii"]["error"] = str(error)

    result["angel_one"] = fetch_angel_data()

    result["updated_at"] = datetime.now(IST).isoformat()

    _cache["time"] = now
    _cache["data"] = result

    return result
