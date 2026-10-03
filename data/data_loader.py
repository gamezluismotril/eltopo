"""
Descarga de velas (OHLCV) por ticker y temporalidad usando Alpaca.
Cachea en CSV para no repetir descargas.
"""
import time
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from config import (
    CACHE_DIR, PERIODS_DAYS, ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_FEED,
)
from utils.logger import get_logger

log = get_logger(__name__)

OHLCV_CACHE = CACHE_DIR / "ohlcv"
OHLCV_CACHE.mkdir(exist_ok=True)


# Cliente global (singleton)
_client = None


def _get_client() -> StockHistoricalDataClient:
    global _client
    if _client is None:
        if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
            raise RuntimeError("Faltan claves de Alpaca en .env")
        _client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
    return _client


# ============================================================
# MAPEO DE TEMPORALIDADES A ALPACA
# ============================================================
TIMEFRAME_MAP = {
    "daily": TimeFrame(1, TimeFrameUnit.Day),
    "h1": TimeFrame(1, TimeFrameUnit.Hour),
    "m15": TimeFrame(15, TimeFrameUnit.Minute),
    "m5": TimeFrame(5, TimeFrameUnit.Minute),
}


def _cache_path(symbol: str, timeframe: str) -> Path:
    return OHLCV_CACHE / f"{symbol}_{timeframe}.csv"


def _is_cache_fresh(path: Path, timeframe: str) -> bool:
    """
    Considera fresco el cache segun la temporalidad:
      - daily: 24 horas
      - h1: 1 hora
      - m5/m15: 15 minutos
    """
    if not path.exists():
        return False

    age_min = (time.time() - path.stat().st_mtime) / 60

    if timeframe == "daily":
        return age_min < 60 * 24
    elif timeframe == "h1":
        return age_min < 60
    else:  # m5, m15
        return age_min < 15


# ============================================================
# DESCARGA
# ============================================================
def download_ohlcv(
    symbol: str,
    timeframe: str = "daily",
    use_cache: bool = True,
    force_refresh: bool = False,
) -> pd.DataFrame | None:
    """
    Descarga velas OHLCV de Alpaca.

    Returns:
        DataFrame con DatetimeIndex (UTC) y columnas:
        Open, High, Low, Close, Volume
        o None si falla.
    """
    if timeframe not in TIMEFRAME_MAP:
        log.error(f"Timeframe invalido: {timeframe}")
        return None

    cache = _cache_path(symbol, timeframe)

    # Cache
    if use_cache and not force_refresh and _is_cache_fresh(cache, timeframe):
        try:
            df = pd.read_csv(cache, index_col=0, parse_dates=True)
            if len(df) > 0:
                return df
        except Exception:
            pass

    # Descarga
    try:
        client = _get_client()
        days = PERIODS_DAYS.get(timeframe, 365)
        end = datetime.now()
        start = end - timedelta(days=days)

        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TIMEFRAME_MAP[timeframe],
            start=start,
            end=end,
            feed=ALPACA_FEED,
        )

        bars = client.get_stock_bars(req)
        df = bars.df

        if df is None or df.empty:
            return None

        # Quitar el nivel de symbol si lo tiene
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol, level=0)

        # Renombrar a formato estandar
        df = df.rename(columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
            "trade_count": "TradeCount",
            "vwap": "VWAP_Raw",
        })

        cols = ["Open", "High", "Low", "Close", "Volume"]
        for c in cols:
            if c not in df.columns:
                log.warning(f"[{symbol} {timeframe}] falta columna {c}")
                return None

        df = df[cols].copy()
        df = df.dropna()

        if len(df) == 0:
            return None

        # Guardar
        df.to_csv(cache)

        return df

    except Exception as e:
        log.warning(f"Error {symbol} {timeframe}: {e}")
        return None


def get_multi_timeframe(symbol: str) -> dict:
    """Descarga las 3 temporalidades clave."""
    result = {}
    for tf in ["daily", "h1", "m5"]:
        df = download_ohlcv(symbol, tf)
        if df is not None and len(df) > 0:
            result[tf] = df
    return result


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    print("=== Test data_loader Alpaca con NVDA ===\n")

    for tf in ["daily", "h1", "m5"]:
        print(f"--- {tf} ---")
        df = download_ohlcv("NVDA", tf, force_refresh=True)
        if df is not None:
            print(f"  Velas: {len(df)}")
            print(f"  Rango: {df.index[0]} -> {df.index[-1]}")
            print(f"  Ultima vela:")
            print(df.tail(1).to_string())
        else:
            print(f"  FALLO")
        print()