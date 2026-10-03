"""Distribucion general del scan."""
import pandas as pd

df = pd.read_csv("cache/scan_results.csv")
print("=" * 60)
print("DISTRIBUCION POR COLOR")
print("=" * 60)
print(df["color"].value_counts())
print()

print("=" * 60)
print("DISTRIBUCION POR SIDE")
print("=" * 60)
print(df["side_label"].value_counts())
print()

print("=" * 60)
print("SCORES")
print("=" * 60)
print(df["score"].describe())
print()

print("=" * 60)
print("VERDES (score >= 75)")
print("=" * 60)
greens = df[df["score"] >= 75]
print(f"Total: {len(greens)}")
print()
if len(greens) > 0:
    cols = ["ticker", "score", "color", "side_label", "alignment", "rsi", "adx"]
    print(greens[cols].to_string(index=False))
