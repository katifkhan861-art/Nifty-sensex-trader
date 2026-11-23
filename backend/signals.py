def generate_signal(price, ema_20, ema_50, rsi):
    if price is None or ema_20 is None or ema_50 is None or rsi is None:
        return {"signal": "WAIT", "reason": "Data incomplete"}

    if ema_20 > ema_50 and price > ema_20 and 50 < rsi < 70:
        return {
            "signal": "CALL BIAS",
            "entry": price,
            "stop_loss": round(price * 0.99, 2),
            "target": round(price * 1.02, 2),
            "reason": "Bullish trend confirmation"
        }

    if ema_20 < ema_50 and price < ema_20 and 30 < rsi < 50:
        return {
            "signal": "PUT BIAS",
            "entry": price,
            "stop_loss": round(price * 1.01, 2),
            "target": round(price * 0.98, 2),
            "reason": "Bearish trend confirmation"
        }

    return {
        "signal": "WAIT",
        "reason": "No clear trend confirmation"
    }
