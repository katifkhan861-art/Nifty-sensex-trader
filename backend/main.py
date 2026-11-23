from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="NIFTY SENSEX Trading API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://katifkhan861-art.github.io"
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "NIFTY SENSEX API is running"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/status")
def status():
    return {
        "nifty": "DEMO",
        "sensex": "DEMO",
        "live_data": False
    }
