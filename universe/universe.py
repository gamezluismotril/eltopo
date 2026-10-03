"""
Universo de acciones para ELTOPO.
Descarga la lista completa de tickers de NYSE + NASDAQ + AMEX
desde los ficheros publicos de NASDAQ Trader.
"""
import io
import time
import requests
import pandas as pd
from functools import lru_cache

from config import CACHE_DIR
from utils.logger import get_logger

log = get_logger(__name__)


URLS = {
    "nasdaq": "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    "other": "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
}

UNIVERSE_CACHE = CACHE_DIR / "universe.csv"


def _download_symbols(url: str) -> pd.DataFrame:
    log.info(f"Descargando simbolos de {url}")
    headers = {"User-Agent": "Mozilla/5.0 (ELTOPO Universe Loader)"}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()

    content = r.text
    df = pd.read_csv(io.StringIO(content), sep="|")

    # Quitar fila final 'File Creation Time'
    df = df[df.iloc[:, 0] != "File Creation Time"]

    return df


def _parse_nasdaq(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "symbol": df["Symbol"],
        "name": df["Security Name"],
        "exchange": "NASDAQ",
        "is_etf": df["ETF"] == "Y",
        "is_test": df["Test Issue"] == "Y",
    })


def _parse_other(df: pd.DataFrame) -> pd.DataFrame:
    exchange_map = {
        "N": "NYSE",
        "A": "AMEX",
        "P": "ARCA",
        "Z": "BATS",
        "V": "IEX",
    }
    return pd.DataFrame({
        "symbol": df["ACT Symbol"],
        "name": df["Security Name"],
        "exchange": df["Exchange"].map(exchange_map).fillna("OTHER"),
        "is_etf": df["ETF"] == "Y",
        "is_test": df["Test Issue"] == "Y",
    })


@lru_cache(maxsize=1)
def load_universe(use_cache: bool = True) -> pd.DataFrame:
    """
    Carga el universo completo de acciones.

    Returns:
        DataFrame con columnas: symbol, name, exchange, is_etf, is_test
    """
    if use_cache and UNIVERSE_CACHE.exists():
        age_hours = (time.time() - UNIVERSE_CACHE.stat().st_mtime) / 3600
        if age_hours < 24:
            log.info(f"Usando cache local ({age_hours:.1f}h de antiguedad)")
            return pd.read_csv(UNIVERSE_CACHE)

    log.info("Descargando universo desde NASDAQ Trader...")
    nasdaq_df = _download_symbols(URLS["nasdaq"])
    other_df = _download_symbols(URLS["other"])

    df = pd.concat([
        _parse_nasdaq(nasdaq_df),
        _parse_other(other_df),
    ], ignore_index=True)

    df = df[~df["is_test"]]
    df = df[~df["is_etf"]]
    df = df.drop_duplicates(subset="symbol")
    df = df.sort_values("symbol").reset_index(drop=True)

    df.to_csv(UNIVERSE_CACHE, index=False)
    log.success(f"Universo: {len(df)} simbolos")

    return df


if __name__ == "__main__":
    df = load_universe()
    print()
    print(f"Total simbolos: {len(df)}")
    print()
    print("Distribucion por exchange:")
    print(df["exchange"].value_counts())
    print()
    print("Primeros 10:")
    print(df.head(10).to_string(index=False))
