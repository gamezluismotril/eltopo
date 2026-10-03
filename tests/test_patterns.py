"""Test: patrones en las ultimas 30 velas de NVDA"""
from data.data_loader import download_ohlcv
from analysis.indicators import compute_all_indicators
from analysis.levels import detect_sr_levels, score_all_levels
from analysis.patterns import detect_all_patterns
import pandas as pd

df = download_ohlcv("NVDA", "daily")
df = compute_all_indicators(df)

last = df.iloc[-1]
ema = {
    "EMA_8": float(last["EMA_8"]),
    "EMA_20": float(last["EMA_20"]),
    "EMA_200": float(last["EMA_200"]),
}
vwap = float(last["VWAP"])

hits = 0
for i in range(len(df) - 30, len(df)):
    sub = df.iloc[:i+1]
    sr = detect_sr_levels(sub)
    sr_scored = score_all_levels(sub, sr, ema, vwap)
    pats = detect_all_patterns(sub, sr_scored, ema, vwap)
    if pats:
        hits += 1
        names = [p["name"] for p in pats]
        print(f"{df.index[i].date()} -> {names}")

print()
print(f"Total: {hits} dias con patrones en las ultimas 30 velas")
