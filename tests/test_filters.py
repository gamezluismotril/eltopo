"""
Test rapido del filtro con 100 tickers.
"""
from universe.universe import load_universe
from universe.filters import clean_universe, fetch_metrics_batch, apply_filters

# 1. Cargar universo
u = load_universe()
print(f"Universo bruto: {len(u)}")

# 2. Limpieza de simbolos
u_clean = clean_universe(u)
print(f"Tras limpieza: {len(u_clean)}")

# 3. Solo primeros 100
sample = u_clean.head(100).copy()
print(f"Probando con: {len(sample)} simbolos")
print()

# 4. Descargar metricas
metrics = fetch_metrics_batch(sample["symbol"].tolist(), max_workers=10)
print()
print(f"Metricas obtenidas: {len(metrics)}")

if len(metrics) > 0:
    print()
    print("Ejemplos de metricas:")
    print(metrics.head(10).to_string(index=False))
