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
        for fut in tqdm(as_completed(futures), total=len(symbols), desc="Analisis"):
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
# BLOQUE B: ENRIQUECIMIENTO DEL TOP
# ============================================================
def _build_reasons(raw: dict) -> list[dict]:
    """Construye la lista de motivos del score a partir del JSON de analyze_ticker."""
    reasons = []
    tf_daily = raw.get("timeframes", {}).get("daily", {})
    modules = tf_daily.get("modules", {})
    indicators = tf_daily.get("indicators", {})
    alignment = raw.get("alignment", "")
    confluence = raw.get("confluence", "")

    # Tendencia
    trend = modules.get("trend", {}).get("score", 0)
    if trend >= 80:
        reasons.append({
            "icon": "✅",
            "label": "Tendencia fuerte",
            "detail": "EMAs alineadas y ADX alto",
            "points": 25,
        })
    elif trend >= 60:
        reasons.append({
            "icon": "✅",
            "label": "Tendencia moderada",
            "detail": "EMAs alineadas",
            "points": 15,
        })
    elif trend < 40:
        reasons.append({
            "icon": "⚠️",
            "label": "Sin tendencia clara",
            "detail": "EMAs mezcladas",
            "points": -5,
        })

    # Alineación multitemporal
    if alignment == "aligned_bullish":
        reasons.append({
            "icon": "✅",
            "label": "3 temporalidades alineadas",
            "detail": "Diario, 1h y 5m apuntan arriba",
            "points": 15,
        })
    elif alignment == "aligned_bearish":
        reasons.append({
            "icon": "✅",
            "label": "3 temporalidades alineadas",
            "detail": "Diario, 1h y 5m apuntan abajo",
            "points": 15,
        })
    elif alignment and "opposed" in alignment:
        reasons.append({
            "icon": "❌",
            "label": "Conflicto entre temporalidades",
            "detail": "Señales contradictorias",
            "points": -25,
        })
    elif alignment == "mixed":
        reasons.append({
            "icon": "⚠️",
            "label": "Señal mixta",
            "detail": "Temporalidades no del todo alineadas",
            "points": -10,
        })

    # Soporte / resistencia
    sr = modules.get("sr", {}).get("score", 0)
    if sr >= 80:
        reasons.append({
            "icon": "✅",
            "label": "Niveles clave favorables",
            "detail": "Cerca de soporte o resistencia fuerte",
            "points": 12,
        })
    elif sr >= 60:
        reasons.append({
            "icon": "✅",
            "label": "Niveles S/R correctos",
            "detail": "Zona operativa razonable",
            "points": 6,
        })

    # Momentum
    momentum = modules.get("momentum", {}).get("score", 0)
    rsi = indicators.get("rsi")
    if momentum >= 70 and rsi is not None and 40 <= rsi <= 70:
        reasons.append({
            "icon": "✅",
            "label": "Momentum saludable",
            "detail": f"RSI {rsi:.1f} en zona neutral-alcista",
            "points": 10,
        })
    elif rsi is not None and rsi > 75:
        reasons.append({
            "icon": "⚠️",
            "label": "Sobrecompra",
            "detail": f"RSI {rsi:.1f} (>75)",
            "points": -5,
        })
    elif rsi is not None and rsi < 25:
        reasons.append({
            "icon": "⚠️",
            "label": "Sobreventa",
            "detail": f"RSI {rsi:.1f} (<25)",
            "points": -5,
        })

    # Volumen
    vol = modules.get("volume", {}).get("score", 0)
    rel_vol = indicators.get("rel_vol")
    if vol >= 80 and rel_vol is not None:
        reasons.append({
            "icon": "✅",
            "label": "Volumen confirma",
            "detail": f"{rel_vol:.1f}× el volumen medio",
            "points": 8,
        })

    # Patrones
    patterns = tf_daily.get("patterns", [])
    high_pat = [p for p in patterns if p.get("level_score", 0) >= 70]
    if high_pat:
        p = high_pat[0]
        reasons.append({
            "icon": "✅",
            "label": f"Patrón: {p.get('name', '').replace('_', ' ')}",
            "detail": f"En nivel {p.get('level', 0):.2f}",
            "points": 7,
        })

    # Velas
    candles = tf_daily.get("candles", [])
    if candles:
        c = candles[0]
        reasons.append({
            "icon": "✅",
            "label": f"Vela: {c.get('name', '').replace('_', ' ')}",
            "detail": f"{c.get('direction', '')} en {c.get('zone', 'N/A')}",
            "points": 5,
        })

    # Régimen
    regime = raw.get("regime_daily", "")
    if regime == "trending":
        reasons.append({
            "icon": "✅",
            "label": "Régimen en tendencia",
            "detail": "El mercado favorece la dirección",
            "points": 3,
        })
    elif regime == "ranging":
        reasons.append({
            "icon": "⚠️",
            "label": "Régimen en rango",
            "detail": "Menos continuidad esperada",
            "points": -15,
        })

    # Confluencia
    if confluence == "high":
        reasons.append({
            "icon": "✅",
            "label": "Confluencia alta",
            "detail": "Varios módulos confirman",
            "points": 5,
        })
    elif confluence == "very_low":
        reasons.append({
            "icon": "⚠️",
            "label": "Confluencia muy baja",
            "detail": "Pocos módulos confirman",
            "points": -5,
        })

    # RSI penalty explícito
    rsi_pen = tf_daily.get("rsi_penalty", 0)
    if rsi_pen < 0:
        reasons.append({
            "icon": "⚠️",
            "label": "RSI extremo",
            "detail": "Penalización aplicada",
            "points": rsi_pen,
        })

    return reasons


def _build_sparkline(symbol: str) -> list[float]:
    """Devuelve los últimos 20 cierres diarios."""
    try:
        df = download_ohlcv(symbol, "daily")
        if df is None or len(df) < 5:
            return []
        return [round(float(x), 2) for x in df["Close"].tail(20).tolist()]
    except Exception:
        return []


def _build_chart_5d(symbol: str) -> list[dict]:
    """Devuelve las últimas 5 velas OHLC."""
    try:
        df = download_ohlcv(symbol, "daily")
        if df is None or len(df) < 5:
            return []
        last5 = df.tail(5)
        chart = []
        for idx, row in last5.iterrows():
            chart.append({
                "date": str(idx.date()) if hasattr(idx, "date") else str(idx),
                "o": round(float(row["Open"]), 2),
                "h": round(float(row["High"]), 2),
                "l": round(float(row["Low"]), 2),
                "c": round(float(row["Close"]), 2),
            })
        return chart
    except Exception:
        return []


def enrich_top_ticker(raw: dict) -> dict:
    """Enriquece un ticker del top con sparkline, chart_5d y reasons."""
    symbol = raw.get("ticker", "")
    if not symbol:
        return raw

    enriched = dict(raw)
    enriched["reasons"] = _build_reasons(raw)
    enriched["sparkline"] = _build_sparkline(symbol)
    enriched["chart_5d"] = _build_chart_5d(symbol)
    return enriched


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

    # === BLOQUE B: enriquecer los 30 tickers del top ===
    log.info("Enriqueciendo top con sparkline, chart_5d y reasons...")
    top_long = [enrich_top_ticker(r) for r in top_long]
    top_short = [enrich_top_ticker(r) for r in top_short]

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