"""
Indicadores tecnicos para ELTOPO (version profesional).
VWAP, EMAs, RSI, ADX, Estocastico, ATR, Volumen Relativo,
Bollinger Bands, MACD, Keltner, OBV, ATR Percentile.
"""
import pandas as pd
import numpy as np

from config import (
    EMA_PERIODS, RSI_PERIOD, ADX_PERIOD,
    STOCH_PERIOD, STOCH_SMOOTH_K, STOCH_SMOOTH_D,
    ATR_PERIOD, VOLUME_MA_PERIOD,
)


def _ensure_series(df, col):
    s = df[col]
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
    return s


# ============================================================
# EMAs
# ============================================================
def add_emas(df):
    close = _ensure_series(df, "Close")
    for p in EMA_PERIODS:
        df[f"EMA_{p}"] = close.ewm(span=p, adjust=False).mean()
    return df


# ============================================================
# VWAP
# ============================================================
def vwap(df, reset_daily=True):
    high = _ensure_series(df, "High")
    low = _ensure_series(df, "Low")
    close = _ensure_series(df, "Close")
    volume = _ensure_series(df, "Volume")
    typical = (high + low + close) / 3

    if reset_daily and hasattr(df.index, "date"):
        dates = pd.Series(df.index.date, index=df.index)
        pv = typical * volume
        return pv.groupby(dates).cumsum() / volume.groupby(dates).cumsum().replace(0, np.nan)
    return (typical * volume).cumsum() / volume.cumsum().replace(0, np.nan)


# ============================================================
# RSI
# ============================================================
def rsi(df, period=RSI_PERIOD):
    close = _ensure_series(df, "Close")
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


# ============================================================
# ADX
# ============================================================
def adx(df, period=ADX_PERIOD):
    high = _ensure_series(df, "High")
    low = _ensure_series(df, "Low")
    close = _ensure_series(df, "Close")
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    atr_val = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean() / atr_val
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean() / atr_val
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return pd.DataFrame({
        "ADX": dx.ewm(alpha=1/period, adjust=False).mean(),
        "PLUS_DI": plus_di,
        "MINUS_DI": minus_di,
    })


# ============================================================
# ESTOCASTICO
# ============================================================
def stochastic(df, period=STOCH_PERIOD, smooth_k=STOCH_SMOOTH_K, smooth_d=STOCH_SMOOTH_D):
    high = _ensure_series(df, "High")
    low = _ensure_series(df, "Low")
    close = _ensure_series(df, "Close")
    lowest = low.rolling(period).min()
    highest = high.rolling(period).max()
    k_raw = 100 * (close - lowest) / (highest - lowest).replace(0, np.nan)
    k = k_raw.rolling(smooth_k).mean()
    d = k.rolling(smooth_d).mean()
    return pd.DataFrame({"K": k, "D": d})


# ============================================================
# ATR
# ============================================================
def atr(df, period=ATR_PERIOD):
    high = _ensure_series(df, "High")
    low = _ensure_series(df, "Low")
    close = _ensure_series(df, "Close")
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()


# ============================================================
# VOLUMEN RELATIVO
# ============================================================
def relative_volume(df, period=VOLUME_MA_PERIOD):
    vol = _ensure_series(df, "Volume")
    avg = vol.rolling(period).mean()
    return vol / avg.replace(0, np.nan)


# ============================================================
# BOLLINGER
# ============================================================
def bollinger(df, period=20, std=2):
    close = _ensure_series(df, "Close")
    ma = close.rolling(period).mean()
    sd = close.rolling(period).std()
    upper = ma + std * sd
    lower = ma - std * sd
    width = (upper - lower) / ma.replace(0, np.nan) * 100
    pct_b = (close - lower) / (upper - lower).replace(0, np.nan)
    return pd.DataFrame({
        "BB_UPPER": upper, "BB_MID": ma, "BB_LOWER": lower,
        "BB_WIDTH": width, "BB_PCT_B": pct_b,
    })


# ============================================================
# MACD
# ============================================================
def macd(df, fast=12, slow=26, signal=9):
    close = _ensure_series(df, "Close")
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    line = ema_fast - ema_slow
    sig = line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({
        "MACD": line, "MACD_SIGNAL": sig, "MACD_HIST": line - sig,
    })


# ============================================================
# KELTNER
# ============================================================
def keltner(df, period=20, mult=1.5):
    close = _ensure_series(df, "Close")
    ema_mid = close.ewm(span=period, adjust=False).mean()
    atr_val = atr(df)
    return pd.DataFrame({
        "KC_UPPER": ema_mid + mult * atr_val,
        "KC_MID": ema_mid,
        "KC_LOWER": ema_mid - mult * atr_val,
    })


# ============================================================
# OBV
# ============================================================
def obv(df):
    close = _ensure_series(df, "Close")
    volume = _ensure_series(df, "Volume")
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


# ============================================================
# ATR PERCENTILE
# ============================================================
def atr_percentile(df, lookback=100):
    atr_series = atr(df)
    return atr_series.rolling(lookback).apply(
        lambda x: (x.iloc[-1] > x).mean() * 100, raw=False
    )


# ============================================================
# CALCULO COMPLETO
# ============================================================
def compute_all_indicators(df):
    if df is None or df.empty:
        return df

    df = df.copy()
    df = add_emas(df)
    df["VWAP"] = vwap(df)
    df["RSI"] = rsi(df)

    adx_df = adx(df)
    df["ADX"] = adx_df["ADX"]
    df["PLUS_DI"] = adx_df["PLUS_DI"]
    df["MINUS_DI"] = adx_df["MINUS_DI"]

    stoch = stochastic(df)
    df["STOCH_K"] = stoch["K"]
    df["STOCH_D"] = stoch["D"]

    df["ATR"] = atr(df)
    df["ATR_PCT"] = df["ATR"] / _ensure_series(df, "Close") * 100
    df["ATR_PCTL"] = atr_percentile(df)

    df["REL_VOL"] = relative_volume(df)

    bb = bollinger(df)
    for c in bb.columns:
        df[c] = bb[c]

    m = macd(df)
    for c in m.columns:
        df[c] = m[c]

    kc = keltner(df)
    for c in kc.columns:
        df[c] = kc[c]

    df["OBV"] = obv(df)
    return df


# ============================================================
# ULTIMOS VALORES (con claves en minuscula)
# ============================================================
def get_last_values(df):
    """
    Extrae los ultimos valores de todos los indicadores.
    Claves en minuscula para uso limpio.
    """
    if df is None or df.empty:
        return {}

    last = df.iloc[-1]

    def _val(key):
        if key not in last.index:
            return None
        v = last[key]

        # Si es Series/DataFrame con un solo valor, extraerlo
        if isinstance(v, pd.Series):
            if len(v) == 0:
                return None
            v = v.iloc[0]
        elif isinstance(v, pd.DataFrame):
            if v.empty:
                return None
            v = v.iloc[0, 0]

        try:
            if pd.isna(v):
                return None
        except Exception:
            pass

        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    keys = [
        "Close",
        "EMA_8", "EMA_20", "EMA_200",
        "VWAP",
        "RSI",
        "ADX", "PLUS_DI", "MINUS_DI",
        "STOCH_K", "STOCH_D",
        "ATR", "ATR_PCT", "ATR_PCTL",
        "REL_VOL",
        "BB_UPPER", "BB_MID", "BB_LOWER", "BB_WIDTH", "BB_PCT_B",
        "MACD", "MACD_SIGNAL", "MACD_HIST",
        "KC_UPPER", "KC_MID", "KC_LOWER",
        "OBV",
    ]
    return {k.lower(): _val(k) for k in keys}


def is_squeeze(df, lookback=5):
    if df is None or len(df) < 20:
        return False
    last = df.iloc[-lookback:]
    cond = (last["BB_UPPER"] < last["KC_UPPER"]) & (last["BB_LOWER"] > last["KC_LOWER"])
    return bool(cond.all())


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    from data.data_loader import download_ohlcv

    print("=== Test indicators (claves minuscula) con NVDA ===\n")
    df = download_ohlcv("NVDA", "daily", force_refresh=True)
    if df is None:
        print("Fallo descarga")
    else:
        df = compute_all_indicators(df)
        print(f"Velas: {len(df)}")
        print(f"Columnas: {len(df.columns)}")
        print()
        print("Ultimos valores:")
        vals = get_last_values(df)
        for k, v in vals.items():
            if v is None:
                print(f"  {k:>12}: None")
            else:
                print(f"  {k:>12}: {v:.4f}")
        print()
        print(f"Squeeze BB/KC: {is_squeeze(df)}")