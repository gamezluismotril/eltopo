"""
Backtest riguroso MULTITEMPORAL del sistema ELTOPO.
Recalcula el score usando daily + h1 + m5 en cada punto historico.
Evita look-ahead bias (solo usa velas hasta la fecha de la senal).
"""
import json
import time
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

from config import CACHE_DIR
from data.data_loader import download_ohlcv
from analysis.indicators import compute_all_indicators, get_last_values
from analysis.levels import detect_sr_levels, score_all_levels
from analysis.candles import detect_candles, candles_score
from analysis.patterns import detect_all_patterns, patterns_score
from analysis.technicals import (
    score_trend, score_momentum, score_volume,
    detect_regime, regime_adjustment,
    alignment_adjustment, confluence_check, cap_by_confluence,
    hard_filters, INTERNAL_WEIGHTS, TIMEFRAME_WEIGHTS,
)
from utils.colors import score_to_color
from utils.logger import get_logger

log = get_logger(__name__)

BACKTEST_CSV = CACHE_DIR / "backtest_results.csv"
BACKTEST_SIGNALS = CACHE_DIR / "backtest_signals.csv"


# ============================================================
# ANALISIS DE UNA TEMPORALIDAD EN UN PUNTO HISTORICO
# ============================================================
def analyze_tf_at(df_tf: pd.DataFrame, idx: int, timeframe: str) -> dict | None:
    """Analiza una temporalidad usando solo velas hasta idx."""
    if df_tf is None or idx is None or idx < 20:
        return None

    sub = df_tf.iloc[:idx+1].copy()
    if len(sub) < 20:
        return None

    sub = compute_all_indicators(sub)
    ind = get_last_values(sub)
    if ind.get("close") is None:
        return None

    sr = detect_sr_levels(sub)
    ema_levels = {
        "EMA_8": ind.get("ema_8"),
        "EMA_20": ind.get("ema_20"),
        "EMA_200": ind.get("ema_200"),
    }
    sr_scored = score_all_levels(sub, sr, ema_levels, ind.get("vwap"))

    candles = detect_candles(sub, ema_levels, ind.get("vwap"), sr_scored)
    c_score, _ = candles_score(candles)

    patterns = detect_all_patterns(sub, sr_scored, ema_levels, ind.get("vwap"))
    p_score, p_dir = patterns_score(patterns)

    sr_score = 0
    for level in sr_scored.get("supports", []) + sr_scored.get("resistances", []):
        if level.get("score", 0) > sr_score:
            sr_score = level["score"]

    t_score, t_bias = score_trend(sub, ind)
    m_score, _ = score_momentum(sub, ind)
    v_score, _ = score_volume(sub, ind)

    regime = detect_regime(sub, ind)
    regime_adj = regime_adjustment(regime)

    internal = (
        INTERNAL_WEIGHTS["sr"] * sr_score +
        INTERNAL_WEIGHTS["pattern"] * p_score +
        INTERNAL_WEIGHTS["candle"] * c_score +
        INTERNAL_WEIGHTS["trend"] * t_score +
        INTERNAL_WEIGHTS["momentum"] * m_score +
        INTERNAL_WEIGHTS["volume"] * v_score
    ) + regime_adj
    internal = int(min(max(internal, 0), 100))

    biases = [t_bias, p_dir if p_dir != "none" else "neutral"]
    bullish = sum(1 for b in biases if b in ("bullish", "bullish_weak"))
    bearish = sum(1 for b in biases if b in ("bearish", "bearish_weak"))
    if bullish > bearish:
        structure_bias = "bullish"
    elif bearish > bullish:
        structure_bias = "bearish"
    else:
        structure_bias = "neutral"

    modules = {
        "sr": sr_score,
        "pattern": p_score,
        "candle": c_score,
        "trend": t_score,
        "momentum": m_score,
        "volume": v_score,
    }

    return {
        "score": internal,
        "structure_bias": structure_bias,
        "regime": regime,
        "modules": modules,
        "indicators": ind,
        "atr": ind.get("atr"),
        "close": ind.get("close"),
        "rel_vol": ind.get("rel_vol"),
    }


# ============================================================
# SCORE MULTITEMPORAL EN UN PUNTO HISTORICO
# ============================================================
def compute_score_multitemporal(df_daily, df_h1, df_m5, idx_daily):
    """Calcula el score final multitemporal para un dia historico."""
    daily_date = df_daily.index[idx_daily]

    # Encontrar indice en h1
    idx_h1 = None
    try:
        h1_dates = df_h1.index
        valid = h1_dates[h1_dates <= daily_date]
        if len(valid) > 0:
            idx_h1 = h1_dates.get_loc(valid[-1])
            if isinstance(idx_h1, slice):
                idx_h1 = idx_h1.stop - 1
            elif isinstance(idx_h1, np.ndarray):
                idx_h1 = int(idx_h1[-1])
    except Exception:
        pass

    # Encontrar indice en m5
    idx_m5 = None
    try:
        m5_dates = df_m5.index
        valid = m5_dates[m5_dates <= daily_date]
        if len(valid) > 0:
            idx_m5 = m5_dates.get_loc(valid[-1])
            if isinstance(idx_m5, slice):
                idx_m5 = idx_m5.stop - 1
            elif isinstance(idx_m5, np.ndarray):
                idx_m5 = int(idx_m5[-1])
    except Exception:
        pass

    daily = analyze_tf_at(df_daily, idx_daily, "daily")
    if daily is None:
        return None

    h1 = analyze_tf_at(df_h1, idx_h1, "h1") if idx_h1 is not None and idx_h1 >= 20 else None
    m5 = analyze_tf_at(df_m5, idx_m5, "m5") if idx_m5 is not None and idx_m5 >= 20 else None

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

    daily_modules_list = [{"color": score_to_color(v)} for v in daily["modules"].values()]
    _, conf = confluence_check(daily_modules_list)

    final_score = int(min(max(weighted, 0), 100))
    final_score = cap_by_confluence(final_score, conf)

    blocks = hard_filters(daily, h1, m5)
    if blocks:
        final_score = min(final_score, 50)

    if daily["structure_bias"] == "bullish":
        side = "long"
    elif daily["structure_bias"] == "bearish":
        side = "short"
    else:
        side = "neutral"

    return {
        "score": final_score,
        "side": side,
        "structure_bias": daily["structure_bias"],
        "alignment": align_label,
        "confluence": conf,
        "blocks": blocks,
        "atr": daily["atr"],
        "close": daily["close"],
        "regime": daily["regime"],
        "score_daily": daily["score"],
        "score_h1": h1["score"] if h1 else None,
        "score_m5": m5["score"] if m5 else None,
    }


# ============================================================
# BACKTEST PRINCIPAL
# ============================================================
def run_backtest(symbols, start_idx=120, max_signals=1000, min_score=75):
    log.info(f"Backtest multitemporal de {len(symbols)} tickers (min_score={min_score})")
    log.info(f"Esto puede tardar 15-30 min.")

    trades = []
    signals_log = []
    green_count = 0
    processed = 0
    t0 = time.time()

    for symbol in symbols:
        df_daily = download_ohlcv(symbol, "daily")
        df_h1 = download_ohlcv(symbol, "h1")
        df_m5 = download_ohlcv(symbol, "m5")

        if df_daily is None or len(df_daily) < start_idx + 20:
            continue
        if df_h1 is None or df_m5 is None:
            continue

        processed += 1
        elapsed = (time.time() - t0) / 60
        log.info(f"[{processed}/{len(symbols)}] {symbol} | "
                 f"señales: {green_count} | trades: {len(trades)} | "
                 f"elapsed: {elapsed:.1f}min")

        for idx in range(start_idx, len(df_daily) - 6):
            try:
                score_data = compute_score_multitemporal(df_daily, df_h1, df_m5, idx)
            except Exception:
                continue

            if score_data is None:
                continue

            if score_data["score"] >= 60:
                signals_log.append({
                    "symbol": symbol,
                    "date": str(df_daily.index[idx].date()),
                    "score": score_data["score"],
                    "side": score_data["side"],
                    "alignment": score_data["alignment"],
                    "confluence": score_data["confluence"],
                    "blocks": ",".join(score_data["blocks"]),
                    "score_daily": score_data["score_daily"],
                    "score_h1": score_data["score_h1"],
                    "score_m5": score_data["score_m5"],
                })

            if score_data["score"] < min_score:
                continue
            if score_data["blocks"]:
                continue
            if score_data["side"] == "neutral":
                continue

            green_count += 1

            entry_idx = idx + 1
            if entry_idx >= len(df_daily) - 5:
                continue

            entry_price = float(df_daily["Open"].iloc[entry_idx])
            atr = score_data["atr"]
            if not atr or atr == 0:
                continue

            side = score_data["side"]

            if side == "long":
                stop = entry_price - 1.5 * atr
                target = entry_price + 3.0 * atr
            else:
                stop = entry_price + 1.5 * atr
                target = entry_price - 3.0 * atr

            exit_price = None
            exit_reason = None

            for j in range(entry_idx, min(entry_idx + 5, len(df_daily))):
                low = float(df_daily["Low"].iloc[j])
                high = float(df_daily["High"].iloc[j])

                if side == "long":
                    if low <= stop:
                        exit_price = stop
                        exit_reason = "stop"
                        break
                    if high >= target:
                        exit_price = target
                        exit_reason = "target"
                        break
                else:
                    if high >= stop:
                        exit_price = stop
                        exit_reason = "stop"
                        break
                    if low <= target:
                        exit_price = target
                        exit_reason = "target"
                        break

            if exit_price is None:
                exit_idx = min(entry_idx + 4, len(df_daily) - 1)
                exit_price = float(df_daily["Close"].iloc[exit_idx])
                exit_reason = "time"

            if side == "long":
                pnl_pct = (exit_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - exit_price) / entry_price

            trades.append({
                "symbol": symbol,
                "date": str(df_daily.index[entry_idx].date()),
                "side": side,
                "score": score_data["score"],
                "score_daily": score_data["score_daily"],
                "score_h1": score_data["score_h1"],
                "score_m5": score_data["score_m5"],
                "alignment": score_data["alignment"],
                "regime": score_data["regime"],
                "entry": entry_price,
                "exit": exit_price,
                "pnl_pct": pnl_pct,
                "exit_reason": exit_reason,
            })

            if len(trades) >= max_signals:
                log.warning(f"Limite de {max_signals} trades alcanzado")
                break

        if len(trades) >= max_signals:
            break

    trades_df = pd.DataFrame(trades)
    signals_df = pd.DataFrame(signals_log)

    if not trades_df.empty:
        trades_df.to_csv(BACKTEST_CSV, index=False)
    if not signals_df.empty:
        signals_df.to_csv(BACKTEST_SIGNALS, index=False)

    elapsed = (time.time() - t0) / 60
    log.success(f"Backtest completado en {elapsed:.1f} min")
    log.info(f"Señales verdes encontradas: {green_count}")
    log.info(f"Trades ejecutados: {len(trades)}")
    log.info(f"Señales >= 60 registradas: {len(signals_log)}")

    return trades_df, signals_df


# ============================================================
# METRICAS
# ============================================================
def compute_metrics(trades):
    if trades.empty:
        print("Sin trades para analizar")
        return

    wins = trades[trades["pnl_pct"] > 0]
    losses = trades[trades["pnl_pct"] <= 0]

    win_rate = len(wins) / len(trades) * 100
    avg_win = wins["pnl_pct"].mean() * 100 if len(wins) > 0 else 0
    avg_loss = losses["pnl_pct"].mean() * 100 if len(losses) > 0 else 0
    expectancy = (win_rate/100 * avg_win) + ((100-win_rate)/100 * avg_loss)

    total_return = trades["pnl_pct"].sum() * 100

    print()
    print("=" * 60)
    print("RESULTADOS DEL BACKTEST MULTITEMPORAL")
    print("=" * 60)
    print(f"Total trades:        {len(trades)}")
    print(f"Wins:                {len(wins)} ({win_rate:.1f}%)")
    print(f"Losses:              {len(losses)} ({100-win_rate:.1f}%)")
    print(f"Avg win:             +{avg_win:.2f}%")
    print(f"Avg loss:            {avg_loss:.2f}%")
    print(f"Expectancy:          {expectancy:+.2f}% por trade")
    print(f"Total return:        {total_return:+.1f}%")
    print()
    print("Exit reasons:")
    print(trades["exit_reason"].value_counts())
    print()
    print("Por side:")
    print(trades.groupby("side")["pnl_pct"].agg(["count", "mean", "sum"]).round(4))
    print()
    print("Por alignment:")
    print(trades.groupby("alignment")["pnl_pct"].agg(["count", "mean"]).round(4))
    print()
    print("Por rango de score:")
    trades["score_bin"] = pd.cut(trades["score"], bins=[60, 65, 70, 75, 80, 85, 100])
    print(trades.groupby("score_bin")["pnl_pct"].agg(["count", "mean"]).round(4))


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    df_scan = pd.read_csv(CACHE_DIR / "scan_results.csv")
    symbols = df_scan.head(150)["ticker"].tolist()

    print(f"Backtest multitemporal con {len(symbols)} tickers del Top 150")
    print(f"Tickers: {symbols[:10]}...")
    print()
    print("ATENCION: Va a tardar 15-30 min. No cierres la ventana.")
    print()

    trades, signals = run_backtest(symbols, start_idx=120, max_signals=1000, min_score=75)

    if not trades.empty:
        compute_metrics(trades)
    else:
        print()
        print("Sin trades con score >= 75.")
        print(f"Señales >= 60 registradas: {len(signals)}")
        if len(signals) > 0:
            print()
            print("Distribucion de scores de las señales registradas:")
            print(signals["score"].describe())
            print()
            print("Top 20 señales por score:")
            print(signals.nlargest(20, "score").to_string(index=False))