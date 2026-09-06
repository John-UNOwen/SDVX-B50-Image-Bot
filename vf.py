"""SDVX Volforce (VF) calculation — the standard per-chart B50 formula.

Ported from whiteou7/new-vf-calc (MIT). Each chart's VF is

    floor(level * (score / 10_000_000) * grade_coeff * clear_coeff * 20) * 0.001

and the B50 total is the sum of the top 50 per-chart VF values.
"""

from __future__ import annotations

import math

# Grade coefficient table (score-based).
GRADE_COEFF: dict[str, float] = {
    "PUC": 1.05,
    "S": 1.05,
    "AAA+": 1.02,
    "AAA": 1.00,
    "AA+": 0.97,
    "AA": 0.94,
    "A+": 0.91,
    "A": 0.88,
    "B": 0.85,
    "C": 0.82,
    "D": 0.80,
}

# Clear-type (lamp) coefficient table for the current version (Nabla).
CLEAR_COEFF: dict[str, float] = {
    "PERFECT ULTIMATE CHAIN": 1.10,
    "ULTIMATE CHAIN": 1.06,
    "MAXXIVE CLEAR": 1.04,
    "EXCESSIVE CLEAR": 1.02,
    "CLEAR": 1.00,
    "FAILED": 0.50,
}

# Exceed Gear (previous game version) used a slightly lower UC coefficient.
CLEAR_COEFF_EXCEED: dict[str, float] = {**CLEAR_COEFF, "ULTIMATE CHAIN": 1.05}


def round_level_for_mode(level: float, exceed: bool) -> float:
    """Exceed Gear only had whole-number chart levels; truncate when requested."""
    return math.trunc(level) if exceed else level


def calculate_vf(level, score, grade, lamp, exceed=False) -> float:
    """Return the per-chart VF for a single score.

    Args:
        level:  chart level (e.g. 17.5)
        score:  raw score (e.g. 9833032)
        grade:  grade string (e.g. "AAA+", "S", "PUC")
        lamp:   clear-type string (e.g. "EXCESSIVE CLEAR", "ULTIMATE CHAIN")
        exceed: use Exceed Gear coefficient/rounding when True
    """
    g = GRADE_COEFF.get(grade, 1.0)
    c = (CLEAR_COEFF_EXCEED if exceed else CLEAR_COEFF).get(lamp, 1.0)
    lvl = round_level_for_mode(float(level), exceed)
    base = lvl * (float(score) / 10_000_000) * g * c * 20
    return math.floor(base) * 0.001
