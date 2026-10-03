"""
ELTOPO - Sistema de analisis de datos para day trading.
Configuracion central del proyecto.

IMPORTANTE: Este sistema NO emite recomendaciones de compra/venta.
Solo analiza y presenta datos.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


# ============================================================
# RUTAS DEL PROYECTO
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "cache"
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data_store"

CACHE_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)


# ============================================================
# ALPACA
# ============================================================
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
ALPACA_DATA_URL = os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets")
ALPACA_FEED = os.getenv("ALPACA_FEED", "iex")


# ============================================================
# UNIVERSO
# ============================================================
EXCHANGES = ["NYSE", "NASDAQ", "AMEX"]

MIN_PRICE = 1.0
MIN_AVG_VOLUME = 500_000
MIN_MARKET_CAP = 300_000_000

TARGET_UNIVERSE_SIZE = 3500


# ============================================================
# TEMPORALIDADES
# ============================================================
TIMEFRAMES = {
    "daily": "1Day",
    "h1": "1Hour",
    "m5": "5Min",
    "m15": "15Min",
}

PERIODS_DAYS = {
    "daily": 365,
    "h1": 60,
    "m15": 30,
    "m5": 30,
}


# ============================================================
# ESCALA DE COLORES
# ============================================================
COLOR_GREEN_THRESHOLD = 75
COLOR_YELLOW_THRESHOLD = 60

COLOR_GREEN = "green"
COLOR_YELLOW = "yellow"
COLOR_RED = "red"
COLOR_NEUTRAL = "neutral"


# ============================================================
# PESOS DEL SCORE TECNICO INTERNO
# ============================================================
TECHNICAL_WEIGHTS = {
    "sr": 0.30,
    "pattern": 0.25,
    "candle": 0.15,
    "trend": 0.15,
    "momentum": 0.10,
    "volume": 0.05,
}


# ============================================================
# PESOS MULTITEMPORALES
# ============================================================
TIMEFRAME_WEIGHTS = {
    "daily": 0.50,
    "h1": 0.32,
    "m5": 0.18,
}


# ============================================================
# PARAMETROS TECNICOS
# ============================================================
SWING_LOOKBACK = 5
SR_TOLERANCE_PCT = 0.5

EMA_PERIODS = [8, 20, 200]
RSI_PERIOD = 14
ADX_PERIOD = 14
STOCH_PERIOD = 14
STOCH_SMOOTH_K = 3
STOCH_SMOOTH_D = 3
ATR_PERIOD = 14
VOLUME_MA_PERIOD = 20

VWAP_ENABLED = True


# ============================================================
# EMBUDO DE FILTRADO
# ============================================================
PREFILTER_MIN_REL_VOLUME = 1.2
PREFILTER_MIN_ATR_PCT = 1.5
PREFILTER_MAX_CANDIDATES = 500

DEEP_ANALYSIS_MAX = 50


# ============================================================
# DESTACADOS / TOP
# ============================================================
TOP_N = 15                     # por lado (LONG y SHORT)
TOP_N_VISIBLE_DEFAULT = 5      # visibles por defecto en la app
MIN_SCORE_FOR_TOP = 60


# ============================================================
# PARAMETROS DE TRADING (validados con backtest)
# ============================================================
# Time stops diferenciados (validados con backtest)
LONG_HOLD_DAYS = 1             # LONG: cerrar al final del dia
SHORT_HOLD_DAYS = 10           # SHORT: hasta 10 dias

# Gestion de riesgo
STOP_ATR_MULT = 1.5            # Stop loss: 1.5 x ATR
TARGET_ATR_MULT = 3.0          # Take profit: 3.0 x ATR

# Resultados del backtest (referencia)
BACKTEST_WIN_RATE = 91.3       # %
BACKTEST_EXPECTANCY = 4.40     # % por trade
BACKTEST_TOTAL_RETURN = 101.3  # % en ~4 meses
BACKTEST_TRADES = 23           # numero de trades del backtest


# ============================================================
# SCANNER
# ============================================================
SCAN_INTERVAL_MINUTES = 5
MAX_CONCURRENT_DOWNLOADS = 20
DOWNLOAD_BATCH_SIZE = 100
DOWNLOAD_RETRIES = 3
DOWNLOAD_TIMEOUT = 30

ALPACA_RATE_LIMIT_PER_MIN = 180
ALPACA_MAX_WORKERS = 8


# ============================================================
# API REST
# ============================================================
API_HOST = "0.0.0.0"
API_PORT = 8000
API_TITLE = "ELTOPO API"
API_VERSION = "1.0.0"


# ============================================================
# NOTA LEGAL
# ============================================================
LEGAL_DISCLAIMER = (
    "Esta aplicacion ofrece analisis de datos, "
    "no asesoramiento financiero."
)


# ============================================================
# LOGGING
# ============================================================
LOG_LEVEL = "INFO"
LOG_FILE = LOGS_DIR / "eltopo.log"


if __name__ == "__main__":
    print("=" * 60)
    print("Configuracion ELTOPO")
    print("=" * 60)
    print(f"BASE_DIR: {BASE_DIR}")
    print(f"CACHE_DIR: {CACHE_DIR}")
    print()
    print("ALPACA:")
    print(f"  API Key:  {'OK' if ALPACA_API_KEY else 'FALTA'}")
    print(f"  Secret:   {'OK' if ALPACA_SECRET_KEY else 'FALTA'}")
    print(f"  Feed:     {ALPACA_FEED}")
    print()
    print("SCORING:")
    print(f"  Verde:    >= {COLOR_GREEN_THRESHOLD}")
    print(f"  Amarillo: >= {COLOR_YELLOW_THRESHOLD}")
    print(f"  Pesos multitemporales: {TIMEFRAME_WEIGHTS}")
    print()
    print("DESTACADOS:")
    print(f"  Top por lado:          {TOP_N}")
    print(f"  Visible por defecto:   {TOP_N_VISIBLE_DEFAULT}")
    print(f"  Score minimo:          {MIN_SCORE_FOR_TOP}")
    print()
    print("TRADING (backtest):")
    print(f"  LONG_HOLD_DAYS:        {LONG_HOLD_DAYS}")
    print(f"  SHORT_HOLD_DAYS:       {SHORT_HOLD_DAYS}")
    print(f"  Stop:                  {STOP_ATR_MULT} x ATR")
    print(f"  Target:                {TARGET_ATR_MULT} x ATR")
    print(f"  Win rate historico:    {BACKTEST_WIN_RATE}%")
    print(f"  Expectancy:            +{BACKTEST_EXPECTANCY}% por trade")
    print(f"  Total return backtest: +{BACKTEST_TOTAL_RETURN}%")
    print("=" * 60)