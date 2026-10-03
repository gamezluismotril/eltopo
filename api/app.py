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


# ============================================================
# RUTAS DE DATOS
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent
DESTACADOS_JSON = BASE_DIR / "public_data" / "destacados.json"
CACHE_DESTACADOS_JSON = CACHE_DIR / "destacados.json"
UNIVERSE_CSV = CACHE_DIR / "universe_filtered.csv"
PUBLIC_UNIVERSE_CSV = BASE_DIR / "public_data" / "universe.csv"


def _load_destacados():
    """Carga el JSON desde public_data (produccion) o cache (local)."""
    json_path = DESTACADOS_JSON if DESTACADOS_JSON.exists() else CACHE_DESTACADOS_JSON
    if not json_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Sin datos. Ejecuta el scanner.",
        )
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


def _load_universe():
    """Carga el universo filtrado (ticker -> nombre)."""
    csv_path = PUBLIC_UNIVERSE_CSV if PUBLIC_UNIVERSE_CSV.exists() else UNIVERSE_CSV
    if not csv_path.exists():
        return []
    try:
        import csv
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [row for row in reader]
    except Exception:
        return []


def _find_in_destacados(symbol: str):
    """Busca el ticker en destacados. Devuelve el item o None."""
    try:
        data = _load_destacados()
        for item in data.get("long", []) + data.get("short", []):
            if item.get("ticker") == symbol:
                return item
    except Exception:
        pass
    return None


# ============================================================
# ENDPOINTS
# ============================================================
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
            "/search/{query}",
            "/health",
        ],
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/destacados")
def get_destacados():
    """Devuelve el Top 15 LONG + Top 15 SHORT."""
    return _load_destacados()


@app.get("/destacados/long")
def get_destacados_long():
    """Solo el Top LONG."""
    data = _load_destacados()
    return {
        "timestamp": data.get("timestamp"),
        "count": len(data.get("long", [])),
        "long": data.get("long", []),
        "disclaimer": LEGAL_DISCLAIMER,
    }


@app.get("/destacados/short")
def get_destacados_short():
    """Solo el Top SHORT."""
    data = _load_destacados()
    return {
        "timestamp": data.get("timestamp"),
        "count": len(data.get("short", [])),
        "short": data.get("short", []),
        "disclaimer": LEGAL_DISCLAIMER,
    }


@app.get("/ticker/{symbol}")
def get_ticker(symbol: str):
    """Analisis completo de un ticker.
    1. Busca en destacados.json (rapido)
    2. Si no esta, intenta analisis en vivo
    """
    symbol = symbol.upper()

    # 1. Buscar en destacados
    item = _find_in_destacados(symbol)
    if item:
        return item

    # 2. Intento de analisis en vivo (puede tardar o fallar)
    try:
        from analysis.technicals import analyze_ticker
        result = analyze_ticker(symbol)
        if "error" in result:
            raise HTTPException(
                status_code=404,
                detail=f"'{symbol}' no tiene datos suficientes. Prueba con otro ticker del Top 15.",
            )
        return result
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=404,
            detail=f"'{symbol}' no se pudo analizar. Prueba con otro ticker del Top 15.",
        )


@app.get("/search/{query}")
def search(query: str):
    """Busca tickers por nombre o symbol.
    Devuelve lista de coincidencias.
    """
    query = query.upper().strip()
    if len(query) < 2:
        return {"query": query, "results": []}

    universe = _load_universe()
    results = []

    for row in universe:
        symbol = (row.get("symbol") or "").upper()
        name = (row.get("name") or "").upper()

        if query in symbol or query in name:
            results.append({
                "symbol": symbol,
                "name": row.get("name") or "",
                "exchange": row.get("exchange") or "",
            })
            if len(results) >= 20:
                break

    return {
        "query": query,
        "count": len(results),
        "results": results,
    }