"""
API REST de ELTOPO.
Sirve los datos del scanner a la web y a la app Android.
"""
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import CACHE_DIR, API_TITLE, API_VERSION, LEGAL_DISCLAIMER

app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    description=LEGAL_DISCLAIMER,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DESTACADOS_JSON = CACHE_DIR / "destacados.json"


@app.get("/")
def root():
    return {
        "app": API_TITLE,
        "version": API_VERSION,
        "disclaimer": LEGAL_DISCLAIMER,
        "endpoints": [
            "/destacados",
            "/destacados/long",
            "/destacados/short",
            "/ticker/{symbol}",
            "/health",
        ],
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/destacados")
def get_destacados():
    if not DESTACADOS_JSON.exists():
        raise HTTPException(status_code=404, detail="Sin datos. Ejecuta el scanner.")
    with open(DESTACADOS_JSON, encoding="utf-8") as f:
        data = json.load(f)
    return data


@app.get("/destacados/long")
def get_destacados_long():
    if not DESTACADOS_JSON.exists():
        raise HTTPException(status_code=404, detail="Sin datos")
    with open(DESTACADOS_JSON, encoding="utf-8") as f:
        data = json.load(f)
    return {
        "timestamp": data.get("timestamp"),
        "count": len(data.get("long", [])),
        "long": data.get("long", []),
        "disclaimer": LEGAL_DISCLAIMER,
    }


@app.get("/destacados/short")
def get_destacados_short():
    if not DESTACADOS_JSON.exists():
        raise HTTPException(status_code=404, detail="Sin datos")
    with open(DESTACADOS_JSON, encoding="utf-8") as f:
        data = json.load(f)
    return {
        "timestamp": data.get("timestamp"),
        "count": len(data.get("short", [])),
        "short": data.get("short", []),
        "disclaimer": LEGAL_DISCLAIMER,
    }


@app.get("/ticker/{symbol}")
def get_ticker(symbol: str):
    from analysis.technicals import analyze_ticker
    symbol = symbol.upper()
    try:
        return analyze_ticker(symbol)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))