
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

APP_TITLE = "NIFTY SENSEX Trading API"

SUPPORTED_SYMBOLS = ("NIFTY", "SENSEX")

TIMEFRAME_LABELS = {
    "15m": "15 Minute",
    "1h": "1 Hour",
    "1d": "Daily",
}

QUOTE_MAX_AGE_SECONDS = 180

app = FastAPI(title=APP_TITLE)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


FRONTEND_FILE = (
    Path(__file__).resolve().parent.parent / "index.html"
)


# =========================================================
# BASIC HELPERS
# =========================================================

def now_ist():
    return datetime.now(IST)


def safe_number(value):
    try:
        if value is None:
            return None

        number = float(value)

        if not math.isfinite(number):
            return None

        return number

    except (TypeError, ValueError, OverflowError):
        return None


def parse_datetime(value):
    """
    ISO timestamp aur Unix timestamp dono support karta hai.
    """

    if value is None:
        return None

    try:
        if isinstance(value, (int, float)):
            timestamp = float(value)

            if timestamp > 100000000000:
                timestamp /= 1000

            return datetime.fromtimestamp(
                timestamp,
                tz=IST,
            )

        value = str(value).strip()

        if not value:
            return None

        try:
            parsed = datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )
        except ValueError:
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)

        return parsed.astimezone(IST)

    except (ValueError, TypeError, OverflowError, OSError):
        return None


def extract_quote_timestamp(data):
    """
    Angel One quote response mein timestamp ke common
    field names check karta hai.

    Timestamp field na mile to None return karta hai.
    """

    if not isinstance(data, dict):
        return None

    possible_fields = [
        "exchange_timestamp",
        "exchangeTimestamp",
        "exch_feed_time",
        "exch_trade_time",
        "last_traded_timestamp",
        "lastTradeTime",
        "timestamp",
        "trade_timestamp",
        "feed_time",
    ]

    for field in possible_fields:
        value = data.get(field)

        parsed = parse_datetime(value)

        if parsed is not None:
            return parsed

    return None


def get_quote_freshness(data, current_time=None):
    current_time = current_time or now_ist()

    quote_time = extract_quote_timestamp(data)

    if quote_time is None:
        return {
            "status": "UNKNOWN",
            "timestamp": None,
            "age_seconds": None,
            "fresh": False,
        }

    age = (current_time - quote_time).total_seconds()

    if age < 0:
        return {
            "status": "INVALID_TIMESTAMP",
            "timestamp": quote_time.isoformat(),
            "age_seconds": round(age, 2),
            "fresh": False,
        }

    fresh = age <= QUOTE_MAX_AGE_SECONDS

    return {
        "status": "FRESH" if fresh else "STALE",
        "timestamp": quote_time.isoformat(),
        "age_seconds": round(age, 2),
        "fresh": fresh,
    }


def market_is_open(current_time=None):
    current_time = current_time or now_ist()

    current_clock = current_time.time()

    return (
        current_time.weekday() < 5
        and time(9, 15) <= current_clock <= time(15, 30)
    )


def normalize_symbol(symbol):
    symbol = str(symbol).upper().strip()

    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail="Invalid symbol. Use NIFTY or SENSEX.",
        )

    return symbol


def validate_timeframe(timeframe):
    if timeframe not in TIMEFRAME_LABELS:
        raise HTTPException(
            status_code=400,
            detail="Invalid timeframe. Use 15m, 1h or 1d.",
        )

    return timeframe


# =========================================================
# HOME AND HEALTH
# =========================================================

@app.get("/", include_in_schema=False)
def home():
    if FRONTEND_FILE.exists():
        return FileResponse(FRONTEND_FILE)

    return {
        "message": "NIFTY SENSEX API is running",
        "status": "ok",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": APP_TITLE,
        "updated_at": now_ist().isoformat(),
    }


# =========================================================
# API STATUS
# =========================================================

@app.get("/api/status")
def status():

    current_time = now_ist()

    try:
        broker = get_market_status() or {}
    except Exception as error:
        broker = {
            "connected": False,
            "mode": "ERROR",
            "message": str(error),
        }

    markets = {}

    for symbol in SUPPORTED_SYMBOLS:

        try:
            result = get_market_quote(symbol) or {}

            data = result.get("data") or {}

            price = safe_number(data.get("ltp"))

            connected = (
                result.get("connected", False)
                and price is not None
                and price > 0
            )

            freshness = get_quote_freshness(
                data,
                current_time,
            )

            markets[symbol] = {
                "status": (
                    "QUOTE_RECEIVED"
                    if connected
                    else "DATA_UNAVAILABLE"
                ),
                "price": price,
                "quote_freshness": freshness,
            }

        except Exception as error:

            markets[symbol] = {
                "status": "ERROR",
                "price": None,
                "quote_freshness": {
                    "status": "UNKNOWN",
                    "fresh": False,
                },
                "error": str(error),
            }

    broker_connected = bool(
        broker.get("connected", False)
    )

    quote_data_available = all(
        markets[symbol]["status"] == "QUOTE_RECEIVED"
        for symbol in SUPPORTED_SYMBOLS
    )

    all_quotes_fresh = all(
        markets[symbol]["quote_freshness"]["fresh"]
        for symbol in SUPPORTED_SYMBOLS
    )

    session_open = market_is_open(current_time)

    live_data = (
        broker_connected
        and quote_data_available
        and all_quotes_fresh
        and session_open
    )

    return {
        "mode": broker.get("mode", "DEMO"),

        "message": broker.get(
            "message",
            "Connection check completed",
        ),

        "nifty": markets["NIFTY"]["status"],
        "sensex": markets["SENSEX"]["status"],

        "markets": markets,

        "broker_connected": broker_connected,

        "market_session_open": session_open,

        "quote_data_available": quote_data_available,

        "quote_freshness_verified": all_quotes_fresh,

        "live_data": live_data,

        "live_data_status": (
            "LIVE"
            if live_data
            else "NOT_VERIFIED"
        ),

        "updated_at": current_time.isoformat(),

        "note": (
            "Live data requires broker connection, market session "
            "and fresh exchange timestamps. If the broker response "
            "does not contain a recognized timestamp, freshness "
            "remains UNKNOWN. Exchange holidays are not independently "
            "verified."
        ),
    }


# =========================================================
# MARKET OVERVIEW
# =========================================================

@app.get("/api/market/overview")
def market_overview():

    current_time = now_ist()

    markets = {}

    for symbol in SUPPORTED_SYMBOLS:

        try:
            result = get_market_quote(symbol) or {}

            data = result.get("data") or {}

            price = safe_number(data.get("ltp"))

            connected = (
                result.get("connected", False)
                and price is not None
                and price > 0
            )

            markets[symbol] = {
                "price": price if connected else None,

                "mode": (
                    "BROKER_CONNECTED"
                    if connected
                    else "DATA_UNAVAILABLE"
                ),

                "quote_freshness": get_quote_freshness(
                    data,
                    current_time,
                ),
            }

        except Exception as error:

            markets[symbol] = {
                "price": None,
                "mode": "ERROR",
                "error": str(error),
            }

    return {
        "markets": markets,
        "updated_at": current_time.isoformat(),
    }


# =========================================================
# CLOSED CANDLE FILTER
# =========================================================

def get_closed_candles(candles, timeframe):

    current_time = now_ist()

    durations = {
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
    }

    if timeframe not in ["15m", "1h", "1d"]:
        raise ValueError("Unsupported timeframe")

    closed = []

    for candle in candles:

        try:
            candle_time = parse_datetime(
                candle.get("time")
            )

            if candle_time is None:
                continue

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

            if candle_end <= current_time:
                closed.append(candle)

        except (ValueError, TypeError, KeyError):
            continue

    if not closed:
        raise RuntimeError(
            f"No completed candles available for {timeframe}"
        )

    closed.sort(
        key=lambda candle: parse_datetime(
            candle.get("time")
        )
    )

    return closed


# =========================================================
# TIMEFRAME ANALYSIS
# =========================================================

def analyze_timeframe(symbol, timeframe):

    symbol = normalize_symbol(symbol)
    timeframe = validate_timeframe(timeframe)

    candles = get_historical_candles(
        symbol,
        timeframe,
    )

    if not candles:
        raise RuntimeError(
            f"No historical candles available for {symbol} {timeframe}"
        )

    candles = get_closed_candles(
        candles,
        timeframe,
    )

    indicators = calculate_indicators(candles)

    if not isinstance(indicators, dict):
        raise RuntimeError("Invalid indicator response")

    if "error" in indicators:
        raise RuntimeError(indicators["error"])

    required = [
        "close",
        "ema_20",
        "ema_50",
        "rsi",
        "macd",
        "macd_signal",
        "atr",
        "adx",
    ]

    values = {}

    for field in required:

        value = safe_number(
            indicators.get(field)
        )

        if value is None:
            raise RuntimeError(
                f"Invalid or missing indicator: {field}"
            )

        values[field] = value

    price = values["close"]
    ema20 = values["ema_20"]
    ema50 = values["ema_50"]
    rsi = values["rsi"]
    macd = values["macd"]
    macd_signal = values["macd_signal"]
    atr = values["atr"]
    adx = values["adx"]

    if price <= 0 or atr < 0:
        raise RuntimeError("Invalid price or ATR")

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

    if not isinstance(signal, dict):
        raise RuntimeError("Invalid signal response")

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


# =========================================================
# PARTICIPANT POSITION SUMMARY
# =========================================================

def build_participant_summary(participant_data):

    if not isinstance(participant_data, dict):

        return {
            "status": "UNAVAILABLE",
            "note": "Participant data unavailable.",
        }

    status_value = participant_data.get(
        "status",
        "UNAVAILABLE",
    )

    rows = participant_data.get("data", []) or []

    if status_value != "CONNECTED" or not rows:

        return {
            "status": status_value,
            "date": participant_data.get("date"),
            "participants": {},
            "note": "Valid participant-wise data unavailable.",
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

        "unit": participant_data.get(
            "unit",
            "contracts",
        ),

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


# =========================================================
# INSTITUTIONAL DATA SUMMARY
# =========================================================

def get_institutional_summary(symbol):

    try:

        data = get_institutional_data() or {}

        if not isinstance(data, dict):
            raise RuntimeError("Invalid institutional data response")

        fii_data = data.get("fii_dii", {}) or {}

        rows = fii_data.get("data", []) or []

        fii_net = None
        dii_net = None
        report_date = None

        for row in rows:

            category = str(
                row.get("category", "")
            ).upper()

            net = safe_number(
                row.get("net_value_cr")
            )

            if net is None:
                continue

            if "FII" in category or "FPI" in category:

                fii_net = net

                report_date = (
                    row.get("date") or report_date
                )

            elif "DII" in category:

                dii_net = net

                report_date = (
                    row.get("date") or report_date
                )

        if fii_net is None or dii_net is None:

            fii_dii_bias = "UNKNOWN"

        elif fii_net > 0 and dii_net > 0:

            fii_dii_bias = "BOTH_BUYING"

        elif fii_net < 0 and dii_net < 0:

            fii_dii_bias = "BOTH_SELLING"

        else:

            fii_dii_bias = "MIXED"

        angel = data.get("angel_one", {}) or {}

        pcr_data = angel.get("pcr", {}) or {}

        selected_pcr = None
        selected_pcr_symbol = None

        if symbol == "NIFTY":

            for pcr_symbol, value in pcr_data.items():

                if re.match(
                    r"^NIFTY\d.*FUT$",
                    str(pcr_symbol).upper(),
                ):

                    parsed_value = safe_number(value)

                    if parsed_value is not None:

                        selected_pcr = parsed_value
                        selected_pcr_symbol = pcr_symbol

                        break

        oi_data = angel.get("oi_buildup", {}) or {}

        oi_summary = {}

        categories = [
            "LONG_BUILT_UP",
            "SHORT_BUILT_UP",
            "SHORT_COVERING",
            "LONG_UNWINDING",
        ]

        for category in categories:

            records = oi_data.get(category, []) or []

            symbols = [
                item.get("symbol")
                for item in records
                if isinstance(item, dict) and item.get("symbol")
            ]

            oi_summary[category] = {
                "count": len(symbols),
                "symbols": symbols,
            }

        participant_data = data.get(
            "participant_positions",
            {},
        )

        participant_summary = build_participant_summary(
            participant_data
        )

        pcr_available = selected_pcr is not None

        oi_available = any(
            oi_summary[category]["count"] > 0
            for category in categories
        )

        return {
            "fii_dii": {
                "status": (
                    "CONNECTED"
                    if fii_net is not None and dii_net is not None
                    else "UNAVAILABLE"
                ),

                "date": report_date,

                "fii_net_cr": fii_net,

                "dii_net_cr": dii_net,

                "bias": fii_dii_bias,
            },

            "pcr": {
                "status": (
                    "CONNECTED"
                    if pcr_available
                    else "NOT_APPLICABLE"
                    if symbol == "SENSEX"
                    else "UNAVAILABLE"
                ),

                "symbol": selected_pcr_symbol,

                "value": selected_pcr,
            },

            "oi_buildup": {
                "status": (
                    "CONNECTED"
                    if oi_available
                    else "UNAVAILABLE"
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


# =========================================================
# SINGLE TIMEFRAME ANALYSIS API
# =========================================================

@app.get("/api/market/analysis")
def market_analysis(
    symbol: str = "NIFTY",
    timeframe: str = "15m",
):

    symbol = normalize_symbol(symbol)

    timeframe = validate_timeframe(timeframe)

    try:

        result = analyze_timeframe(
            symbol,
            timeframe,
        )

        return {
            "symbol": symbol,

            "timeframe": timeframe,

            "timeframe_label": TIMEFRAME_LABELS[timeframe],

            **result,

            "updated_at": now_ist().isoformat(),
        }

    except Exception as error:

        raise HTTPException(
            status_code=502,
            detail=f"Market data unavailable: {str(error)}",
        )


# =========================================================
# SIGNAL VALIDATION
# =========================================================

def validate_trade_levels(signal_name, signal_data):

    if not isinstance(signal_data, dict):
        return None

    entry = safe_number(signal_data.get("entry"))

    stop_loss = safe_number(
        signal_data.get("stop_loss")
    )

    target = safe_number(
        signal_data.get("target")
    )

    if entry is None or stop_loss is None or target is None:
        return None

    if entry <= 0 or stop_loss <= 0 or target <= 0:
        return None

    if signal_name == "CALL BIAS":

        if not (stop_loss < entry < target):
            return None

    elif signal_name == "PUT BIAS":

        if not (target < entry < stop_loss):
            return None

    else:

        return None

    return {
        "entry": entry,
        "stop_loss": stop_loss,
        "target": target,
        "risk_reward": signal_data.get("risk_reward"),
    }


# =========================================================
# COMBINED MARKET ANALYSIS
# =========================================================

@app.get("/api/market/combined")
def combined_market_analysis(symbol: str = "NIFTY"):

    symbol = normalize_symbol(symbol)

    try:

        # Three timeframe analysis

        daily = analyze_timeframe(
            symbol,
            "1d",
        )

        hourly = analyze_timeframe(
            symbol,
            "1h",
        )

        fifteen = analyze_timeframe(
            symbol,
            "15m",
        )

        # Institutional supporting data

        institutional = get_institutional_summary(
            symbol
        )

        daily_direction = daily["direction"]

        hourly_direction = hourly["direction"]

        fifteen_direction = fifteen["direction"]

        daily_signal = daily["signal"].get(
            "signal",
            "WAIT",
        )

        hourly_signal = hourly["signal"].get(
            "signal",
            "WAIT",
        )

        fifteen_signal = fifteen["signal"].get(
            "signal",
            "WAIT",
        )

        # Default is always WAIT

        final_signal = "WAIT"

        reason = (
            "Daily, 1-hour aur 15-minute confirmation "
            "abhi ek direction mein nahi hain."
        )

        # CALL confirmation

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

        # PUT confirmation

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

        # Validate entry and risk levels

        levels = None

        if final_signal in ["CALL BIAS", "PUT BIAS"]:

            levels = validate_trade_levels(
                final_signal,
                fifteen["signal"],
            )

            if levels is None:

                final_signal = "WAIT"

                reason = (
                    "Trade levels invalid or incomplete. "
                    "Fresh confirmation ka intezar karein."
                )

        entry = None
        stop_loss = None
        target = None
        risk_reward = None

        exit_condition = (
            "WAIT: clear confirmation ka intezar karein."
        )

        if final_signal in ["CALL BIAS", "PUT BIAS"]:

            entry = levels["entry"]

            stop_loss = levels["stop_loss"]

            target = levels["target"]

            risk_reward = levels["risk_reward"]

            if final_signal == "CALL BIAS":

                exit_condition = (
                    "Stop-loss hit hone par exit karein. "
                    "Target par profit book karein. "
                    "15-minute candle EMA20 ke neeche close "
                    "ho to position dobara evaluate karein."
                )

            else:

                exit_condition = (
                    "Stop-loss hit hone par exit karein. "
                    "Target par profit book karein. "
                    "15-minute candle EMA20 ke upar close "
                    "ho to position dobara evaluate karein."
                )

        # Final direction

        if final_signal == "CALL BIAS":

            final_direction = "BULLISH"

        elif final_signal == "PUT BIAS":

            final_direction = "BEARISH"

        else:

            final_direction = "NEUTRAL"

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

            "direction": final_direction,

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
                "positions. Exit conditions require manual "
                "monitoring. This API does not place or manage "
                "broker orders."
            ),

            "updated_at": now_ist().isoformat(),
        }

    except Exception as error:

        raise HTTPException(
            status_code=502,
            detail=(
                "Combined analysis unavailable: "
                + str(error)
            ),
        )


# =========================================================
# INSTITUTIONAL API
# =========================================================

@app.get("/api/market/institutional")
def institutional_data():

    try:

        return get_institutional_data()

    except Exception as error:

        raise HTTPException(
            status_code=502,
            detail=(
                "Institutional data unavailable: "
                + str(error)
            ),
        )
