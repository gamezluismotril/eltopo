"""
Deteccion de soportes y resistencias (v2 calibrada).
El corazon del sistema ELTOPO.
"""
import numpy as np
import pandas as pd
from scipy.signal import argrelextrema

from config import SWING_LOOKBACK, SR_TOLERANCE_PCT


# ============================================================
# ESCALA INTERNA PARA NIVELES INDIVIDUALES
# ============================================================
# (distinta de la escala global del sistema 85/60)
LEVEL_STRONG = 75   # verde
LEVEL_MEDIUM = 50   # amarillo
# < 50 â†’ rojo


# ============================================================
# DETECCION DE PIVOTES
# ============================================================
def find_swing_highs(df, lookback=SWING_LOOKBACK):
    highs = df["High"].values
    idx = argrelextrema(highs, np.greater_equal, order=lookback)[0]
    result = []
    for i in idx:
        if not result or i - result[-1] >= lookback:
            result.append(i)
    return result


def find_swing_lows(df, lookback=SWING_LOOKBACK):
    lows = df["Low"].values
    idx = argrelextrema(lows, np.less_equal, order=lookback)[0]
    result = []
    for i in idx:
        if not result or i - result[-1] >= lookback:
            result.append(i)
    return result


# ============================================================
# AGRUPACION
# ============================================================
def _cluster_levels(levels, tolerance_pct=SR_TOLERANCE_PCT):
    if not levels:
        return []
    levels = sorted(levels, key=lambda x: x["price"])
    clusters = []
    current = [levels[0]]
    for lvl in levels[1:]:
        ref_price = np.mean([x["price"] for x in current])
        diff_pct = abs(lvl["price"] - ref_price) / ref_price * 100
        if diff_pct <= tolerance_pct:
            current.append(lvl)
        else:
            clusters.append(current)
            current = [lvl]
    clusters.append(current)
    result = []
    for c in clusters:
        result.append({
            "price": float(np.mean([x["price"] for x in c])),
            "touches": len(c),
            "volume": float(np.mean([x.get("volume", 0) for x in c])) if c else 0.0,
            "last_idx": int(max([x.get("idx", 0) for x in c])) if c else 0,
        })
    return result


# ============================================================
# DETECCION PRINCIPAL
# ============================================================
def detect_sr_levels(df, lookback=SWING_LOOKBACK, tolerance_pct=SR_TOLERANCE_PCT):
    if df is None or len(df) < lookback * 3:
        return {"supports": [], "resistances": [], "current_price": None}

    current_price = float(df["Close"].iloc[-1])
    high_idxs = find_swing_highs(df, lookback)
    low_idxs = find_swing_lows(df, lookback)

    highs = [{"price": float(df["High"].iloc[i]),
              "volume": float(df["Volume"].iloc[i]),
              "idx": int(i)} for i in high_idxs]
    lows = [{"price": float(df["Low"].iloc[i]),
             "volume": float(df["Volume"].iloc[i]),
             "idx": int(i)} for i in low_idxs]

    high_clusters = _cluster_levels(highs, tolerance_pct)
    low_clusters = _cluster_levels(lows, tolerance_pct)

    supports = []
    resistances = []
    for c in low_clusters + high_clusters:
        if c["price"] < current_price:
            supports.append(c)
        else:
            resistances.append(c)

    supports.sort(key=lambda x: current_price - x["price"])
    resistances.sort(key=lambda x: x["price"] - current_price)

    return {
        "supports": supports[:5],
        "resistances": resistances[:5],
        "current_price": current_price,
    }


# ============================================================
# SCORING DE NIVELES (v2 calibrado)
# ============================================================
def _get_year_high_low(df):
    """Maximo y minimo del ultimo aÃ±o (252 velas)."""
    if df is None or len(df) < 20:
        return None, None
    lookback = min(252, len(df))
    recent = df.tail(lookback)
    return float(recent["High"].max()), float(recent["Low"].min())


def _get_prev_session_levels(df):
    """Cierre y rango de la sesion anterior."""
    if df is None or len(df) < 2:
        return None, None, None
    prev = df.iloc[-2]
    return float(prev["Close"]), float(prev["High"]), float(prev["Low"])


def score_level(level, df, is_support, ema_levels=None, vwap_val=None):
    """
    Puntua la fuerza de un nivel de 0 a 100.

    Pesos:
      - touches (25 pts)   -> 1 toque=12, 2=22, 3+=25
      - volume (15 pts)    -> hasta 15 con volumen 1.5x
      - confluence (35 pts) -> EMA_200=15, VWAP=12, EMA_20=10, EMA_8=6, round=5, aÃ±o=10
      - recency (15 pts)   -> lineal segun cercania en el tiempo
      - distance (10 pts)  -> bonus por cercania al precio actual
    """
    if df is None or df.empty:
        return 0, {}

    score = 0
    details = {}
    price = level["price"]
    touches = level["touches"]
    volume = level.get("volume", 0)
    last_idx = level.get("last_idx", 0)
    n = len(df)
    current_price = float(df["Close"].iloc[-1])

    # --- 1. TOQUES (25 pts) ---
    if touches == 1:
        t_score = 12
    elif touches == 2:
        t_score = 22
    else:
        t_score = 25
    score += t_score
    details["touches_pts"] = t_score

    # --- 2. VOLUMEN (15 pts) ---
    v_score = 0
    if volume > 0 and "Volume" in df.columns:
        avg_vol = df["Volume"].mean()
        if avg_vol > 0:
            v_ratio = volume / avg_vol
            v_score = min(v_ratio / 1.5, 1.0) * 15
    score += v_score
    details["volume_pts"] = round(v_score, 1)

    # --- 3. CONFLUENCIA (35 pts) ---
    confluence_pts = 0
    confluences_found = []

    # EMAs
    ema_weights = {"EMA_200": 15, "EMA_20": 10, "EMA_8": 10}
    if ema_levels:
        for label, ema_val in ema_levels.items():
            if ema_val is None or (isinstance(ema_val, float) and np.isnan(ema_val)):
                continue
            diff_pct = abs(ema_val - price) / price * 100
            if diff_pct <= SR_TOLERANCE_PCT:
                w = ema_weights.get(label, 5)
                confluence_pts += w
                confluences_found.append(label)

    # VWAP
    if vwap_val is not None and not (isinstance(vwap_val, float) and np.isnan(vwap_val)):
        diff_pct = abs(vwap_val - price) / price * 100
        if diff_pct <= SR_TOLERANCE_PCT:
            confluence_pts += 12
            confluences_found.append("VWAP")

    # Numero redondo
    for round_val in [round(price),
                      round(price / 5) * 5,
                      round(price / 10) * 10,
                      round(price / 25) * 25,
                      round(price / 50) * 50]:
        if round_val > 0:
            diff_pct = abs(round_val - price) / price * 100
            if diff_pct <= 0.3:
                confluence_pts += 5
                confluences_found.append(f"round_{round_val}")
                break

    # Maximo/minimo del aÃ±o
    y_high, y_low = _get_year_high_low(df)
    if y_high and abs(y_high - price) / price * 100 <= 1.0:
        confluence_pts += 10
        confluences_found.append("year_high")
    if y_low and abs(y_low - price) / price * 100 <= 1.0:
        confluence_pts += 10
        confluences_found.append("year_low")

    confluence_pts = min(confluence_pts, 35)
    score += confluence_pts
    details["confluence_pts"] = round(confluence_pts, 1)
    details["confluences"] = confluences_found

    # --- 4. RECENCIA (15 pts) ---
    # Si el ultimo toque fue reciente, mas puntos
    if n > 0:
        age_ratio = (n - 1 - last_idx) / n  # 0 = reciente, 1 = antiguo
        r_score = (1 - age_ratio) * 15
        score += r_score
        details["recency_pts"] = round(r_score, 1)

    # --- 5. DISTANCIA (10 pts) ---
    dist_pct = abs(current_price - price) / current_price * 100
    if dist_pct <= 0.5:
        d_score = 10
    elif dist_pct <= 1:
        d_score = 8
    elif dist_pct <= 2:
        d_score = 5
    elif dist_pct <= 4:
        d_score = 2
    else:
        d_score = 0
    score += d_score
    details["distance_pts"] = d_score

    return int(round(min(score, 100))), details


def score_all_levels(df, levels, ema_levels=None, vwap_val=None):
    scored_supports = []
    for s in levels.get("supports", []):
        sc, det = score_level(s, df, True, ema_levels, vwap_val)
        scored_supports.append({**s, "score": sc, "details": det})

    scored_resistances = []
    for r in levels.get("resistances", []):
        sc, det = score_level(r, df, False, ema_levels, vwap_val)
        scored_resistances.append({**r, "score": sc, "details": det})

    return {
        "supports": scored_supports,
        "resistances": scored_resistances,
        "current_price": levels.get("current_price"),
    }


def level_color(score):
    """Color semantico para niveles individuales."""
    if score >= LEVEL_STRONG:
        return "green"
    elif score >= LEVEL_MEDIUM:
        return "yellow"
    else:
        return "red"


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    from data.data_loader import download_ohlcv
    from analysis.indicators import compute_all_indicators

    print("=== Test levels (v2 calibrado) con NVDA ===\n")

    df = download_ohlcv("NVDA", "daily", force_refresh=True)
    df = compute_all_indicators(df)

    last = df.iloc[-1]
    ema_levels = {
        "EMA_8": float(last["EMA_8"]) if not pd.isna(last["EMA_8"]) else None,
        "EMA_20": float(last["EMA_20"]) if not pd.isna(last["EMA_20"]) else None,
        "EMA_200": float(last["EMA_200"]) if not pd.isna(last["EMA_200"]) else None,
    }
    vwap_val = float(last["VWAP"]) if not pd.isna(last["VWAP"]) else None

    levels = detect_sr_levels(df)
    scored = score_all_levels(df, levels, ema_levels, vwap_val)

    print(f"Precio actual: {scored['current_price']:.2f}")
    print(f"EMA_8: {ema_levels['EMA_8']:.2f}  EMA_20: {ema_levels['EMA_20']:.2f}  "
          f"EMA_200: {ema_levels['EMA_200']:.2f}  VWAP: {vwap_val:.2f}")
    print()

    print("--- SOPORTES ---")
    for s in scored["supports"]:
        color = level_color(s["score"])
        print(f"  [{color:>6}] {s['price']:>8.2f}  score={s['score']:>3}  "
              f"toques={s['touches']}  "
              f"[t={s['details']['touches_pts']} v={s['details']['volume_pts']} "
              f"c={s['details']['confluence_pts']} r={s['details']['recency_pts']} "
              f"d={s['details']['distance_pts']}]  "
              f"{s['details']['confluences']}")

    print()
    print("--- RESISTENCIAS ---")
    for r in scored["resistances"]:
        color = level_color(r["score"])
        print(f"  [{color:>6}] {r['price']:>8.2f}  score={r['score']:>3}  "
              f"toques={r['touches']}  "
              f"[t={r['details']['touches_pts']} v={r['details']['volume_pts']} "
              f"c={r['details']['confluence_pts']} r={r['details']['recency_pts']} "
              f"d={r['details']['distance_pts']}]  "
              f"{r['details']['confluences']}")
