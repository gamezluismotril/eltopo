"""
Script one-time: asigna sectores a los tickers del universo usando yfinance.
Version 2: con delays y reintentos para evitar bloqueos de Yahoo.

- Solo procesa los tickers que tengan sector='Otros' o vacío
- Delay de 1 seg entre peticiones
- Pausa de 30 seg cada 100 tickers
- 2 reintentos por ticker
"""
import time
from pathlib import Path

import pandas as pd
import yfinance as yf
from tqdm import tqdm

from config import CACHE_DIR
from utils.logger import get_logger

log = get_logger(__name__)

UNIVERSE_CSV = CACHE_DIR / "universe_filtered.csv"

DELAY_BETWEEN = 1.0      # segundos entre peticiones
BATCH_SIZE = 100          # tickers por batch
BATCH_PAUSE = 30          # segundos de pausa entre batches
MAX_RETRIES = 2           # reintentos por ticker


def _get_sector(symbol: str) -> str | None:
    """Intenta obtener el sector de un ticker con reintentos."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            info = yf.Ticker(symbol).info
            sector = info.get("sector")
            if sector:
                return sector
        except Exception:
            pass

        if attempt < MAX_RETRIES:
            time.sleep(2)

    return None


def main():
    if not UNIVERSE_CSV.exists():
        log.error(f"No existe {UNIVERSE_CSV}")
        return

    df = pd.read_csv(UNIVERSE_CSV)
    log.info(f"Universo: {len(df)} tickers")

    if "sector" not in df.columns:
        df["sector"] = "Otros"

    # Solo procesar los que estén como "Otros" o vacíos
    mask = df["sector"].isna() | (df["sector"] == "Otros") | (df["sector"] == "")
    to_process = df[mask].copy()
    log.info(f"Tickers a procesar: {len(to_process)}")

    if len(to_process) == 0:
        log.success("No hay nada que procesar")
        return

    fixed = 0
    still_failed = 0

    indices_to_process = to_process.index.tolist()

    for i, idx in enumerate(tqdm(indices_to_process, desc="Recuperando")):
        symbol = df.at[idx, "symbol"]

        sector = _get_sector(symbol)
        if sector:
            df.at[idx, "sector"] = sector
            fixed += 1
        else:
            still_failed += 1

        # Guardar cada 100 tickers (por si se corta)
        if (i + 1) % BATCH_SIZE == 0:
            df.to_csv(UNIVERSE_CSV, index=False)
            log.info(f"  Guardado parcial: {i+1}/{len(indices_to_process)} "
                     f"(recuperados: {fixed}, fallos: {still_failed})")

            if i + 1 < len(indices_to_process):
                log.info(f"  Pausa de {BATCH_PAUSE}s para no saturar Yahoo...")
                time.sleep(BATCH_PAUSE)
        else:
            time.sleep(DELAY_BETWEEN)

    # Guardar al final
    df.to_csv(UNIVERSE_CSV, index=False)

    log.success(f"Recuperados: {fixed} | Aún fallando: {still_failed}")

    log.info("Nueva distribución:")
    for sec, count in df["sector"].value_counts().items():
        log.info(f"  {sec}: {count}")


if __name__ == "__main__":
    main()