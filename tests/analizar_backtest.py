"""Analisis detallado del backtest por side."""
import pandas as pd

df = pd.read_csv("cache/backtest_results.csv")

print("=" * 70)
print("ANALISIS POR SIDE")
print("=" * 70)

for side in ["long", "short"]:
    sub = df[df["side"] == side]
    if sub.empty:
        continue

    wins = sub[sub["pnl_pct"] > 0]
    losses = sub[sub["pnl_pct"] <= 0]

    win_rate = len(wins) / len(sub) * 100
    avg_win = wins["pnl_pct"].mean() * 100 if len(wins) > 0 else 0
    avg_loss = losses["pnl_pct"].mean() * 100 if len(losses) > 0 else 0
    expectancy = sub["pnl_pct"].mean() * 100
    total = sub["pnl_pct"].sum() * 100

    print()
    print(f"--- {side.upper()} ---")
    print(f"  Total trades:    {len(sub)}")
    print(f"  Wins:            {len(wins)} ({win_rate:.1f}%)")
    print(f"  Losses:          {len(losses)} ({100-win_rate:.1f}%)")
    print(f"  Avg win:         +{avg_win:.2f}%")
    print(f"  Avg loss:        {avg_loss:.2f}%")
    print(f"  Expectancy:      {expectancy:+.2f}%")
    print(f"  Total return:    {total:+.1f}%")
    print(f"  Exit reasons:")
    for reason, cnt in sub["exit_reason"].value_counts().items():
        print(f"    {reason}: {cnt}")

print()
print("=" * 70)
print("TODOS LOS LONG (detallado)")
print("=" * 70)
longs = df[df["side"] == "long"].copy()
if not longs.empty:
    longs["pnl_pct"] = longs["pnl_pct"] * 100
    cols = ["symbol", "date", "score", "alignment", "pnl_pct", "exit_reason"]
    print(longs[cols].to_string(index=False))

print()
print("=" * 70)
print("TODOS LOS SHORT (detallado)")
print("=" * 70)
shorts = df[df["side"] == "short"].copy()
if not shorts.empty:
    shorts["pnl_pct"] = shorts["pnl_pct"] * 100
    cols = ["symbol", "date", "score", "alignment", "pnl_pct", "exit_reason"]
    print(shorts[cols].to_string(index=False))
