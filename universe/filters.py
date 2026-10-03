"""
Filtros del universo de acciones (version conservadora con cache incremental).
Reduce los ~7500 simbolos a los ~3500 operables usando yfinance.
"""
import re
import time
import random
import pandas as pd
import yfinance as yf
from pathlib import Path

from config import CACHE_DIR, MIN_PRICE, MIN_AVG_VOLUME, MIN_MARKET_CAP
from universe.universe import load_universe
from utils.logger import get_logger

log = get_logger(__name__)


FILTERED_CACHE = CACHE_DIR / "universe_filtered.csv"
PRICES_CACHE = CACHE_DIR / "universe_prices.csv"
MCAPS_CACHE = CACHE_DIR / "universe_mcaps.csv"

BATCH_SIZE = 40
PAUSE_BETWEEN_BATCHES = 3.0
HISTORY_PERIOD = "5d"
MCAP_DELAY = 0.5
MAX_RETRIES = 2


EXCLUDE_PATTERNS = [
    r"\.W$", r"\.WS$", r"\.U$", r"\.R$",
    r"\.P[A-Z]?$", r"\.PR$", r"\.RT$",
    r"[\^\-=]", r"\d{3,}",
]


def _is_clean_symbol(symbol: str) -> bool:
    if not isinstance(symbol, str) or len(symbol) == 0:
        return False
    if len(symbol) > 5:
        return False
    for pat in EXCLUDE_PATTERNS:
        if re.search(pat, symbol, flags=re.IGNORECASE):
            return False
    if not re.match(r"^[A-Z][A-Z\.\-]{0,4}$", symbol):
        return False
    return True


def clean_universe(df: pd.DataFrame) -> pd.DataFrame:
    n0 = len(df)
    df = df[df["symbol"].apply(_is_clean_symbol)]
    log.info(f"Limpieza simbolos: {n0} -> {len(df)}")
    return df.reset_index(drop=True)


# ============================================================
# FASE 1: PRECIOS Y VOLUMEN (con cache incremental)
# ============================================================
def _load_prices_cache() -> pd.DataFrame:
    if PRICES_CACHE.exists():
        try:
            df = pd.read_csv(PRICES_CACHE)
            log.info(f"Cache precios: {len(df)} tickers ya descargados")
            return df
        except Exception as e:
            log.warning(f"No se pudo leer cache precios: {e}")
    return pd.DataFrame(columns=["symbol", "price", "avg_volume"])


def _save_prices_cache(df: pd.DataFrame):
    df.to_csv(PRICES_CACHE, index=False)


def download_batch_prices(symbols: list[str]) -> pd.DataFrame:
    """
    Descarga precios y volumen en lotes con cache incremental.
    Si ya hay datos en cache, solo descarga los que faltan.
    """
    cache = _load_prices_cache()
    already = set(cache["symbol"].tolist())
    pending = [s for s in symbols if s not in already]

    log.info(f"Fase 1: {len(already)} en cache, {len(pending)} pendientes")

    if len(pending) == 0:
        log.success("Fase 1: todo estaba en cache")
        return cache

    results = []
    total = len(pending)
    n_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, total, BATCH_SIZE):
        batch = pending[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1

        for attempt in range(MAX_RETRIES + 1):
            try:
                data = yf.download(
                    tickers=batch,
                    period=HISTORY_PERIOD,
                    interval="1d",
                    group_by="ticker",
                    progress=False,
                    threads=False,
                    auto_adjust=False,
                )

                for sym in batch:
                    try:
                        if len(batch) == 1:
                            sub = data
                        else:
                            sub = data[sym] if sym in data.columns.get_level_values(0) else None
                        if sub is None or sub.empty:
                            continue
                        sub = sub.dropna()
                        if sub.empty:
                            continue
                        last_price = float(sub["Close"].iloc[-1])
                        avg_vol = float(sub["Volume"].tail(5).mean())
                        if last_price > 0 and avg_vol > 0:
                            results.append({
                                "symbol": sym,
                                "price": last_price,
                                "avg_volume": avg_vol,
                            })
                    except Exception:
                        continue
                break  # exito, salir del retry

            except Exception as e:
                if "RateLimit" in str(e) or "Too Many" in str(e):
                    wait = 5 * (2 ** attempt) + random.uniform(0, 3)
                    log.warning(f"  Rate limit batch {batch_num}, reintento en {wait:.1f}s")
                    time.sleep(wait)
                else:
                    log.warning(f"  Batch {batch_num} fallo: {e}")
                    break

        # Guardado incremental cada 5 batches
        if batch_num % 5 == 0:
            partial = pd.concat([cache, pd.DataFrame(results)], ignore_index=True)
            partial = partial.drop_duplicates(subset="symbol", keep="last")
            _save_prices_cache(partial)
            log.info(f"  Batch {batch_num}/{n_batches}: {len(partial)} acumulados (guardado)")

        time.sleep(PAUSE_BETWEEN_BATCHES + random.uniform(0, 1.0))

    # Guardado final
    final = pd.concat([cache, pd.DataFrame(results)], ignore_index=True)
    final = final.drop_duplicates(subset="symbol", keep="last")
    _save_prices_cache(final)
    log.success(f"Fase 1 completada: {len(final)} tickers totales")
    return final


# ============================================================
# FASE 2: MARKET CAP (con cache incremental)
# ============================================================
def _load_mcaps_cache() -> pd.DataFrame:
    if MCAPS_CACHE.exists():
        try:
            df = pd.read_csv(MCAPS_CACHE)
            log.info(f"Cache mcaps: {len(df)} tickers")
            return df
        except Exception:
            pass
    return pd.DataFrame(columns=["symbol", "market_cap"])


def _save_mcaps_cache(df: pd.DataFrame):
    df.to_csv(MCAPS_CACHE, index=False)


def fetch_market_cap(symbol: str) -> dict | None:
    try:
        t = yf.Ticker(symbol)
        info = t.info or {}
        mcap = info.get("marketCap")
        if mcap:
            return {"symbol": symbol, "market_cap": float(mcap)}
    except Exception:
        pass
    return None


def fetch_market_caps(symbols: list[str]) -> pd.DataFrame:
    from tqdm import tqdm

    cache = _load_mcaps_cache()
    already = set(cache["symbol"].tolist())
    pending = [s for s in symbols if s not in already]

    log.info(f"Fase 2: {len(already)} en cache, {len(pending)} pendientes")

    if len(pending) == 0:
        return cache

    results = []
    for idx, sym in enumerate(tqdm(pending, desc="Market cap"), 1):
        r = fetch_market_cap(sym)
        if r:
            results.append(r)

        if idx % 50 == 0:
            partial = pd.concat([cache, pd.DataFrame(results)], ignore_index=True)
            partial = partial.drop_duplicates(subset="symbol", keep="last")
            _save_mcaps_cache(partial)

        time.sleep(MCAP_DELAY + random.uniform(0, 0.2))

    final = pd.concat([cache, pd.DataFrame(results)], ignore_index=True)
    final = final.drop_duplicates(subset="symbol", keep="last")
    _save_mcaps_cache(final)
    log.success(f"Fase 2 completada: {len(final)} market caps totales")
    return final


# ============================================================
# CONSTRUCCION DEL UNIVERSO FILTRADO
# ============================================================
def build_filtered_universe(use_cache: bool = True) -> pd.DataFrame:
    if use_cache and FILTERED_CACHE.exists():
        age_hours = (time.time() - FILTERED_CACHE.stat().st_mtime) / 3600
        if age_hours < 24:
            log.info(f"Usando cache filtrado ({age_hours:.1f}h)")
            return pd.read_csv(FILTERED_CACHE)

    # 1. Universo
    universe = load_universe()
    universe = clean_universe(universe)
    symbols = universe["symbol"].tolist()

    # 2. Fase 1
    prices = download_batch_prices(symbols)

    # 3. Filtro precio + volumen
    n0 = len(prices)
    prices = prices[prices["price"] >= MIN_PRICE]
    n1 = len(prices)
    prices = prices[prices["avg_volume"] >= MIN_AVG_VOLUME]
    n2 = len(prices)
    log.info(f"Filtro precio: {n0} -> {n1}")
    log.info(f"Filtro volumen: {n1} -> {n2}")

    # 4. Fase 2 (solo candidatos)
    candidates = prices["symbol"].tolist()
    mcaps = fetch_market_caps(candidates)

    if len(mcaps) == 0:
        log.error("No market caps obtenidos. Abortando.")
        return pd.DataFrame()

    # 5. Merge y filtro market cap
    merged = prices.merge(mcaps, on="symbol", how="left")
    merged["market_cap"] = merged["market_cap"].fillna(0)
    n3 = len(merged)
    merged = merged[merged["market_cap"] >= MIN_MARKET_CAP]
    n4 = len(merged)
    log.info(f"Filtro market cap: {n3} -> {n4}")

    # 6. Añadir nombre y exchange
    final = merged.merge(
        universe[["symbol", "name", "exchange"]],
        on="symbol",
        how="left",
    )
    final = final.sort_values("avg_volume", ascending=False).reset_index(drop=True)

    # 7. Guardar
    final.to_csv(FILTERED_CACHE, index=False)
    log.success(f"Universo filtrado final: {len(final)} simbolos")

    return final


if __name__ == "__main__":
    df = build_filtered_universe()
    print()
    print(f"Total acciones operables: {len(df)}")
    if len(df) > 0:
        print()
        print("Top 15 por volumen:")
        cols = ["symbol", "price", "avg_volume", "market_cap"]
        print(df.nlargest(15, "avg_volume")[cols].to_string(index=False))