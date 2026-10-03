"""
Sistema de colores semantico para ELTOPO.

Escala:
    verde    -> score >= 85 (estructura clara)
    amarillo -> score 60-84 (mixta)
    rojo     -> score < 60 (debil o contradictoria)
    neutral  -> sin datos
"""

from config import (
    COLOR_GREEN_THRESHOLD,
    COLOR_YELLOW_THRESHOLD,
    COLOR_GREEN,
    COLOR_YELLOW,
    COLOR_RED,
    COLOR_NEUTRAL,
)


ANSI = {
    COLOR_GREEN: "\033[92m",
    COLOR_YELLOW: "\033[93m",
    COLOR_RED: "\033[91m",
    COLOR_NEUTRAL: "\033[90m",
    "reset": "\033[0m",
}

EMOJI = {
    COLOR_GREEN: "\U0001F7E2",     # verde
    COLOR_YELLOW: "\U0001F7E1",    # amarillo
    COLOR_RED: "\U0001F534",       # rojo
    COLOR_NEUTRAL: "\u26AA",       # blanco/neutral
}


def score_to_color(score):
    """
    Convierte un score numerico en color semantico.
    """
    if score is None:
        return COLOR_NEUTRAL
    try:
        s = float(score)
    except (TypeError, ValueError):
        return COLOR_NEUTRAL

    if s >= COLOR_GREEN_THRESHOLD:
        return COLOR_GREEN
    elif s >= COLOR_YELLOW_THRESHOLD:
        return COLOR_YELLOW
    else:
        return COLOR_RED


def format_score(score):
    """Formatea un score con emoji y color ANSI."""
    color = score_to_color(score)
    emoji = EMOJI[color]
    ansi = ANSI[color]
    reset = ANSI["reset"]
    if score is None:
        return f"{emoji} {ansi}--{reset}"
    return f"{emoji} {ansi}{score:.0f}{reset}"


def bias_color(bias):
    """Convierte sesgo a color."""
    bias = (bias or "").lower()
    if bias in ("bullish", "up", "alcista"):
        return COLOR_GREEN
    elif bias in ("bearish", "down", "bajista"):
        return COLOR_RED
    return COLOR_YELLOW


if __name__ == "__main__":
    print("=== Test escala de colores ===")
    for s in [None, 20, 45, 59, 60, 72, 84, 85, 92, 100]:
        label = f"{str(s):>4}" if s is not None else "None"
        print(f"  Score {label} -> {format_score(s)}  ({score_to_color(s)})")

    print()
    print("=== Test sesgos ===")
    for b in ["bullish", "bearish", "neutral", "up", "down"]:
        print(f"  {b:>10} -> {bias_color(b)}")