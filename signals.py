def generate_signal(price, ema_20, ema_50, rsi):
    if any(v is None for v in (price, ema_20, ema_50, rsi)):
        return {"signal": "WAIT", "reason": "Data incomplete"}
    price, ema_20, ema_50, rsi = map(float, (price, ema_20, ema_50, rsi))
    if ema_20 > ema_50 and price > ema_20 and 50 < rsi < 70:
        stop = min(ema_20, price * 0.99)
        return {"signal": "CALL BIAS", "direction": "BULLISH", "entry": round(price, 2), "stop_loss": round(stop, 2), "target": round(price + 2 * (price - stop), 2), "risk_reward": "1:2 (index reference)", "reason": "Price EMA20 से ऊपर, EMA20 EMA50 से ऊपर और RSI bullish zone में है.", "note": "यह index-level bias है, option premium का trade setup नहीं।"}
    if ema_20 < ema_50 and price < ema_20 and 30 < rsi < 50:
        stop = max(ema_20, price * 1.01)
        return {"signal": "PUT BIAS", "direction": "BEARISH", "entry": round(price, 2), "stop_loss": round(stop, 2), "target": round(price - 2 * (stop - price), 2), "risk_reward": "1:2 (index reference)", "reason": "Price EMA20 से नीचे, EMA20 EMA50 से नीचे और RSI bearish zone में है.", "note": "यह index-level bias है, option premium का trade setup नहीं।"}
    return {"signal": "WAIT", "direction": "SIDEWAYS / MIXED", "entry": None, "stop_loss": None, "target": None, "reason": "Trend confirmation नहीं है; trade से बचें और अगले candle का इंतजार करें।"}
