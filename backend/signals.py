
def generate_signal(price, ema_20, ema_50, rsi):
    if any(value is None for value in (price, ema_20, ema_50, rsi)):
        return {
            "signal": "WAIT",
            "reason": "Market data incomplete"
        }

    if price <= 0:
        return {"signal": "WAIT", "reason": "Invalid price"}

    # Bullish confirmation
    if ema_20 > ema_50 and price > ema_20 and 50 < rsi < 70:
        entry = round(price, 2)
        return {
            "signal": "CALL BIAS",
            "entry": entry,
            "stop_loss": round(price * 0.99, 2),
            "target": round(price * 1.02, 2),
            "reason": "EMA trend and RSI bullish confirmation",
            "risk_note": "Index levels only; verify before trading"
        }

    # Bearish confirmation
    if ema_20 < ema_50 and price < ema_20 and 30 < rsi < 50:
        entry = round(price, 2)
        return {
            "signal": "PUT BIAS",
            "entry": entry,
            "stop_loss": round(price * 1.01, 2),
            "target": round(price * 0.98, 2),
            "reason": "EMA trend and RSI bearish confirmation",
            "risk_note": "Index levels only; verify before trading"
        }

    return {
        "signal": "WAIT",
        "reason": "No clear trend confirmation"
    }
