
from pathlib import Path
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
import re
import math

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from market_data import (
    get_market_status,
    get_market_quote,
    get_historical_candles,
)
from indicators import calculate_indicators
from signals import generate_signal
from institutional_data import get_institutional_data


IST = ZoneInfo("Asia/Kolkata")

app = FastAPI(title="NIFTY SENSEX Trading API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

FRONTEND_FILE = Path(__file__).resolve().parent.parent / "index.html"


@app.get("/", include_in_schema=False)
def home():
    if FRONTEND_FILE.exists():
        return FileResponse(FRONTEND_FILE)

    return {"message": "NIFTY SENSEX API is running"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "NIFTY SENSEX Trading API",
    }


def safe_number(value):
    try:
        number = float(value)

        if not math.isfinite(number):
            return None

        return number

    except (TypeError, ValueError):
        return None


@app.get("/api/status")
def status():
    broker = get_market_status()

    now = datetime.now(IST)
    current_time = now.time()

    # Basic weekday and market-hours check.
    # Exchange holidays are not checked here.
    market_session_open = (
        now.weekday() < 5
        and time(9, 15) <= current_time <= time(15, 30)
    )

    markets = {}

    for symbol in ["NIFTY", "SENSEX"]:
        try:
            result = get_market_quote(symbol)
            data = result.get("data") or {}

            price = safe_number(data.get("ltp"))

            connected = (
                result.get("connected", False)
                and price is not None
                and price > 0
            )

            markets[symbol] = {
                "status": (
                    "QUOTE_RECEIVED"
                    if connected
                    else "DATA_UNAVAILABLE"
                ),
                "price": price,
            }

        except Exception as error:
            markets[symbol] = {
                "status": "ERROR",
                "price": None,
                "error": str(error),
            }

    broker_connected = bool(broker.get("connected", False))

    quote_data_available = all(
        markets[symbol]["status"] == "QUOTE_RECEIVED"
        for symbol in ["NIFTY", "SENSEX"]
    )

    return {
        "mode": broker.get("mode", "DEMO"),
        "message": broker.get(
            "message",
            "Connection check completed"
        ),
        "nifty": markets["NIFTY"]["status"],
        "sensex": markets["SENSEX"]["status"],
        "markets": markets,
        "broker_connected": broker_connected,
        "market_session_open": market_session_open,
        "quote_data_available": quote_data_available,
        "live_data": (
            broker_connected
            and quote_data_available
            and market_session_open
        ),
        "updated_at": now.isoformat(),
        "note": (
            "Market session is based on weekday and clock time. "
            "Exchange holidays and quote timestamp freshness "
            "are not independently verified."
        ),
    }


@app.get("/api/market/overview")
def market_overview():
    markets = {}

    for symbol in ["NIFTY", "SENSEX"]:
        result = get_market_quote(symbol)

        if result.get("connected"):
            data = result.get("data") or {}

            markets[symbol] = {
                "price": safe_number(data.get("ltp")),
                "mode": "BROKER_CONNECTED",
            }
        else:
            markets[symbol] = {
                "price": None,
                "mode": "DATA UNAVAILABLE",
                "error": result.get("error"),
            }

    return {
        "markets": markets,
        "updated_at": datetime.now(IST).isoformat(),
    }


def get_closed_candles(candles, timeframe):
    """
    Analysis mein sirf completed candles use karta hai.
    Angel One timestamps ko candle start time maana gaya hai.
    """

    now = datetime.now(IST)

    durations = {
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
    }

    if timeframe not in ["15m", "1h", "1d"]:
        raise ValueError("Unsupported timeframe")

    closed = []

    for candle in candles:
        try:
            candle_time = datetime.fromisoformat(
                str(candle["time"]).replace("Z", "+00:00")
            )

            if candle_time.tzinfo is None:
                candle_time = candle_time.replace(tzinfo=IST)
            else:
                candle_time = candle_time.astimezone(IST)

            market_close = datetime.combine(
                candle_time.date(),
                time(15, 30),
                tzinfo=IST,
            )

            if timeframe == "1d":
                candle_end = market_close
            else:
                candle_end = min(
                    candle_time + durations[timeframe],
                    market_close,
                )

            if candle_end <= now:
                closed.append(candle)

        except (ValueError, TypeError, KeyError):
            continue

    if not closed:
        raise RuntimeError(
            f"No completed candles available for {timeframe}"
        )

    return closed


def analyze_timeframe(symbol, timeframe):
    candles = get_historical_candles(symbol, timeframe)

    candles = get_closed_candles(candles, timeframe)

    indicators = calculate_indicators(candles)

    if "error" in indicators:
        raise RuntimeError(indicators["error"])

    price = indicators["close"]
    ema20 = indicators["ema_20"]
    ema50 = indicators["ema_50"]
    rsi = indicators["rsi"]
    macd = indicators["macd"]
    macd_signal = indicators["macd_signal"]
    atr = indicators["atr"]
    adx = indicators["adx"]

    signal = generate_signal(
        price=price,
        ema_20=ema20,
        ema_50=ema50,
        rsi=rsi,
        macd=macd,
        macd_signal=macd_signal,
        atr=atr,
        adx=adx,
    )

    if (
        price > ema20
        and ema20 > ema50
        and macd > macd_signal
    ):
        direction = "BULLISH"

    elif (
        price < ema20
        and ema20 < ema50
        and macd < macd_signal
    ):
        direction = "BEARISH"

    else:
        direction = "NEUTRAL"

    return {
        "timeframe": timeframe,
        "direction": direction,
        "price": price,
        "indicators": {
            "ema_20": ema20,
            "ema_50": ema50,
            "rsi": rsi,
            "macd": macd,
            "macd_signal": macd_signal,
            "atr": atr,
            "adx": adx,
        },
        "signal": signal,
        "candle_confirmation": "CLOSED_CANDLES_ONLY",
    }


def build_participant_summary(participant_data):
    """
    NSE participant-wise daily OI summary.
    Net index futures aur net index options alag rakhta hai.
    """

    if not isinstance(participant_data, dict):
        return {
            "status": "UNAVAILABLE",
            "note": "Participant data unavailable.",
        }

    status_value = participant_data.get(
        "status",
        "UNAVAILABLE"
    )

    rows = participant_data.get("data", []) or []

    if status_value != "CONNECTED" or not rows:
        return {
            "status": status_value,
            "date": participant_data.get("date"),
            "participants": {},
            "note": "Valid participant-wise data available nahi hai.",
        }

    participants = {}

    for row in rows:
        name = str(
            row.get("participant", "")
        ).upper().strip()

        if name not in ["FII", "DII", "PRO", "CLIENT"]:
            continue

        participants[name] = {
            "net_index_futures": safe_number(
                row.get("net_index_futures")
            ),
            "net_stock_futures": safe_number(
                row.get("net_stock_futures")
            ),
            "net_index_options": safe_number(
                row.get("net_index_options")
            ),
            "total_long_contracts": safe_number(
                row.get("total_long_contracts")
            ),
            "total_short_contracts": safe_number(
                row.get("total_short_contracts")
            ),
        }

    def get_position(value):
        if value is None:
            return "UNKNOWN"

        if value > 0:
            return "NET_LONG"

        if value < 0:
            return "NET_SHORT"

        return "NEUTRAL"

    fii = participants.get("FII", {})
    dii = participants.get("DII", {})

    fii_net = fii.get("net_index_futures")
    dii_net = dii.get("net_index_futures")

    return {
        "status": "CONNECTED",
        "date": participant_data.get("date"),
        "unit": participant_data.get("unit", "contracts"),
        "participants": participants,
        "interpretation": {
            "fii_index_futures": get_position(fii_net),
            "dii_index_futures": get_position(dii_net),
            "fii_net_index_futures": fii_net,
            "dii_net_index_futures": dii_net,
            "options_direction": "NOT_DETERMINED",
        },
        "note": (
            "Participant-wise figures are daily aggregate "
            "derivative positions. Index futures may include "
            "multiple indices; they are not NIFTY-only or "
            "SENSEX-only positions."
        ),
    }


def get_institutional_summary(symbol):
    try:
        data = get_institutional_data()

        fii_data = data.get("fii_dii", {})
        rows = fii_data.get("data", [])

        fii_net = None
        dii_net = None
        report_date = None

        for row in rows:
            category = str(
                row.get("category", "")
            ).upper()

            net = safe_number(row.get("net_value_cr"))

            if net is None:
                continue

            if "FII" in category or "FPI" in category:
                fii_net = net
                report_date = row.get("date") or report_date

            elif "DII" in category:
                dii_net = net
                report_date = row.get("date") or report_date

        if fii_net is None or dii_net is None:
            fii_dii_bias = "UNKNOWN"

        elif fii_net > 0 and dii_net > 0:
            fii_dii_bias = "BOTH_BUYING"

        elif fii_net < 0 and dii_net < 0:
            fii_dii_bias = "BOTH_SELLING"

        else:
            fii_dii_bias = "MIXED"

        angel = data.get("angel_one", {})
        pcr_data = angel.get("pcr", {})

        nifty_pcr = None
        nifty_pcr_symbol = None

        if symbol == "NIFTY":
            for pcr_symbol, value in pcr_data.items():
                if re.match(
                    r"^NIFTY\d.*FUT$",
                    pcr_symbol.upper()
                ):
                    nifty_pcr = safe_number(value)
                    nifty_pcr_symbol = pcr_symbol
                    break

        oi_data = angel.get("oi_buildup", {})
        oi_summary = {}

        for category in [
            "LONG_BUILT_UP",
            "SHORT_BUILT_UP",
            "SHORT_COVERING",
            "LONG_UNWINDING",
        ]:
            records = oi_data.get(category, []) or []

            oi_summary[category] = {
                "count": len(records),
                "symbols": [
                    item.get("symbol")
                    for item in records
                    if item.get("symbol")
                ],
            }

        participant_data = data.get(
            "participant_positions",
            {}
        )

        participant_summary = build_participant_summary(
            participant_data
        )

        return {
            "fii_dii": {
                "status": fii_data.get(
                    "status",
                    "UNAVAILABLE"
                ),
                "date": report_date,
                "fii_net_cr": fii_net,
                "dii_net_cr": dii_net,
                "bias": fii_dii_bias,
            },
            "pcr": {
                "status": (
                    angel.get("pcr_status", "UNAVAILABLE")
                    if symbol == "NIFTY"
                    else "NOT_APPLICABLE"
                ),
                "symbol": nifty_pcr_symbol,
                "value": nifty_pcr,
            },
            "oi_buildup": {
                "status": angel.get(
                    "oi_buildup_status",
                    "UNAVAILABLE"
                ),
                "categories": oi_summary,
                "note": (
                    "These are stock futures buildup lists, "
                    "not direct NIFTY or SENSEX index OI."
                ),
            },
            "participant_positions": participant_data,
            "participant_summary": participant_summary,
        }

    except Exception as error:
        return {
            "status": "UNAVAILABLE",
            "error": str(error),
        }


@app.get("/api/market/analysis")
def market_analysis(
    symbol: str = "NIFTY",
    timeframe: str = "15m",
):
    symbol = symbol.upper()

    labels = {
        "15m": "15 Minute",
        "1h": "1 Hour",
        "1d": "Daily",
    }

    if symbol not in ["NIFTY", "SENSEX"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid symbol",
        )

    if timeframe not in labels:
        raise HTTPException(
            status_code=400,
            detail="Invalid timeframe",
        )

    try:
        result = analyze_timeframe(symbol, timeframe)

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "timeframe_label": labels[timeframe],
            **result,
            "updated_at": datetime.now(IST).isoformat(),
        }

    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Market data unavailable: {str(error)}",
        )


@app.get("/api/market/combined")
def combined_market_analysis(symbol: str = "NIFTY"):
    symbol = symbol.upper()

    if symbol not in ["NIFTY", "SENSEX"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid symbol",
        )

    try:
        daily = analyze_timeframe(symbol, "1d")
        hourly = analyze_timeframe(symbol, "1h")
        fifteen = analyze_timeframe(symbol, "15m")

        institutional = get_institutional_summary(symbol)

        daily_direction = daily["direction"]
        hourly_direction = hourly["direction"]
        fifteen_direction = fifteen["direction"]

        daily_signal = daily["signal"].get("signal", "WAIT")
        hourly_signal = hourly["signal"].get("signal", "WAIT")
        fifteen_signal = fifteen["signal"].get("signal", "WAIT")

        final_signal = "WAIT"

        reason = (
            "Daily, 1-hour aur 15-minute confirmation "
            "abhi ek direction mein nahi hain."
        )

        if (
            daily_direction == "BULLISH"
            and hourly_direction == "BULLISH"
            and fifteen_direction == "BULLISH"
            and daily_signal == "CALL BIAS"
            and hourly_signal == "CALL BIAS"
            and fifteen_signal == "CALL BIAS"
        ):
            final_signal = "CALL BIAS"

            reason = (
                "Daily, 1-hour aur 15-minute teeno "
                "CALL direction confirm kar rahe hain."
            )

        elif (
            daily_direction == "BEARISH"
            and hourly_direction == "BEARISH"
            and fifteen_direction == "BEARISH"
            and daily_signal == "PUT BIAS"
            and hourly_signal == "PUT BIAS"
            and fifteen_signal == "PUT BIAS"
        ):
            final_signal = "PUT BIAS"

            reason = (
                "Daily, 1-hour aur 15-minute teeno "
                "PUT direction confirm kar rahe hain."
            )

        entry = None
        stop_loss = None
        target = None
        risk_reward = None

        exit_condition = (
            "WAIT: clear confirmation ka intezar karein."
        )

        if final_signal in ["CALL BIAS", "PUT BIAS"]:
            entry = fifteen["signal"].get("entry")
            stop_loss = fifteen["signal"].get("stop_loss")
            target = fifteen["signal"].get("target")
            risk_reward = fifteen["signal"].get("risk_reward")

            if final_signal == "CALL BIAS":
                exit_condition = (
                    "Stop-loss hit hone par exit karein, "
                    "target par profit book karein, ya 15-minute "
                    "candle EMA20 ke neeche close ho to "
                    "position dobara evaluate karein."
                )

            else:
                exit_condition = (
                    "Stop-loss hit hone par exit karein, "
                    "target par profit book karein, ya 15-minute "
                    "candle EMA20 ke upar close ho to "
                    "position dobara evaluate karein."
                )

        confirmation = {
            "daily": {
                "direction": daily_direction,
                "signal": daily_signal,
            },
            "one_hour": {
                "direction": hourly_direction,
                "signal": hourly_signal,
            },
            "fifteen_minute": {
                "direction": fifteen_direction,
                "signal": fifteen_signal,
            },
        }

        return {
            "symbol": symbol,
            "signal": final_signal,
            "direction": (
                "BULLISH" if final_signal == "CALL BIAS"
                else "BEARISH" if final_signal == "PUT BIAS"
                else "NEUTRAL"
            ),
            "entry": entry,
            "stop_loss": stop_loss,
            "target": target,
            "risk_reward": risk_reward,
            "exit_condition": exit_condition,
            "reason": reason,
            "confirmation": confirmation,
            "institutional": institutional,
            "signal_method": {
                "daily": "Overall market direction",
                "one_hour": "Trend confirmation",
                "fifteen_minute": (
                    "Entry and risk levels using closed candles"
                ),
                "ema": "Trend confirmation",
                "rsi": "Momentum confirmation",
                "macd": "Momentum direction confirmation",
                "adx": "Trend strength confirmation",
                "atr": "Volatility-based risk levels",
                "fii_dii": "Daily supporting context",
                "pcr": (
                    "Supporting options context, "
                    "not standalone trigger"
                ),
                "oi_buildup": (
                    "Stock futures breadth context, "
                    "not direct index trigger"
                ),
                "participant_positions": (
                    "Daily aggregate derivative positioning. "
                    "Supporting context only."
                ),
            },
            "timeframes": {
                "daily": daily,
                "one_hour": hourly,
                "fifteen_minute": fifteen,
            },
            "risk_note": (
                "Entry, target and stop-loss are index levels, "
                "not option premium. These are analytical levels, "
                "not guaranteed outcomes. Confirm live price, "
                "liquidity and risk before trading. "
                "Participant positions are daily aggregate data "
                "and may not represent NIFTY-only or SENSEX-only "
                "positions. Exit conditions require manual monitoring."
            ),
            "updated_at": datetime.now(IST).isoformat(),
        }

    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Combined analysis unavailable: {str(error)}",
        )


@app.get("/api/market/institutional")
def institutional_data():
    try:
        return get_institutional_data()

    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Institutional data unavailable: {str(error)}",
        )
