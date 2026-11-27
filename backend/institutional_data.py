
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import time
import requests
import csv
import io

from market_data import get_api, api_request

IST = ZoneInfo("Asia/Kolkata")

NSE_HOME = "https://www.nseindia.com"
NSE_REPORT = "https://www.nseindia.com/reports/fii-dii"
NSE_API = "https://www.nseindia.com/api/fiidiiTradeReact"

PARTICIPANT_URL = (
    "https://archives.nseindia.com/content/nsccl/"
    "fao_participant_oi_{date}.csv"
)

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
        if value in (None, ""):
            return None
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _normalized(value):
    return "".join(
        ch.lower() for ch in str(value)
        if ch.isalnum()
    )


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


def fetch_participant_positions():
    session = requests.Session()
    session.headers.update({
        **HEADERS,
        "Accept": "text/csv,application/csv,text/plain,*/*",
    })

    errors = []

    # Aaj aur pichhle 7 calendar days ki files check karein.
    today = datetime.now(IST).date()

    for offset in range(8):
        report_date = today - timedelta(days=offset)
        date_string = report_date.strftime("%d%m%Y")

        url = PARTICIPANT_URL.format(date=date_string)

        try:
            response = session.get(url, timeout=20)

            if response.status_code != 200:
                errors.append(
                    f"{date_string}: HTTP {response.status_code}"
                )
                continue

            content = response.content.decode(
                "utf-8-sig", errors="replace"
            ).strip()

            if not content or content.startswith("<"):
                errors.append(f"{date_string}: Invalid CSV")
                continue

            reader = csv.DictReader(io.StringIO(content))

            if not reader.fieldnames:
                errors.append(f"{date_string}: Missing CSV headers")
                continue

            rows = []

            for raw_row in reader:
                row = {
                    _normalized(key): value
                    for key, value in raw_row.items()
                    if key is not None
                }

                participant = (
                    row.get("clienttype")
                    or row.get("participanttype")
                    or row.get("participant")
                    or ""
                ).strip()

                if not participant:
                    continue

                def get_value(*names):
                    for name in names:
                        value = _number(row.get(_normalized(name)))
                        if value is not None:
                            return value
                    return 0

                future_index_long = get_value(
                    "Future Index Long"
                )
                future_index_short = get_value(
                    "Future Index Short"
                )
                future_stock_long = get_value(
                    "Future Stock Long"
                )
                future_stock_short = get_value(
                    "Future Stock Short"
                )

                call_long = get_value(
                    "Option Index Call Long"
                )
                put_long = get_value(
                    "Option Index Put Long"
                )
                call_short = get_value(
                    "Option Index Call Short"
                )
                put_short = get_value(
                    "Option Index Put Short"
                )

                total_long = get_value(
                    "Total Long Contracts"
                )
                total_short = get_value(
                    "Total Short Contracts"
                )

                rows.append({
                    "participant": participant.upper(),

                    "future_index_long": future_index_long,
                    "future_index_short": future_index_short,
                    "net_index_futures": (
                        future_index_long - future_index_short
                    ),

                    "future_stock_long": future_stock_long,
                    "future_stock_short": future_stock_short,
                    "net_stock_futures": (
                        future_stock_long - future_stock_short
                    ),

                    "index_call_long": call_long,
                    "index_put_long": put_long,
                    "index_call_short": call_short,
                    "index_put_short": put_short,

                    "net_index_options": (
                        call_long + put_long
                        - call_short - put_short
                    ),

                    "total_long_contracts": total_long,
                    "total_short_contracts": total_short,
                    "net_total_contracts": (
                        total_long - total_short
                    ),
                })

            useful_rows = [
                row for row in rows
                if row["participant"] != "TOTAL"
            ]

            if useful_rows:
                return {
                    "status": "CONNECTED",
                    "source": "NSE India",
                    "report": "Participant-wise Open Interest",
                    "date": report_date.isoformat(),
                    "unit": "contracts",
                    "data": useful_rows,
                    "note": (
                        "Daily participant-wise open interest. "
                        "Not live data and not rupee cash flows."
                    ),
                }

            errors.append(f"{date_string}: No participant rows")

        except Exception as error:
            errors.append(f"{date_string}: {str(error)}")

    return {
        "status": "NOT_CONNECTED",
        "source": "NSE India",
        "data": [],
        "errors": errors[-5:],
        "note": "Participant-wise CSV could not be retrieved.",
    }


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
                "CONNECTED" if result["pcr"] else "NO_DATA"
            )

        except Exception as error:
            result["pcr_status"] = "ERROR"
            result["pcr_error"] = str(error)

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
            "source": "NSE India",
            "data": [],
            "note": "Participant-wise data is not connected.",
        },

        "note": (
            "FII/DII values are daily cash-market data. "
            "Participant positions are daily derivative contracts. "
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

    # NEW: NSE participant-wise positions
    result["participant_positions"] = (
        fetch_participant_positions()
    )

    result["updated_at"] = datetime.now(IST).isoformat()

    _cache["time"] = time.time()
    _cache["data"] = result

    return result
