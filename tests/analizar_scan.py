"""Analisis del Top 10 y del scan completo."""
import json
import pandas as pd

print("=" * 70)
print("TOP 10 VALORES DESTACADOS")
print("=" * 70)

with open("cache/top10_destacados.json", encoding="utf-8") as f:
    d = json.load(f)

print(f"Timestamp: {d['timestamp']}")
print(f"Total: {d['count']}")
print()

for i, v in enumerate(d["valores_destacados"], 1):
    blocks = v.get("hard_blocks", [])
    print(f"{i:>2}. {v['ticker']:<6} score={v['score']:>3} ({v['color']:<6}) "
          f"bias={v['structure_bias']:<8} align={v['alignment']:<22} "
          f"blocks={blocks}")

print()
print("=" * 70)
print("DISTRIBUCION POR COLOR")
print("=" * 70)

df = pd.read_csv("cache/scan_results.csv")
print(f"Total destacados: {len(df)}")
print()
print(df["color"].value_counts())
print()

print("=" * 70)
print("TOP 25")
print("=" * 70)
cols = ["ticker", "score", "color", "bias", "alignment", "close", "atr_pct", "rsi", "adx"]
print(df.head(25)[cols].to_string(index=False))

print()
print("=" * 70)
print("TICKERS CON SCORE >= 70")
print("=" * 70)
high = df[df["score"] >= 70]
print(f"Total: {len(high)}")
print()
if len(high) > 0:
    print(high[cols].to_string(index=False))

print()
print("=" * 70)
print("BLOQUEOS APLICADOS")
print("=" * 70)
blocks = df[df["blocks"].notna() & (df["blocks"] != "")]
print(f"Tickers con bloqueos: {len(blocks)}")
print()
if len(blocks) > 0:
    print(blocks["blocks"].value_counts())