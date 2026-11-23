import pandas as pd


def calculate_indicators(candles):
    if not candles or len(candles) < 50:
        return {"error": "कम से कम 50 candles जरूरी हैं"}

    df = pd.DataFrame(candles)

    close = pd.to_numeric(df["close"])

    df["ema_20"] = close.ewm(span=20, adjust=False).mean()
    df["ema_50"] = close.ewm(span=50, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, float("nan"))
    df["rsi"] = 100 - (100 / (1 + rs))

    last = df.iloc[-1]

    return {
        "close": float(last["close"]),
        "ema_20": float(last["ema_20"]),
        "ema_50": float(last["ema_50"]),
        "rsi": float(last["rsi"])
    }
