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


# Caché en memoria del universo
_SYMBOL_NAME_MAP = None


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


def _build_symbol_name_map():
    """Construye {symbol: name} desde el universo."""
    global _SYMBOL_NAME_MAP
    if _SYMBOL_NAME_MAP is not None:
        return _SYMBOL_NAME_MAP

    universe = _load_universe()
    mapping = {}
    for row in universe:
        symbol = (row.get("symbol") or "").upper().strip()
        name = (row.get("name") or "").strip()
        if symbol and name:
            # Limpiar el nombre (quitar "Common Stock", "Inc.", etc.)
            clean = name
            for suffix in [
                " - Common Stock", " Common Stock", " - Class A",
                " - Class B", " - Class C", " - Class D",
                " - American Depositary Shares", " - Ordinary Shares",
                " Inc.", " Inc", " Corporation", " Corp.", " Corp",
                " Company", " Co.", " Co", " Ltd.", " Ltd",
                " PLC", " plc", " Limited", " -",
            ]:
                clean = clean.replace(suffix, "")
            mapping[symbol] = clean.strip()
    _SYMBOL_NAME_MAP = mapping
    return mapping


def get_symbol_name(symbol: str) -> str:
    """Devuelve el nombre de un ticker (o '' si no se encuentra)."""
    mapping = _build_symbol_name_map()
    return mapping.get(symbol.upper(), "")


def compute_strength(score: int) -> str:
    """Convierte un score a texto legible."""
    if score >= 80:
        return "MUY FUERTE"
    if score >= 75:
        return "FUERTE"
    if score >= 65:
        return "MEDIA"
    return "DÉBIL"


def translate_alignment(alignment: str) -> str:
    """Traduce el alignment tecnico a español."""
    map_align = {
        "aligned_bullish": "Alineación alcista",
        "aligned_bearish": "Alineación bajista",
        "daily_h1_bullish": "Diario + 1h alcista",
        "daily_h1_bearish": "Diario + 1h bajista",
        "daily_m5_bullish": "Diario + 5m alcista",
        "daily_m5_bearish": "Diario + 5m bajista",
        "opposed_daily_bullish": "Conflicto (diario alcista)",
        "opposed_daily_bearish": "Conflicto (diario bajista)",
        "mixed": "Señal mixta",
        "none": "Sin alineación",
    }
    return map_align.get(alignment, alignment or "")


def translate_regime(regime: str) -> str:
    """Traduce el régimen de mercado."""
    map_reg = {
        "trending": "En tendencia",
        "ranging": "En rango",
        "volatile": "Volátil",
        "compressed": "Comprimido",
        "neutral": "Neutro",
    }
    return map_reg.get(regime, regime or "")


def translate_confluence(conf: str) -> str:
    """Traduce el nivel de confluencia."""
    map_conf = {
        "high": "Alta",
        "medium": "Media",
        "low": "Baja",
        "very_low": "Muy baja",
    }
    return map_conf.get(conf, conf or "")


def enrich_ticker(item: dict) -> dict:
    """Añade campos enriquecidos a un ticker."""
    if not item:
        return item

    symbol = item.get("ticker", "")
    score = item.get("score", 0)

    # Nombre
    if not item.get("name"):
        item["name"] = get_symbol_name(symbol)

    # Strength
    if not item.get("strength"):
        item["strength"] = compute_strength(score)

    # Traducciones
    if item.get("alignment") and not item.get("alignment_es"):
        item["alignment_es"] = translate_alignment(item["alignment"])

    if item.get("regime_daily") and not item.get("regime_es"):
        item["regime_es"] = translate_regime(item["regime_daily"])

    if item.get("confluence") and not item.get("confluence_es"):
        item["confluence_es"] = translate_confluence(item["confluence"])

    # Traducciones por temporalidad
    tfs = item.get("timeframes", {})
    for tf_name, tf_data in tfs.items():
        if not isinstance(tf_data, dict):
            continue
        if tf_data.get("regime") and not tf_data.get("regime_es"):
            tf_data["regime_es"] = translate_regime(tf_data["regime"])
        if tf_data.get("structure_bias") and not tf_data.get("structure_bias_es"):
            bias_map = {
                "bullish": "Alcista",
                "bearish": "Bajista",
                "neutral": "Neutro",
                "bullish_weak": "Alcista débil",
                "bearish_weak": "Bajista débil",
            }
            tf_data["structure_bias_es"] = bias_map.get(
                tf_data["structure_bias"], tf_data["structure_bias"]
            )

    return item


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
    """Devuelve el Top 15 LONG + Top 15 SHORT enriquecidos."""
    data = _load_destacados()

    for item in data.get("long", []):
        enrich_ticker(item)
    for item in data.get("short", []):
        enrich_ticker(item)

    return data


@app.get("/destacados/long")
def get_destacados_long():
    """Solo el Top LONG enriquecido."""
    data = _load_destacados()
    for item in data.get("long", []):
        enrich_ticker(item)
    return {
        "timestamp": data.get("timestamp"),
        "count": len(data.get("long", [])),
        "long": data.get("long", []),
        "disclaimer": LEGAL_DISCLAIMER,
    }


@app.get("/destacados/short")
def get_destacados_short():
    """Solo el Top SHORT enriquecido."""
    data = _load_destacados()
    for item in data.get("short", []):
        enrich_ticker(item)
    return {
        "timestamp": data.get("timestamp"),
        "count": len(data.get("short", [])),
        "short": data.get("short", []),
        "disclaimer": LEGAL_DISCLAIMER,
    }


@app.get("/ticker/{symbol}")
def get_ticker(symbol: str):
    """Analisis completo de un ticker enriquecido."""
    symbol = symbol.upper()

    # 1. Buscar en destacados
    item = _find_in_destacados(symbol)
    if item:
        return enrich_ticker(item)

    # 2. Análisis en vivo
    try:
        from analysis.technicals import analyze_ticker
        result = analyze_ticker(symbol)
        if "error" in result:
            raise HTTPException(
                status_code=404,
                detail=f"'{symbol}' no tiene datos suficientes.",
            )
        return enrich_ticker(result)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=404,
            detail=f"'{symbol}' no se pudo analizar.",
        )


@app.get("/search/{query}")
def search(query: str):
    """Busca tickers por nombre o symbol."""
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