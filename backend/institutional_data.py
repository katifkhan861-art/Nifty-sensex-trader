
from datetime import datetime
from zoneinfo import ZoneInfo

from smartapi_client import connect_angel

IST = ZoneInfo("Asia/Kolkata")


def get_institutional_data():
    result = {
        "updated_at": datetime.now(IST).isoformat(),
        "source": "Angel One SmartAPI",
        "status": "UNAVAILABLE",
        "pcr": None,
        "nifty_pcr": None,
        "oi_buildup": {},
        "fii_dii": {
            "status": "DAILY_REPORT_REQUIRED",
            "message": "Official FII/DII daily report is not connected yet."
        },
        "note": (
            "PCR and OI buildup are market-wide indicators. "
            "They are not proof of FII/DII individual trades."
        )
    }

    try:
        api = connect_angel()
        response = api.putCallRatio()

        if response and response.get("status"):
            rows = response.get("data") or []

            for row in rows:
                symbol = str(
                    row.get("tradingSymbol", "")
                ).upper()

                if symbol.startswith("NIFTY"):
                    try:
                        result["nifty_pcr"] = float(row["pcr"])
                        result["pcr"] = result["nifty_pcr"]
                        result["status"] = "CONNECTED"
                        break
                    except (KeyError, TypeError, ValueError):
                        continue

        buildup_types = [
            "Long Built Up",
            "Short Built Up",
            "Long Unwinding",
            "Short Covering",
        ]

        for buildup_type in buildup_types:
            try:
                buildup = api.oIBuildup({
                    "expirytype": "NEAR",
                    "datatype": buildup_type
                })

                if buildup and buildup.get("status"):
                    rows = buildup.get("data") or []
                    result["oi_buildup"][buildup_type] = [
                        row for row in rows
                        if "NIFTY" in str(row).upper()
                    ]
                else:
                    result["oi_buildup"][buildup_type] = []

            except Exception:
                result["oi_buildup"][buildup_type] = []

    except Exception as error:
        result["error"] = str(error)

    return result
