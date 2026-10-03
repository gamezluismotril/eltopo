"""
Scanner multitemporal para ELTOPO usando Alpaca.
Analiza los tickers del universo filtrado y genera
el ranking de "Valores destacados" separado en LONG y SHORT.
"""
import json
import time
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

from config import (
    CACHE_DIR, TOP_N, MIN_SCORE_FOR_TOP, ALPACA_MAX_WORKERS,
)
from data.data_loader import download_ohlcv
from analysis.technicals import analyze_ticker
from utils.logger import get_logger

log = get_logger(__name__)


UNIVERSE_CSV = CACHE_DIR / "universe_filtered.csv"
RESULTS_CSV = CACHE_DIR / "scan_results.csv"
TOP_JSON = CACHE_DIR / "destacados.json"


# ============================================================
# UNIVERSO
# ============================================================
def load_universe_symbols() -> list[str]:
    if not UNIVERSE_CSV.exists():
        log.error(f"No existe {UNIVERSE_CSV}")
        return []
    df = pd.read_csv(UNIVERSE_CSV)
    symbols = df["symbol"].dropna().astype(str).tolist()
    log.info(f"Universo: {len(symbols)} tickers")
    return symbols


# ============================================================
# PRE-CARGA
# ============================================================
def preload_candles(symbols: list[str]):
    log.info(f"Pre-cargando velas de {len(symbols)} tickers...")

    stats = {"ok": 0, "daily_fail": 0, "partial": 0}
    t0 = time.time()

    for i, symbol in enumerate(tqdm(symbols, desc="Pre-carga")):
        try:
            d = download_ohlcv(symbol, "daily")
            if d is None or len(d) < 50:
                stats["daily_fail"] += 1
                continue

            h1 = download_ohlcv(symbol, "h1")
            m5 = download_ohlcv(symbol, "m5")

            if h1 is None or m5 is None:
                stats["partial"] += 1
            else:
                stats["ok"] += 1

            if (i + 1) % 50 == 0:
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed * 60
                log.info(f"  Progreso: {i+1}/{len(symbols)} | "
                         f"velocidad: {rate:.0f} tickers/min")

        except Exception as e:
            log.warning(f"[{symbol}] pre-carga fallo: {e}")
            stats["daily_fail"] += 1

    elapsed = (time.time() - t0) / 60
    log.success(f"Pre-carga completada en {elapsed:.1f} min: {stats}")


# ============================================================
# ANALISIS
# ============================================================
def _analyze_one(symbol: str) -> dict | None:
    try:
        result = analyze_ticker(symbol)
        if "error" in result:
            return None
        return result
    except Exception as e:
        return {"ticker": symbol, "error": str(e)}


def analyze_all(symbols: list[str], max_workers: int = ALPACA_MAX_WORKERS) -> list[dict]:
    log.info(f"Analizando {len(symbols)} tickers con {max_workers} workers...")

    results = []
    errors = 0
    t0 = time.time()

    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_analyze_one, s): s for s in symbols}
        for fut in tqdm(as_completed(futures), total=len(symbols), desc="Análisis"):
            try:
                r = fut.result()
                if r is None or "error" in r:
                    errors += 1
                    continue
                results.append(r)
            except Exception:
                errors += 1

    elapsed = (time.time() - t0) / 60
    log.success(f"Analizados: {len(results)} OK, {errors} fallos ({elapsed:.1f} min)")
    return results


# ============================================================
# FILTRADO
# ============================================================
def filter_and_rank(results: list[dict], min_score: int = MIN_SCORE_FOR_TOP) -> pd.DataFrame:
    if not results:
        return pd.DataFrame()

    rows = []
    for r in results:
        score = r.get("score", 0)
        if score < min_score:
            continue

        tf_daily = r.get("timeframes", {}).get("daily", {})
        ind_daily = tf_daily.get("indicators", {})
        key_levels = tf_daily.get("key_levels", {})

        rows.append({
            "ticker": r["ticker"],
            "score": score,
            "color": r.get("color"),
            "side": r.get("side", "neutral"),
            "side_label": r.get("side_label", "NEUTRAL"),
            "bias": r.get("structure_bias"),
            "alignment": r.get("alignment"),
            "confluence": r.get("confluence"),
            "regime": r.get("regime_daily"),
            "blocks": ",".join(r.get("hard_blocks", [])),
            "close": ind_daily.get("close"),
            "atr_pct": ind_daily.get("atr_pct"),
            "rsi": ind_daily.get("rsi"),
            "adx": ind_daily.get("adx"),
            "rel_vol": ind_daily.get("rel_vol"),
            "nearest_support": (key_levels.get("supports") or [{}])[0].get("price"),
            "nearest_resistance": (key_levels.get("resistances") or [{}])[0].get("price"),
            "score_daily": tf_daily.get("score"),
            "score_h1": r.get("timeframes", {}).get("h1", {}).get("score"),
            "score_m5": r.get("timeframes", {}).get("m5", {}).get("score"),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    return df


# ============================================================
# GUARDADO
# ============================================================
def save_results(df: pd.DataFrame, results_raw: list[dict]):
    df.to_csv(RESULTS_CSV, index=False)
    log.success(f"Resultados guardados: {RESULTS_CSV}")

    # Separar LONG / SHORT
    df_long = df[df["side"] == "long"].head(TOP_N) if not df.empty else pd.DataFrame()
    df_short = df[df["side"] == "short"].head(TOP_N) if not df.empty else pd.DataFrame()

    top_long_symbols = df_long["ticker"].tolist() if not df_long.empty else []
    top_short_symbols = df_short["ticker"].tolist() if not df_short.empty else []

    top_long = [r for r in results_raw if r["ticker"] in top_long_symbols]
    top_short = [r for r in results_raw if r["ticker"] in top_short_symbols]
    top_long.sort(key=lambda r: r.get("score", 0), reverse=True)
    top_short.sort(key=lambda r: r.get("score", 0), reverse=True)

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_analyzed": len(results_raw),
            "total_destacados": len(df),
            "total_long": len(df_long),
            "total_short": len(df_short),
            "top_long_score": int(df_long["score"].max()) if not df_long.empty else 0,
            "top_short_score": int(df_short["score"].max()) if not df_short.empty else 0,
            "top_n_per_side": TOP_N,
            "visible_default": 5,
        },
        "long": top_long,
        "short": top_short,
        "disclaimer": "Esta aplicacion ofrece analisis de datos, no asesoramiento financiero.",
    }

    with open(TOP_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    log.success(f"Top {TOP_N} LONG + Top {TOP_N} SHORT guardados: {TOP_JSON}")
    log.info(f"  LONG: {len(top_long)} | SHORT: {len(top_short)}")


# ============================================================
# SCANNER
# ============================================================
def run_scanner(
    limit: int | None = None,
    max_workers: int = ALPACA_MAX_WORKERS,
    preload: bool = True,
    min_score: int = MIN_SCORE_FOR_TOP,
):
    t0 = time.time()
    log.info("=" * 60)
    log.info("ELTOPO Scanner - Inicio")
    log.info("=" * 60)

    symbols = load_universe_symbols()
    if limit:
        symbols = symbols[:limit]
        log.info(f"Limite aplicado: {limit}")

    if not symbols:
        log.error("Sin simbolos")
        return

    if preload:
        preload_candles(symbols)

    results = analyze_all(symbols, max_workers=max_workers)

    df = filter_and_rank(results, min_score=min_score)

    save_results(df, results)

    elapsed = (time.time() - t0) / 60
    log.info("=" * 60)
    log.info(f"Scanner completado en {elapsed:.1f} minutos")
    log.info(f"Tickers analizados: {len(results)}")
    log.info(f"Destacados (score >= {min_score}): {len(df)}")
    if not df.empty:
        log.info(f"Score max: {df['score'].max()}")
        log.info(f"Top 3 LONG:")
        for _, row in df[df["side"] == "long"].head(3).iterrows():
            log.info(f"  {row['ticker']}: {row['score']} ({row['color']})")
        log.info(f"Top 3 SHORT:")
        for _, row in df[df["side"] == "short"].head(3).iterrows():
            log.info(f"  {row['ticker']}: {row['score']} ({row['color']})")
    log.info("=" * 60)


if __name__ == "__main__":
    import sys

    limit = None
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            pass

    run_scanner(limit=limit, max_workers=ALPACA_MAX_WORKERS)