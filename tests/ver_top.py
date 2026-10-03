"""Analisis del Top 15 LONG y SHORT."""
import json

with open("cache/destacados.json", encoding="utf-8") as f:
    d = json.load(f)

summary = d.get("summary", {})
print("=" * 70)
print("RESUMEN")
print("=" * 70)
print(f"Total analizados:    {summary.get('total_analyzed')}")
print(f"Total destacados:    {summary.get('total_destacados')}")
print(f"Total LONG:          {summary.get('total_long')}")
print(f"Total SHORT:         {summary.get('total_short')}")
print(f"Top LONG score:      {summary.get('top_long_score')}")
print(f"Top SHORT score:     {summary.get('top_short_score')}")
print()

print("=" * 70)
print("TOP LONG")
print("=" * 70)
print(f"{'#':>2} {'Ticker':<6} {'Score':>5} {'Color':<7} {'Align':<22} {'RSI':>5} {'ATR%':>6} {'ADX':>5}")
print("-" * 70)
for i, v in enumerate(d["long"], 1):
    ind = v["timeframes"]["daily"]["indicators"]
    rsi = ind.get("rsi") or 0
    atr = ind.get("atr_pct") or 0
    adx = ind.get("adx") or 0
    print(f"{i:>2} {v['ticker']:<6} {v['score']:>5} {v['color']:<7} "
          f"{v['alignment']:<22} {rsi:>5.1f} {atr:>6.2f} {adx:>5.1f}")

print()
print("=" * 70)
print("TOP SHORT")
print("=" * 70)
print(f"{'#':>2} {'Ticker':<6} {'Score':>5} {'Color':<7} {'Align':<22} {'RSI':>5} {'ATR%':>6} {'ADX':>5}")
print("-" * 70)
for i, v in enumerate(d["short"], 1):
    ind = v["timeframes"]["daily"]["indicators"]
    rsi = ind.get("rsi") or 0
    atr = ind.get("atr_pct") or 0
    adx = ind.get("adx") or 0
    print(f"{i:>2} {v['ticker']:<6} {v['score']:>5} {v['color']:<7} "
          f"{v['alignment']:<22} {rsi:>5.1f} {atr:>6.2f} {adx:>5.1f}")
