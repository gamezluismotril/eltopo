"""
Actualiza la lista de 'indices' en destacados.json:
  - Los 10 índices/ETFs principales (con sparkline real)
  - Top 5 tickers que MÁS SUBEN hoy
  - Top 5 tickers que MÁS BAJAN hoy
Todo mezclado en orden aleatorio.

Los movers se calculan con el sparkline real de cada ticker.
"""
import json
import random
from pathlib import Path

import pandas as pd

from config import CACHE_DIR
from engine.scanner import build_indices, _build_sparkline
from utils.logger import get_logger

log = get_logger(__name__)

DESTACADOS_JSON = CACHE_DIR / "destacados.json"
RESULTS_CSV = CACHE_DIR / "scan_results.csv"

N_MOVERS = 5  # top N subidas y top N bajadas


def load_movers(n=N_MOVERS):
    """Carga los n tickers que más suben y los n que más bajan."""
    if not RESULTS_CSV.exists():
        return [], []

    df = pd.read_csv(RESULTS_CSV)
    if df.empty:
        return [], []

    df = df[df["close"].notna()].copy()
    if df.empty:
        return [], []

    # Pre-selección rápida: cogemos 80 candidatos por volatilidad
    df = df[df["atr_pct"].notna()].sort_values("atr_pct", ascending=False).head(80)
    candidates = df["ticker"].tolist()

    all_movers = []

    for sym in candidates:
        try:
            spark = _build_sparkline(sym)
            if not spark or len(spark) < 2:
                continue
            change_pct = ((spark[-1] - spark[-2]) / spark[-2]) * 100
            all_movers.append({
                "symbol": sym,
                "name": f"{change_pct:+.2f}%",
                "price": spark[-1],
                "change_pct": round(change_pct, 2),
                "sparkline": spark,
            })
        except Exception:
            continue

    # Ordenar y separar
    all_movers.sort(key=lambda x: x["change_pct"], reverse=True)
    ups = all_movers[:n]
    downs = all_movers[-n:] if len(all_movers) >= n else []
    downs.reverse()

    return ups, downs


def main():
    if not DESTACADOS_JSON.exists():
        log.error(f"No existe {DESTACADOS_JSON}")
        return

    with open(DESTACADOS_JSON, encoding="utf-8") as f:
        data = json.load(f)

    # 1. Descargar índices
    log.info("Descargando índices...")
    indices = build_indices()
    log.info(f"  → {len(indices)} índices obtenidos")

    # 2. Buscar movers
    log.info(f"Buscando Top {N_MOVERS} subidas y Top {N_MOVERS} bajadas...")
    ups, downs = load_movers(N_MOVERS)
    log.info(f"  → {len(ups)} subidas | {len(downs)} bajadas")

    if ups:
        log.info(f"  📈 Mejor: {ups[0]['symbol']} {ups[0]['change_pct']:+.2f}%")
    if downs:
        log.info(f"  📉 Peor:  {downs[0]['symbol']} {downs[0]['change_pct']:+.2f}%")

    # 3. Mezclar todo aleatoriamente
    all_items = indices + ups + downs
    random.shuffle(all_items)

    # 4. Guardar
    data["indices"] = all_items

    with open(DESTACADOS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)

    log.success(f"Guardado: {DESTACADOS_JSON}")
    log.info(f"  Total items en 'indices': {len(all_items)}")


if __name__ == "__main__":
    main()
