
def generate_signal(price, ema_20, ema_50, rsi):
    if any(value is None for value in (price, ema_20, ema_50, rsi)):
        return {
            "signal": "WAIT",
            "reason": "Market data incomplete"
        }

    if price <= 0:
        return {
            "signal": "WAIT",
            "reason": "Invalid price"
        }

    # Bullish confirmation
    if ema_20 > ema_50 and price > ema_20 and 50 < rsi <= 75:
        entry = round(price, 2)

        if rsi > 70:
            reason = "Strong bullish trend, but RSI is elevated"
            risk_note = "Momentum strong; avoid chasing. Index levels only."
        else:
            reason = "EMA trend and RSI bullish confirmation"
            risk_note = "Index levels only; verify before trading"

        return {
            "signal": "CALL BIAS",
            "entry": entry,
            "stop_loss": round(price * 0.99, 2),
            "target": round(price * 1.02, 2),
            "reason": reason,
            "risk_note": risk_note
        }

    # Bearish confirmation
    if ema_20 < ema_50 and price < ema_20 and 25 <= rsi < 50:
        entry = round(price, 2)

        if rsi < 30:
            reason = "Strong bearish trend, but RSI is very low"
            risk_note = "Downward momentum strong; avoid chasing. Index levels only."
        else:
            reason = "EMA trend and RSI bearish confirmation"
            risk_note = "Index levels only; verify before trading"

        return {
            "signal": "PUT BIAS",
            "entry": entry,
            "stop_loss": round(price * 1.01, 2),
            "target": round(price * 0.98, 2),
            "reason": reason,
            "risk_note": risk_note
        }

    return {
        "signal": "WAIT",
        "reason": "No clear trend confirmation"
    }
