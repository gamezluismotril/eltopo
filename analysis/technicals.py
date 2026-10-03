"""
Modulo orquestador de analisis tecnico multitemporal.
Combina daily + h1 + m5 con pesos y reglas de alineacion.
Devuelve JSON final listo para la app.
Incluye penalizacion por RSI extremo.
"""
import json
import numpy as np
import pandas as pd
from datetime import datetime, timezone

from data.data_loader import download_ohlcv
from analysis.indicators import compute_all_indicators, get_last_values, is_squeeze
from analysis.levels import detect_sr_levels, score_all_levels, level_color
from analysis.candles import detect_candles, candles_score
from analysis.patterns import detect_all_patterns, patterns_score
from utils.colors import score_to_color, bias_color
from utils.logger import get_logger

log = get_logger(__name__)


TIMEFRAME_WEIGHTS = {
    "daily": 0.50,
    "h1": 0.32,
    "m5": 0.18,
}

INTERNAL_WEIGHTS = {
    "sr": 0.30,
    "pattern": 0.25,
    "candle": 0.15,
    "trend": 0.15,
    "momentum": 0.10,
    "volume": 0.05,
}


# ============================================================
# SCORE TENDENCIA
# ============================================================
def score_trend(df, ind):
    close = ind.get("close")
    ema8 = ind.get("ema_8")
    ema20 = ind.get("ema_20")
    ema200 = ind.get("ema_200")
    adx = ind.get("adx")

    if any(v is None for v in [close, ema8, ema20, ema200]):
        return 50, "neutral"

    score = 50
    bias = "neutral"

    if close > ema8 > ema20 > ema200:
        score += 30
        bias = "bullish"
    elif close < ema8 < ema20 < ema200:
        score += 30
        bias = "bearish"
    elif close > ema20 > ema200:
        score += 18
        bias = "bullish"
    elif close < ema20 < ema200:
        score += 18
        bias = "bearish"
    elif close > ema200:
        score += 8
        bias = "bullish_weak"
    elif close < ema200:
        score += 8
        bias = "bearish_weak"

    if adx is not None:
        if adx >= 35:
            score += 20
        elif adx >= 25:
            score += 12
        elif adx >= 20:
            score += 5
        else:
            score -= 10

    return int(min(max(score, 0), 100)), bias


# ============================================================
# SCORE MOMENTUM (con deteccion de extremos)
# ============================================================
def score_momentum(df, ind):
    rsi = ind.get("rsi")
    stoch_k = ind.get("stoch_k")
    stoch_d = ind.get("stoch_d")
    macd_hist = ind.get("macd_hist")

    if rsi is None:
        return 50, "neutral"

    score = 50
    bias = "neutral"

    # RSI con deteccion de extremos (aviso suave)
    if 50 <= rsi <= 70:
        score += 15
        bias = "bullish"
    elif 30 <= rsi < 50:
        score += 5
        bias = "bearish"
    elif 70 < rsi <= 75:
        score += 5
    elif 75 < rsi <= 80:
        score -= 5
    elif rsi > 80:
        score -= 15
    elif 20 <= rsi < 30:
        score += 5
    elif 15 <= rsi < 20:
        score -= 5
    elif rsi < 15:
        score -= 15

    if stoch_k is not None and stoch_d is not None:
        if stoch_k > stoch_d and stoch_k < 80:
            score += 10
        elif stoch_k < stoch_d and stoch_k > 20:
            score -= 5

    if macd_hist is not None:
        if macd_hist > 0:
            score += 8
        else:
            score -= 5

    return int(min(max(score, 0), 100)), bias


# ============================================================
# SCORE VOLUMEN
# ============================================================
def score_volume(df, ind):
    rel_vol = ind.get("rel_vol")
    close = ind.get("close")
    vwap = ind.get("vwap")

    if rel_vol is None:
        return 50, "neutral"

    score = 50
    bias = "neutral"

    if rel_vol >= 2.0:
        score += 30
    elif rel_vol >= 1.5:
        score += 20
    elif rel_vol >= 1.2:
        score += 10
    elif rel_vol < 0.8:
        score -= 15

    if close is not None and vwap is not None:
        if close > vwap:
            score += 10
            bias = "bullish"
        else:
            score -= 5
            bias = "bearish"

    return int(min(max(score, 0), 100)), bias


# ============================================================
# REGIMEN
# ============================================================
def detect_regime(df, ind):
    adx = ind.get("adx")
    atr_pctl = ind.get("atr_pctl")
    squeeze = is_squeeze(df) if df is not None else False

    if squeeze:
        return "compressed"
    if atr_pctl is not None and atr_pctl >= 80:
        return "volatile"
    if adx is not None and adx >= 25:
        return "trending"
    if adx is not None and adx < 20:
        return "ranging"
    return "neutral"


def regime_adjustment(regime):
    if regime == "trending":
        return +5
    elif regime == "compressed":
        return 0
    elif regime == "volatile":
        return -5
    elif regime == "ranging":
        return -15
    return 0


# ============================================================
# ANALISIS DE UNA TEMPORALIDAD
# ============================================================
def analyze_timeframe(symbol, timeframe):
    log.info(f"[{symbol} {timeframe}] descargando...")

    df = download_ohlcv(symbol, timeframe)
    if df is None:
        log.warning(f"[{symbol} {timeframe}] download devolvio None")
        return None
    if len(df) < 20:
        log.warning(f"[{symbol} {timeframe}] solo {len(df)} velas")
        return None

    df = compute_all_indicators(df)
    ind = get_last_values(df)

    if ind.get("close") is None:
        log.warning(f"[{symbol} {timeframe}] close es None")
        return None

    log.info(f"[{symbol} {timeframe}] close={ind['close']:.2f} "
             f"rsi={ind.get('rsi')} adx={ind.get('adx')}")

    sr = detect_sr_levels(df)
    ema_levels = {
        "EMA_8": ind.get("ema_8"),
        "EMA_20": ind.get("ema_20"),
        "EMA_200": ind.get("ema_200"),
    }
    sr_scored = score_all_levels(df, sr, ema_levels, ind.get("vwap"))

    candles = detect_candles(df, ema_levels, ind.get("vwap"), sr_scored)
    c_score, c_dir = candles_score(candles)

    patterns = detect_all_patterns(df, sr_scored, ema_levels, ind.get("vwap"))
    p_score, p_dir = patterns_score(patterns)

    sr_score = 0
    for level in sr_scored.get("supports", []) + sr_scored.get("resistances", []):
        if level.get("score", 0) > sr_score:
            sr_score = level["score"]

    t_score, t_bias = score_trend(df, ind)
    m_score, m_bias = score_momentum(df, ind)
    v_score, v_bias = score_volume(df, ind)

    regime = detect_regime(df, ind)
    regime_adj = regime_adjustment(regime)

    # --- Calcular structure_bias ANTES de la penalizacion ---
    biases = [t_bias, p_dir if p_dir != "none" else "neutral"]
    bullish = sum(1 for b in biases if b in ("bullish", "bullish_weak"))
    bearish = sum(1 for b in biases if b in ("bearish", "bearish_weak"))
    if bullish > bearish:
        structure_bias = "bullish"
    elif bearish > bullish:
        structure_bias = "bearish"
    else:
        structure_bias = "neutral"

    # --- Score interno ---
    internal = (
        INTERNAL_WEIGHTS["sr"] * sr_score +
        INTERNAL_WEIGHTS["pattern"] * p_score +
        INTERNAL_WEIGHTS["candle"] * c_score +
        INTERNAL_WEIGHTS["trend"] * t_score +
        INTERNAL_WEIGHTS["momentum"] * m_score +
        INTERNAL_WEIGHTS["volume"] * v_score
    ) + regime_adj

    # --- Penalizacion por RSI extremo ---
    rsi_val = ind.get("rsi")
    rsi_penalty = 0
    if rsi_val is not None:
        if structure_bias == "bullish" and rsi_val > 75:
            rsi_penalty = -5
            log.info(f"[{symbol} {timeframe}] RSI {rsi_val:.1f} > 75 en LONG -> penalty {rsi_penalty}")
        elif structure_bias == "bearish" and rsi_val < 20:
            rsi_penalty = -5
            log.info(f"[{symbol} {timeframe}] RSI {rsi_val:.1f} < 20 en SHORT -> penalty {rsi_penalty}")
    internal += rsi_penalty

    internal = int(min(max(internal, 0), 100))

    return {
        "timeframe": timeframe,
        "score": internal,
        "color": score_to_color(internal),
        "structure_bias": structure_bias,
        "regime": regime,
        "rsi_penalty": rsi_penalty,
        "modules": {
            "sr": {"score": sr_score, "color": score_to_color(sr_score)},
            "pattern": {"score": p_score, "color": score_to_color(p_score)},
            "candle": {"score": c_score, "color": score_to_color(c_score)},
            "trend": {"score": t_score, "color": score_to_color(t_score)},
            "momentum": {"score": m_score, "color": score_to_color(m_score)},
            "volume": {"score": v_score, "color": score_to_color(v_score)},
        },
        "key_levels": {
            "supports": [{"price": l["price"], "score": l["score"],
                          "color": level_color(l["score"])}
                         for l in sr_scored.get("supports", [])[:3]],
            "resistances": [{"price": l["price"], "score": l["score"],
                             "color": level_color(l["score"])}
                            for l in sr_scored.get("resistances", [])[:3]],
        },
        "patterns": patterns,
        "candles": candles,
        "indicators": ind,
    }


# ============================================================
# ALINEACION
# ============================================================
def alignment_adjustment(biases):
    d = biases.get("daily", "neutral")
    h = biases.get("h1", "neutral")
    m = biases.get("m5", "neutral")

    if d == h == m == "bullish":
        return +15, "aligned_bullish"
    if d == h == m == "bearish":
        return +15, "aligned_bearish"
    if d == h == "bullish":
        return +8, "daily_h1_bullish"
    if d == h == "bearish":
        return +8, "daily_h1_bearish"
    if d == m == "bullish":
        return +3, "daily_m5_bullish"
    if d == m == "bearish":
        return +3, "daily_m5_bearish"
    if d == "bullish" and h == "bearish" and m == "bearish":
        return -25, "opposed_daily_bullish"
    if d == "bearish" and h == "bullish" and m == "bullish":
        return -25, "opposed_daily_bearish"
    return -10, "mixed"


# ============================================================
# CONFLUENCIA
# ============================================================
def confluence_check(modules_list):
    green = sum(1 for m in modules_list if m.get("color") == "green")
    if green >= 3:
        return 0, "high"
    elif green == 2:
        return 0, "medium"
    elif green == 1:
        return 0, "low"
    return 0, "very_low"


def cap_by_confluence(score, confluence):
    if confluence == "very_low":
        return min(score, 60)
    if confluence == "low":
        return min(score, 70)
    if confluence == "medium":
        return min(score, 85)
    return score


# ============================================================
# FILTROS DUROS
# ============================================================
def hard_filters(daily, h1, m5):
    blocks = []

    if daily["structure_bias"] == "neutral":
        blocks.append("daily_neutral")

    ind_d = daily["indicators"]
    if ind_d.get("atr_pct") is not None and ind_d["atr_pct"] < 1.0:
        blocks.append("low_volatility")

    if m5:
        ind_m5 = m5["indicators"]
        if ind_m5.get("rel_vol") is not None and ind_m5["rel_vol"] < 0.4:
            blocks.append("no_intraday_interest")

    d = daily["structure_bias"]
    h = h1["structure_bias"] if h1 else "neutral"
    m = m5["structure_bias"] if m5 else "neutral"
    if d == "bullish" and h == "bearish" and m == "bearish":
        blocks.append("opposed_daily")
    if d == "bearish" and h == "bullish" and m == "bullish":
        blocks.append("opposed_daily")

    return blocks


# ============================================================
# ANALISIS COMPLETO
# ============================================================
def analyze_ticker(symbol):
    log.info(f"=== Analizando {symbol} ===")

    result = {
        "ticker": symbol,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "score": 0,
        "color": "neutral",
        "side": "neutral",
        "side_label": "NEUTRAL",
        "side_color": "yellow",
        "structure_bias": "neutral",
        "confluence": "very_low",
        "timeframes": {},
        "alignment": "none",
        "regime_daily": "neutral",
        "hard_blocks": [],
        "disclaimer": "Esta aplicacion ofrece analisis de datos, no asesoramiento financiero.",
    }

    daily = analyze_timeframe(symbol, "daily")
    h1 = analyze_timeframe(symbol, "h1")
    m5 = analyze_timeframe(symbol, "m5")

    if daily is None:
        result["error"] = "Sin datos diarios"
        log.error(f"{symbol}: sin datos diarios")
        return result

    result["timeframes"]["daily"] = daily
    if h1:
        result["timeframes"]["h1"] = h1
    if m5:
        result["timeframes"]["m5"] = m5

    blocks = hard_filters(daily, h1, m5)
    result["hard_blocks"] = blocks

    weighted = daily["score"] * TIMEFRAME_WEIGHTS["daily"]
    if h1:
        weighted += h1["score"] * TIMEFRAME_WEIGHTS["h1"]
    if m5:
        weighted += m5["score"] * TIMEFRAME_WEIGHTS["m5"]

    biases = {
        "daily": daily["structure_bias"],
        "h1": h1["structure_bias"] if h1 else "neutral",
        "m5": m5["structure_bias"] if m5 else "neutral",
    }
    align_adj, align_label = alignment_adjustment(biases)
    weighted += align_adj
    result["alignment"] = align_label

    daily_modules = list(daily["modules"].values())
    _, conf = confluence_check(daily_modules)
    result["confluence"] = conf

    final_score = int(min(max(weighted, 0), 100))
    final_score = cap_by_confluence(final_score, conf)

    if blocks:
        final_score = min(final_score, 50)

    result["score"] = final_score
    result["color"] = score_to_color(final_score)
    result["structure_bias"] = daily["structure_bias"]
    result["regime_daily"] = daily["regime"]

    # Side
    bias = daily["structure_bias"]
    if bias == "bullish":
        result["side"] = "long"
        result["side_label"] = "LONG"
        result["side_color"] = "green"
    elif bias == "bearish":
        result["side"] = "short"
        result["side_label"] = "SHORT"
        result["side_color"] = "red"
    else:
        result["side"] = "neutral"
        result["side_label"] = "NEUTRAL"
        result["side_color"] = "yellow"

    log.success(f"{symbol}: score={final_score} ({result['color']}) "
                f"side={result['side_label']} "
                f"alignment={align_label} blocks={blocks}")

    return result


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    print("=== Test technicals multitemporal con NVDA ===\n")
    result = analyze_ticker("NVDA")

    print()
    print(json.dumps(result, indent=2, default=str))

    print()
    print(f"{'='*50}")
    print(f"Score final: {result['score']} ({result['color']})")
    print(f"Side: {result['side_label']} ({result['side_color']})")
    print(f"Structure bias: {result['structure_bias']}")
    print(f"Alignment: {result['alignment']}")
    print(f"Confluence: {result['confluence']}")
    print(f"Regimen daily: {result['regime_daily']}")
    if result['hard_blocks']:
        print(f"BLOQUEOS: {result['hard_blocks']}")
    print(f"{'='*50}")