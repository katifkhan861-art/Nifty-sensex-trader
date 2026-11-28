
import math


def generate_signal(
    price,
    ema_20,
    ema_50,
    rsi,
    macd,
    macd_signal,
    atr,
    adx,
):
    values = (
        price, ema_20, ema_50, rsi,
        macd, macd_signal, atr, adx
    )

    try:
        values = [float(v) for v in values]
    except (TypeError, ValueError):
        return {
            "signal": "WAIT",
            "reason": "Market indicators incomplete"
        }

    if not all(math.isfinite(v) for v in values):
        return {
            "signal": "WAIT",
            "reason": "Invalid indicator values"
        }

    if price <= 0 or atr <= 0:
        return {
            "signal": "WAIT",
            "reason": "Invalid price or ATR"
        }

    if adx < 20:
        return {
            "signal": "WAIT",
            "reason": "Trend strength is weak (ADX below 20)"
        }

    risk = 1.5 * atr
    reward = 2.0 * risk

    # Bullish confirmation
    if (
        ema_20 > ema_50
        and price > ema_20
        and 50 < rsi < 70
        and macd > macd_signal
    ):
        return {
            "signal": "CALL BIAS",
            "entry": round(price, 2),
            "stop_loss": round(price - risk, 2),
            "target": round(price + reward, 2),
            "risk_reward": "1:2",
            "reason": "EMA, RSI, MACD and ADX bullish confirmation",
            "risk_note": "Index levels only; not option premium."
        }

    # Bearish confirmation
    if (
        ema_20 < ema_50
        and price < ema_20
        and 30 < rsi < 50
        and macd < macd_signal
    ):
        return {
            "signal": "PUT BIAS",
            "entry": round(price, 2),
            "stop_loss": round(price + risk, 2),
            "target": round(price - reward, 2),
            "risk_reward": "1:2",
            "reason": "EMA, RSI, MACD and ADX bearish confirmation",
            "risk_note": "Index levels only; not option premium."
        }

    return {
        "signal": "WAIT",
        "reason": "All trend confirmations are not aligned"
    }
