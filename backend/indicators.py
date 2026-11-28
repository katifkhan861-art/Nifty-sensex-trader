
import pandas as pd
import numpy as np


def calculate_indicators(candles):
    if not candles or len(candles) < 50:
        return {"error": "कम से कम 50 candles जरूरी हैं"}

    try:
        df = pd.DataFrame(candles)

        required = ["open", "high", "low", "close", "volume"]
        if not all(col in df.columns for col in required):
            return {"error": "Candle data incomplete"}

        for col in required:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["high", "low", "close"])
        df = df.sort_values(
            "timestamp"
        ) if "timestamp" in df.columns else df

        if len(df) < 50:
            return {"error": "Valid candles 50 से कम हैं"}

        close = df["close"]
        high = df["high"]
        low = df["low"]

        if (close <= 0).any():
            return {"error": "Invalid candle price"}

        # EMA
        df["ema_20"] = close.ewm(
            span=20, adjust=False
        ).mean()

        df["ema_50"] = close.ewm(
            span=50, adjust=False
        ).mean()

        # RSI 14
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.ewm(
            alpha=1/14, adjust=False
        ).mean()

        avg_loss = loss.ewm(
            alpha=1/14, adjust=False
        ).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))

        df.loc[
            (avg_loss == 0) & (avg_gain > 0), "rsi"
        ] = 100

        df.loc[
            (avg_loss == 0) & (avg_gain == 0), "rsi"
        ] = 50

        # MACD
        ema_12 = close.ewm(
            span=12, adjust=False
        ).mean()

        ema_26 = close.ewm(
            span=26, adjust=False
        ).mean()

        df["macd"] = ema_12 - ema_26

        df["macd_signal"] = df["macd"].ewm(
            span=9, adjust=False
        ).mean()

        # ATR 14
        previous_close = close.shift(1)

        tr = pd.concat([
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs()
        ], axis=1).max(axis=1)

        df["atr"] = tr.ewm(
            alpha=1/14, adjust=False
        ).mean()

        # ADX 14
        up_move = high.diff()
        down_move = -low.diff()

        plus_dm = up_move.where(
            (up_move > down_move) & (up_move > 0), 0
        )

        minus_dm = down_move.where(
            (down_move > up_move) & (down_move > 0), 0
        )

        atr_safe = df["atr"].replace(0, np.nan)

        plus_di = 100 * (
            plus_dm.ewm(alpha=1/14, adjust=False).mean()
            / atr_safe
        )

        minus_di = 100 * (
            minus_dm.ewm(alpha=1/14, adjust=False).mean()
            / atr_safe
        )

        di_sum = (plus_di + minus_di).replace(0, np.nan)

        dx = 100 * (plus_di - minus_di).abs() / di_sum

        df["adx"] = dx.ewm(
            alpha=1/14, adjust=False
        ).mean()

        last = df.iloc[-1]

        result = {
            "close": float(last["close"]),
            "ema_20": float(last["ema_20"]),
            "ema_50": float(last["ema_50"]),
            "rsi": float(last["rsi"]),
            "macd": float(last["macd"]),
            "macd_signal": float(last["macd_signal"]),
            "atr": float(last["atr"]),
            "adx": float(last["adx"])
        }

        if not all(np.isfinite(v) for v in result.values()):
            return {"error": "Indicator calculation incomplete"}

        return result

    except Exception as e:
        return {"error": f"Indicator calculation failed: {str(e)}"}
