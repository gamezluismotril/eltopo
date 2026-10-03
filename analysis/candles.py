"""
Deteccion de patrones de velas japonesas.
Solo cuentan si estan en zona clave (soporte/resistencia/EMA/VWAP).
"""
import numpy as np
import pandas as pd


# ============================================================
# HELPERS (compatibles con Series y DataFrame)
# ============================================================
def _body(c):
    if isinstance(c, pd.DataFrame):
        return (c["Close"] - c["Open"]).abs()
    return abs(c["Close"] - c["Open"])


def _range(c):
    return c["High"] - c["Low"]


def _upper_wick(c):
    if isinstance(c, pd.DataFrame):
        top = pd.concat([c["Close"], c["Open"]], axis=1).max(axis=1)
        return c["High"] - top
    return c["High"] - max(c["Close"], c["Open"])


def _lower_wick(c):
    if isinstance(c, pd.DataFrame):
        bot = pd.concat([c["Close"], c["Open"]], axis=1).min(axis=1)
        return bot - c["Low"]
    return min(c["Close"], c["Open"]) - c["Low"]


def _is_bullish(c):
    return c["Close"] > c["Open"]


def _is_bearish(c):
    return c["Close"] < c["Open"]


def _avg_body(df, n=10):
    """Media del cuerpo de las ultimas N velas."""
    if len(df) == 0:
        return 0.0
    recent = df.iloc[-min(n, len(df)):]
    bodies = (recent["Close"] - recent["Open"]).abs()
    return float(bodies.mean())


# ============================================================
# PATRONES INDIVIDUALES
# ============================================================
def is_hammer(candle, df):
    """Martillo: cuerpo pequeño arriba, mecha inferior >= 2x el cuerpo."""
    body = _body(candle)
    rng = _range(candle)
    lower = _lower_wick(candle)
    upper = _upper_wick(candle)

    if rng == 0 or body == 0:
        return False

    avg_body = _avg_body(df)
    if avg_body == 0:
        avg_body = body

    return (
        lower >= 2 * body
        and upper <= body * 0.7
        and body <= avg_body * 0.8
    )


def is_shooting_star(candle, df):
    """Estrella fugaz: cuerpo pequeño abajo, mecha superior >= 2x el cuerpo."""
    body = _body(candle)
    rng = _range(candle)
    lower = _lower_wick(candle)
    upper = _upper_wick(candle)

    if rng == 0 or body == 0:
        return False

    avg_body = _avg_body(df)
    if avg_body == 0:
        avg_body = body

    return (
        upper >= 2 * body
        and lower <= body * 0.7
        and body <= avg_body * 0.8
    )


def is_doji(candle, df):
    """Doji: cuerpo muy pequeño respecto al rango."""
    body = _body(candle)
    rng = _range(candle)
    if rng == 0:
        return False
    return body <= rng * 0.1


def is_bullish_engulfing(prev, curr):
    """Envolvente alcista."""
    return (
        _is_bearish(prev) and _is_bullish(curr)
        and curr["Open"] <= prev["Close"]
        and curr["Close"] >= prev["Open"]
    )


def is_bearish_engulfing(prev, curr):
    """Envolvente bajista."""
    return (
        _is_bullish(prev) and _is_bearish(curr)
        and curr["Open"] >= prev["Close"]
        and curr["Close"] <= prev["Open"]
    )


def is_harami_bullish(prev, curr):
    """Harami alcista."""
    if not _is_bearish(prev) or not _is_bullish(curr):
        return False
    return (
        curr["Open"] > prev["Close"]
        and curr["Close"] < prev["Open"]
        and _body(curr) < _body(prev) * 0.6
    )


def is_harami_bearish(prev, curr):
    """Harami bajista."""
    if not _is_bullish(prev) or not _is_bearish(curr):
        return False
    return (
        curr["Open"] < prev["Close"]
        and curr["Close"] > prev["Open"]
        and _body(curr) < _body(prev) * 0.6
    )


def is_three_white_soldiers(df):
    """Tres soldados blancos."""
    if len(df) < 3:
        return False
    c1, c2, c3 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    return (
        _is_bullish(c1) and _is_bullish(c2) and _is_bullish(c3)
        and c2["Close"] > c1["Close"] and c3["Close"] > c2["Close"]
        and c2["Open"] > c1["Open"] and c3["Open"] > c2["Open"]
    )


def is_three_black_crows(df):
    """Tres cuervos negros."""
    if len(df) < 3:
        return False
    c1, c2, c3 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    return (
        _is_bearish(c1) and _is_bearish(c2) and _is_bearish(c3)
        and c2["Close"] < c1["Close"] and c3["Close"] < c2["Close"]
        and c2["Open"] < c1["Open"] and c3["Open"] < c2["Open"]
    )


# ============================================================
# CONTEXTO
# ============================================================
def is_in_key_zone(candle, df, ema_levels, vwap_val, sr_levels, tolerance_pct=0.5):
    """Comprueba si el precio esta cerca de una zona clave."""
    price = float(candle["Close"])
    zones = []

    if ema_levels:
        for label, val in ema_levels.items():
            if val is not None and not (isinstance(val, float) and np.isnan(val)):
                zones.append((label, val))

    if vwap_val is not None and not (isinstance(vwap_val, float) and np.isnan(vwap_val)):
        zones.append(("VWAP", vwap_val))

    if sr_levels:
        for s in sr_levels.get("supports", []):
            zones.append(("support", s["price"]))
        for r in sr_levels.get("resistances", []):
            zones.append(("resistance", r["price"]))

    for label, val in zones:
        if val == 0:
            continue
        diff_pct = abs(val - price) / price * 100
        if diff_pct <= tolerance_pct:
            return True, label
    return False, None


# ============================================================
# DETECCION PRINCIPAL
# ============================================================
def detect_candles(df, ema_levels=None, vwap_val=None, sr_levels=None):
    """
    Detecta patrones de velas en las ultimas velas.
    Devuelve lista de dicts con {name, direction, color, in_zone, zone}.
    """
    if df is None or len(df) < 5:
        return []

    detected = []
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else None

    in_zone, zone_label = is_in_key_zone(
        last, df, ema_levels, vwap_val, sr_levels
    )

    # --- Individuales ---
    if is_hammer(last, df):
        detected.append({
            "name": "hammer",
            "direction": "bullish",
            "color": "green" if in_zone else "yellow",
            "in_zone": in_zone,
            "zone": zone_label,
        })

    if is_shooting_star(last, df):
        detected.append({
            "name": "shooting_star",
            "direction": "bearish",
            "color": "red" if in_zone else "yellow",
            "in_zone": in_zone,
            "zone": zone_label,
        })

    if is_doji(last, df):
        detected.append({
            "name": "doji",
            "direction": "neutral",
            "color": "yellow",
            "in_zone": in_zone,
            "zone": zone_label,
        })

    # --- 2 velas ---
    if prev is not None:
        if is_bullish_engulfing(prev, last):
            detected.append({
                "name": "bullish_engulfing",
                "direction": "bullish",
                "color": "green" if in_zone else "yellow",
                "in_zone": in_zone,
                "zone": zone_label,
            })

        if is_bearish_engulfing(prev, last):
            detected.append({
                "name": "bearish_engulfing",
                "direction": "bearish",
                "color": "red" if in_zone else "yellow",
                "in_zone": in_zone,
                "zone": zone_label,
            })

        if is_harami_bullish(prev, last):
            detected.append({
                "name": "bullish_harami",
                "direction": "bullish",
                "color": "green" if in_zone else "yellow",
                "in_zone": in_zone,
                "zone": zone_label,
            })

        if is_harami_bearish(prev, last):
            detected.append({
                "name": "bearish_harami",
                "direction": "bearish",
                "color": "red" if in_zone else "yellow",
                "in_zone": in_zone,
                "zone": zone_label,
            })

    # --- 3 velas ---
    if is_three_white_soldiers(df):
        detected.append({
            "name": "three_white_soldiers",
            "direction": "bullish",
            "color": "green",
            "in_zone": in_zone,
            "zone": zone_label,
        })

    if is_three_black_crows(df):
        detected.append({
            "name": "three_black_crows",
            "direction": "bearish",
            "color": "red",
            "in_zone": in_zone,
            "zone": zone_label,
        })

    return detected


def candles_score(candles):
    """Convierte la lista de velas en un score 0-100."""
    if not candles:
        return 0, "none"

    priority = {
        "three_white_soldiers": 95,
        "three_black_crows": 95,
        "bullish_engulfing": 80,
        "bearish_engulfing": 80,
        "hammer": 70,
        "shooting_star": 70,
        "bullish_harami": 60,
        "bearish_harami": 60,
        "doji": 50,
    }

    best = max(candles, key=lambda c: priority.get(c["name"], 0))
    base = priority.get(best["name"], 0)

    if best.get("in_zone"):
        base = min(base + 10, 100)

    return base, best["direction"]


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    from data.data_loader import download_ohlcv
    from analysis.indicators import compute_all_indicators
    from analysis.levels import detect_sr_levels, score_all_levels

    print("=== Test candles con NVDA (daily) ===\n")

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

    print("--- ULTIMAS 3 VELAS ---")
    print(df[["Open", "High", "Low", "Close"]].tail(3).to_string())
    print()

    detected = detect_candles(df, ema_levels, vwap_val, sr_scored)
    if not detected:
        print("Sin patrones de velas detectados.")
    else:
        print(f"Patrones detectados: {len(detected)}")
        for c in detected:
            print(f"  [{c['color']:>6}] {c['name']:<22} dir={c['direction']:<8} "
                  f"in_zone={c['in_zone']} zone={c['zone']}")

    score, direction = candles_score(detected)
    print()
    print(f"Score de velas: {score}/100  direccion={direction}")