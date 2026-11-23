from smartapi_client import connect_angel


def get_market_status():
    return {
        "connected": False,
        "mode": "DEMO",
        "message": "Live market data setup pending"
    }


def get_market_quote(symbol_token, exchange="NSE"):
    try:
        smart_api = connect_angel()
        result = smart_api.ltpData(
            exchange,
            "NIFTY",
            str(symbol_token)
        )
        return result
    except Exception as error:
        return {
            "connected": False,
            "error": str(error)
        }
