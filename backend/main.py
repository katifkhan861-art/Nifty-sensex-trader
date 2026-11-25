
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

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
    return {"status": "ok"}


@app.get("/api/status")
def status():
    return {
        "mode": "DEMO",
        "message": "Live data is not connected yet.",
        "nifty": "DEMO",
        "sensex": "DEMO",
        "live_data": False
    }


@app.get("/api/market/overview")
def market_overview():
    return {
        "markets": {
            "NIFTY": {"price": None, "mode": "DEMO"},
            "SENSEX": {"price": None, "mode": "DEMO"}
        }
    }


@app.get("/api/market/analysis")
def market_analysis(symbol: str = "NIFTY", timeframe: str = "15m"):
    labels = {
        "15m": "15 Minute",
        "1h": "1 Hour",
        "1d": "Daily"
    }

    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "timeframe_label": labels.get(timeframe, timeframe),
        "price": None,
        "indicators": {
            "ema_20": None,
            "ema_50": None,
            "rsi": None
        },
        "signal": {
            "signal": "WAIT",
            "direction": "NEUTRAL",
            "entry": None,
            "stop_loss": None,
            "target": None,
            "reason": "Live market data is not connected.",
            "note": "Demo mode only. No trading signal."
        },
        "updated_at": None
    }
