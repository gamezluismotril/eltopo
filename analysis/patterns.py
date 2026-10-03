"""
Deteccion de patrones de precio para ELTOPO.
Rebote, pullback, rotura, fakeout, retest, compresion.
Los mas valorados: rebote y pullback (reyes del day trading).
"""
import numpy as np
import pandas as pd

from config import SR_TOLERANCE_PCT


# ============================================================
# PESOS POR PATRON (para el score)
# ============================================================
PATTERN_WEIGHTS = {
    "rebote_en_soporte": 35,
    "rebote_en_resistencia": 35,
    "pullback_a_ema20": 30,
    "pullback_a_ema8": 28,
    "pullback_a_soporte": 30,
    "rotura_confirmada_alcista": 25,
    "rotura_confirmada_bajista": 25,
    "fakeout_alcista": 25,
    "fakeout_bajista": 25,
    "retest_soporte": 20,
    "retest_resistencia": 20,
    "compresion": 15,
}


# ============================================================
# HELPERS
# ============================================================
def _near(price, level, pct=SR_TOLERANCE_PCT):
    if level is None or level == 0:
        return False
    return abs(price - level) / level * 100 <= pct


def _get_trend(df, period=20):
    if df is None or len(df) < period:
        return "neutral"
    close = df["Close"]
    ema = close.ewm(span=period, adjust=False).mean()
    diff_pct = (close.iloc[-1] - ema.iloc[-1]) / ema.iloc[-1] * 100
    if diff_pct > 0.5:
        return "up"
    elif diff_pct < -0.5:
        return "down"
    return "neutral"


def _avg_volume(df, period=20):
    if len(df) < period:
        return df["Volume"].mean()
    return df["Volume"].iloc[-period:].mean()


# ============================================================
# PATRON 1: REBOTE
# ============================================================
def detect_rebote(df, sr_levels, ema_levels=None, vwap_val=None):
    if df is None or len(df) < 5 or not sr_levels:
        return []

    detected = []
    last = df.iloc[-1]
    close = float(last["Close"])
    open_ = float(last["Open"])
    high = float(last["High"])
    low = float(last["Low"])

    body = abs(close - open_)
    rng = high - low
    upper_wick = high - max(close, open_)
    lower_wick = min(close, open_) - low

    # Rebote en soporte
    for s in sr_levels.get("supports", []):
        lvl = s["price"]
        if not _near(close, lvl, 1.0):
            continue
        is_rejection = (lower_wick >= body * 1.5) or (close > open_ and body > rng * 0.4)
        touched_recently = any(
            _near(float(df["Low"].iloc[i]), lvl, 0.5)
            for i in range(max(0, len(df) - 5), len(df))
        )
        if is_rejection and touched_recently:
            quality = 1.0
            if s.get("score", 0) >= 70:
                quality = 1.3
            elif s.get("score", 0) >= 50:
                quality = 1.1

            detected.append({
                "name": "rebote_en_soporte",
                "direction": "bullish",
                "color": "green" if s.get("score", 0) >= 70 else "yellow",
                "level": lvl,
                "level_score": s.get("score", 0),
                "weight": int(PATTERN_WEIGHTS["rebote_en_soporte"] * quality),
            })
            break

    # Rebote en resistencia
    for r in sr_levels.get("resistances", []):
        lvl = r["price"]
        if not _near(close, lvl, 1.0):
            continue
        is_rejection = (upper_wick >= body * 1.5) or (close < open_ and body > rng * 0.4)
        touched_recently = any(
            _near(float(df["High"].iloc[i]), lvl, 0.5)
            for i in range(max(0, len(df) - 5), len(df))
        )
        if is_rejection and touched_recently:
            quality = 1.0
            if r.get("score", 0) >= 70:
                quality = 1.3
            elif r.get("score", 0) >= 50:
                quality = 1.1

            detected.append({
                "name": "rebote_en_resistencia",
                "direction": "bearish",
                "color": "red" if r.get("score", 0) >= 70 else "yellow",
                "level": lvl,
                "level_score": r.get("score", 0),
                "weight": int(PATTERN_WEIGHTS["rebote_en_resistencia"] * quality),
            })
            break

    return detected


# ============================================================
# PATRON 2: PULLBACK
# ============================================================
def detect_pullback(df, ema_levels, sr_levels=None):
    if df is None or len(df) < 20:
        return []

    detected = []
    last = df.iloc[-1]
    close = float(last["Close"])
    open_ = float(last["Open"])

    trend = _get_trend(df, 20)
    if trend == "neutral":
        return []

    ema_200 = ema_levels.get("EMA_200") if ema_levels else None
    if ema_200:
        if trend == "up" and close < ema_200:
            return []
        if trend == "down" and close > ema_200:
            return []

    if ema_levels:
        for label, key in [("EMA_8", "pullback_a_ema8"), ("EMA_20", "pullback_a_ema20")]:
            ema_val = ema_levels.get(label)
            if ema_val is None:
                continue
            if _near(close, ema_val, 0.8):
                direction = "bullish" if trend == "up" else "bearish"
                if direction == "bullish" and close > open_:
                    detected.append({
                        "name": key,
                        "direction": direction,
                        "color": "green",
                        "level": float(ema_val),
                        "weight": PATTERN_WEIGHTS[key],
                    })
                    return detected
                elif direction == "bearish" and close < open_:
                    detected.append({
                        "name": key,
                        "direction": direction,
                        "color": "red",
                        "level": float(ema_val),
                        "weight": PATTERN_WEIGHTS[key],
                    })
                    return detected

    if sr_levels and trend == "up":
        for s in sr_levels.get("supports", []):
            if _near(close, s["price"], 0.8) and s.get("score", 0) >= 50:
                detected.append({
                    "name": "pullback_a_soporte",
                    "direction": "bullish",
                    "color": "green" if s.get("score", 0) >= 70 else "yellow",
                    "level": s["price"],
                    "level_score": s.get("score", 0),
                    "weight": PATTERN_WEIGHTS["pullback_a_soporte"],
                })
                break

    return detected


# ============================================================
# PATRON 3: ROTURA CONFIRMADA
# ============================================================
def detect_rotura(df, sr_levels):
    if df is None or len(df) < 20 or not sr_levels:
        return []

    detected = []
    last = df.iloc[-1]
    prev = df.iloc[-2]
    close = float(last["Close"])
    prev_close = float(prev["Close"])
    vol = float(last["Volume"])
    avg_vol = _avg_volume(df)

    if avg_vol == 0:
        return []

    rel_vol = vol / avg_vol

    for r in sr_levels.get("resistances", []):
        lvl = r["price"]
        if prev_close < lvl and close > lvl and rel_vol >= 1.5:
            detected.append({
                "name": "rotura_confirmada_alcista",
                "direction": "bullish",
                "color": "green",
                "level": lvl,
                "relative_volume": round(rel_vol, 2),
                "weight": PATTERN_WEIGHTS["rotura_confirmada_alcista"],
            })
            return detected

    for s in sr_levels.get("supports", []):
        lvl = s["price"]
        if prev_close > lvl and close < lvl and rel_vol >= 1.5:
            detected.append({
                "name": "rotura_confirmada_bajista",
                "direction": "bearish",
                "color": "red",
                "level": lvl,
                "relative_volume": round(rel_vol, 2),
                "weight": PATTERN_WEIGHTS["rotura_confirmada_bajista"],
            })
            return detected

    return detected


# ============================================================
# PATRON 4: FAKEOUT (version estricta)
# ============================================================
def detect_fakeout(df, sr_levels):
    """
    Deteccion estricta de falsa rotura.
    Solo mira la ULTIMA vela.
    Requiere:
      - Nivel con score >= 50
      - Mecha >= 0.3% mas alla del nivel
      - Cierre vuelve dentro
      - Volumen >= 1.2x promedio
    """
    if df is None or len(df) < 20 or not sr_levels:
        return []

    detected = []
    last = df.iloc[-1]
    close_now = float(last["Close"])
    high = float(last["High"])
    low = float(last["Low"])
    vol = float(last["Volume"])
    avg_vol = _avg_volume(df)

    if avg_vol == 0:
        return []

    rel_vol = vol / avg_vol
    if rel_vol < 1.2:
        return []

    # Fakeout BAJISTA
    for r in sr_levels.get("resistances", []):
        lvl = r["price"]
        if r.get("score", 0) < 50:
            continue
        broke = high > lvl * 1.003
        closed_inside = close_now < lvl * 0.999
        if broke and closed_inside:
            detected.append({
                "name": "fakeout_bajista",
                "direction": "bearish",
                "color": "red",
                "level": lvl,
                "level_score": r.get("score", 0),
                "relative_volume": round(rel_vol, 2),
                "weight": PATTERN_WEIGHTS["fakeout_bajista"],
            })
            return detected

    # Fakeout ALCISTA
    for s in sr_levels.get("supports", []):
        lvl = s["price"]
        if s.get("score", 0) < 50:
            continue
        broke = low < lvl * 0.997
        closed_inside = close_now > lvl * 1.001
        if broke and closed_inside:
            detected.append({
                "name": "fakeout_alcista",
                "direction": "bullish",
                "color": "green",
                "level": lvl,
                "level_score": s.get("score", 0),
                "relative_volume": round(rel_vol, 2),
                "weight": PATTERN_WEIGHTS["fakeout_alcista"],
            })
            return detected

    return detected


# ============================================================
# PATRON 5: RETEST
# ============================================================
def detect_retest(df, sr_levels):
    if df is None or len(df) < 20 or not sr_levels:
        return []

    detected = []
    last = df.iloc[-1]
    close = float(last["Close"])
    low = float(last["Low"])
    high = float(last["High"])

    for s in sr_levels.get("supports", []):
        lvl = s["price"]
        if close < lvl and _near(high, lvl, 0.5):
            detected.append({
                "name": "retest_resistencia",
                "direction": "bearish",
                "color": "red",
                "level": lvl,
                "weight": PATTERN_WEIGHTS["retest_resistencia"],
            })
            return detected

    for r in sr_levels.get("resistances", []):
        lvl = r["price"]
        if close > lvl and _near(low, lvl, 0.5):
            detected.append({
                "name": "retest_soporte",
                "direction": "bullish",
                "color": "green",
                "level": lvl,
                "weight": PATTERN_WEIGHTS["retest_soporte"],
            })
            return detected

    return detected


# ============================================================
# PATRON 6: COMPRESION
# ============================================================
def detect_compresion(df):
    if df is None or len(df) < 100:
        return []

    if "BB_WIDTH" not in df.columns or "ATR_PCTL" not in df.columns:
        return []

    bb_width = float(df["BB_WIDTH"].iloc[-1])
    atr_pctl = float(df["ATR_PCTL"].iloc[-1])

    if np.isnan(bb_width) or np.isnan(atr_pctl):
        return []

    bb_series = df["BB_WIDTH"].dropna()
    if len(bb_series) < 50:
        return []

    bb_pct = (bb_width > bb_series).mean() * 100

    if bb_pct <= 20 and atr_pctl <= 30:
        return [{
            "name": "compresion",
            "direction": "neutral",
            "color": "yellow",
            "bb_percentile": round(bb_pct, 1),
            "atr_percentile": round(atr_pctl, 1),
            "weight": PATTERN_WEIGHTS["compresion"],
        }]
    return []


# ============================================================
# DETECCION COMPLETA
# ============================================================
def detect_all_patterns(df, sr_levels=None, ema_levels=None, vwap_val=None):
    if df is None or len(df) < 20:
        return []

    all_patterns = []
    all_patterns.extend(detect_rebote(df, sr_levels, ema_levels, vwap_val))
    all_patterns.extend(detect_pullback(df, ema_levels, sr_levels))
    all_patterns.extend(detect_rotura(df, sr_levels))
    all_patterns.extend(detect_fakeout(df, sr_levels))
    all_patterns.extend(detect_retest(df, sr_levels))
    all_patterns.extend(detect_compresion(df))
    return all_patterns


def patterns_score(patterns):
    if not patterns:
        return 0, "none"

    bullish = sum(p["weight"] for p in patterns if p["direction"] == "bullish")
    bearish = sum(p["weight"] for p in patterns if p["direction"] == "bearish")
    neutral = sum(p["weight"] for p in patterns if p["direction"] == "neutral")

    if bullish >= bearish:
        direction = "bullish" if bullish > 0 else "neutral"
        base = bullish + neutral * 0.5
    else:
        direction = "bearish"
        base = bearish + neutral * 0.5

    return int(min(round(base), 100)), direction


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    from data.data_loader import download_ohlcv
    from analysis.indicators import compute_all_indicators
    from analysis.levels import detect_sr_levels, score_all_levels

    print("=== Test patterns con NVDA (daily) ===\n")

    df = download_ohlcv("NVDA", "daily", force_refresh=True)
    df = compute_all_indicators(df)

    last = df.iloc[-1]
    ema_levels = {
        "EMA_8": float(last["EMA_8"]) if not pd.isna(last["EMA_8"]) else None,
        "EMA_20": float(last["EMA_20"]) if not pd.isna(last["EMA_20"]) else None,
        "EMA_200": float(last["EMA_200"]) if not pd.isna(last["EMA_200"]) else None,
    }
    vwap_val = float(last["VWAP"]) if not pd.isna(last["VWAP"]) else None

    sr = detect_sr_levels(df)
    sr_scored = score_all_levels(df, sr, ema_levels, vwap_val)

    patterns = detect_all_patterns(df, sr_scored, ema_levels, vwap_val)

    if not patterns:
        print("Sin patrones de precio detectados hoy.")
    else:
        print(f"Patrones detectados: {len(patterns)}\n")
        for p in patterns:
            print(f"  [{p['color']:>6}] {p['name']:<28} "
                  f"dir={p['direction']:<8} "
                  f"weight={p['weight']:>3}  "
                  f"nivel={p.get('level', '-')}")

    score, direction = patterns_score(patterns)
    print()
    print(f"Score de patrones: {score}/100  direccion={direction}")