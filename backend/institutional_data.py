
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

# Correct NSE archive domain
PARTICIPANT_URL = (
    "https://nsearchives.nseindia.com/content/nsccl/"
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
        ch.lower()
        for ch in str(value).strip().lstrip("\ufeff")
        if ch.isalnum()
    )


def fetch_fii_dii():
    session = requests.Session()
    session.headers.update(HEADERS)

    session.get(NSE_HOME, timeout=15)
    session.get(NSE_REPORT, timeout=15)

    response = session.get(NSE_API, timeout=20)
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


def _parse_participant_csv(content):
    text = content.decode("utf-8-sig", errors="replace")

    reader = csv.reader(io.StringIO(text))
    all_rows = list(reader)

    if not all_rows:
        raise ValueError("CSV file is empty")

    # Find the actual header row
    header_index = None

    for index, row in enumerate(all_rows):
        normalized = {_normalized(x) for x in row}

        if (
            "clienttype" in normalized
            and "futureindexlong" in normalized
            and "futureindexshort" in normalized
        ):
            header_index = index
            break

    if header_index is None:
        raise ValueError(
            "Expected NSE participant CSV headers were not found"
        )

    headers = [
        _normalized(value)
        for value in all_rows[header_index]
    ]

    required_columns = [
        "clienttype",
        "futureindexlong",
        "futureindexshort",
        "futurestocklong",
        "futurestockshort",
        "optionindexcalllong",
        "optionindexputlong",
        "optionindexcallshort",
        "optionindexputshort",
        "totallongcontracts",
        "totalshortcontracts",
    ]

    missing = [
        column for column in required_columns
        if column not in headers
    ]

    if missing:
        raise ValueError(
            "Missing CSV columns: " + ", ".join(missing)
        )

    parsed = []

    for raw_row in all_rows[header_index + 1:]:
        if not raw_row:
            continue

        values = {
            headers[i]: raw_row[i].strip()
            for i in range(min(len(headers), len(raw_row)))
        }

        participant = values.get("clienttype", "").strip()

        if not participant:
            continue

        def get_value(column):
            return _number(values.get(column)) or 0

        future_index_long = get_value("futureindexlong")
        future_index_short = get_value("futureindexshort")

        future_stock_long = get_value("futurestocklong")
        future_stock_short = get_value("futurestockshort")

        call_long = get_value("optionindexcalllong")
        put_long = get_value("optionindexputlong")
        call_short = get_value("optionindexcallshort")
        put_short = get_value("optionindexputshort")

        total_long = get_value("totallongcontracts")
        total_short = get_value("totalshortcontracts")

        parsed.append({
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
                call_long + put_long - call_short - put_short
            ),

            "total_long_contracts": total_long,
            "total_short_contracts": total_short,
            "net_total_contracts": total_long - total_short,
        })

    parsed = [
        row for row in parsed
        if row["participant"] not in ("TOTAL", "GRAND TOTAL")
    ]

    if not parsed:
        raise ValueError("No participant records found in CSV")

    return parsed


def fetch_participant_positions():
    session = requests.Session()
    session.headers.update({
        **HEADERS,
        "Accept": "text/csv,application/csv,text/plain,*/*",
    })

    errors = []
    today = datetime.now(IST).date()

    # Search latest available report over 15 calendar days
    for offset in range(15):
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

            if not response.content:
                errors.append(f"{date_string}: Empty response")
                continue

            if response.content.lstrip().startswith(b"<"):
                errors.append(
                    f"{date_string}: Received HTML instead of CSV"
                )
                continue

            rows = _parse_participant_csv(response.content)

            return {
                "status": "CONNECTED",
                "source": "NSE India",
                "report": "F&O Participant-wise Open Interest",
                "date": report_date.isoformat(),
                "unit": "contracts",
                "data": rows,
                "note": (
                    "Daily participant-wise open interest. "
                    "Not live data and not rupee cash flows. "
                    "Net positions are calculated from reported contracts."
                ),
            }

        except Exception as error:
            errors.append(
                f"{date_string}: {str(error)}"
            )

    return {
        "status": "NOT_CONNECTED",
        "source": "NSE India",
        "data": [],
        "errors": errors[-8:],
        "note": (
            "NSE participant-wise CSV could not be retrieved "
            "or did not match the expected format."
        ),
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
                "CONNECTED" if result["pcr"] else "NO_DATA"
            )

        except Exception as error:
            result["pcr_status"] = "ERROR"
            result["pcr_error"] = str(error)

        # OI BUILDUP
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

    # NSE participant-wise positions
    result["participant_positions"] = (
        fetch_participant_positions()
    )

    result["updated_at"] = datetime.now(IST).isoformat()

    _cache["time"] = time.time()
    _cache["data"] = result

    return result
