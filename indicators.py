import pandas as pd

def calculate_indicators(candles):
    if not candles or len(candles) < 50:
        return {"error": "कम से कम 50 candles जरूरी हैं"}
    df = pd.DataFrame(candles)
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    if len(close) < 50:
        return {"error": "पर्याप्त valid candles नहीं हैं"}
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    last_rsi = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else (100.0 if float(avg_loss.iloc[-1] or 0) == 0 else 50.0)
    return {"close": round(float(close.iloc[-1]), 2), "ema_20": round(float(ema20.iloc[-1]), 2), "ema_50": round(float(ema50.iloc[-1]), 2), "rsi": round(last_rsi, 2), "candle_count": int(len(close))}
