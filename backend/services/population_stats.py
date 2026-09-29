"""
NHANES 2017-2020 population reference statistics for common biomarkers.

Provides get_percentile(test_name, value) → dict | None.

Scipy is optional: if unavailable, the CDF is computed via math.erf.
"""

import math

try:
    from scipy.stats import norm as _scipy_norm
    def _norm_cdf(z: float) -> float:
        return float(_scipy_norm.cdf(z))
except ImportError:
    def _norm_cdf(z: float) -> float:
        return 0.5 * (1 + math.erf(z / math.sqrt(2)))


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

POPULATION_STATS: dict = {
    "hemoglobin": {
        "mean": 14.5, "sd": 1.4,
        "direction": "optimal_range",
        "optimal_min": 12.0, "optimal_max": 17.5,
        "unit": "g/dL",
    },
    "hematocrit": {
        "mean": 43.0, "sd": 4.5,
        "direction": "optimal_range",
        "optimal_min": 36.0, "optimal_max": 50.0,
        "unit": "%",
    },
    "white blood cells": {
        "mean": 7.2, "sd": 2.0,
        "direction": "optimal_range",
        "optimal_min": 4.5, "optimal_max": 11.0,
        "unit": "K/uL",
    },
    "platelets": {
        "mean": 255, "sd": 65,
        "direction": "optimal_range",
        "optimal_min": 150, "optimal_max": 450,
        "unit": "K/uL",
    },
    "total cholesterol": {
        "mean": 191, "sd": 41,
        "direction": "lower_is_better",
        "unit": "mg/dL",
    },
    "ldl cholesterol": {
        "mean": 114, "sd": 36,
        "direction": "lower_is_better",
        "unit": "mg/dL",
    },
    "hdl cholesterol": {
        "mean": 54, "sd": 16,
        "direction": "higher_is_better",
        "unit": "mg/dL",
    },
    "triglycerides": {
        "mean": 133, "sd": 81,
        "direction": "lower_is_better",
        "unit": "mg/dL",
    },
    "glucose": {
        "mean": 100, "sd": 26,
        "direction": "lower_is_better",
        "unit": "mg/dL",
    },
    "hba1c": {
        "mean": 5.7, "sd": 0.7,
        "direction": "lower_is_better",
        "unit": "%",
    },
    "creatinine": {
        "mean": 0.95, "sd": 0.22,
        "direction": "lower_is_better",
        "unit": "mg/dL",
    },
    "bun": {
        "mean": 15.0, "sd": 5.0,
        "direction": "lower_is_better",
        "unit": "mg/dL",
    },
    "egfr": {
        "mean": 87, "sd": 18,
        "direction": "higher_is_better",
        "unit": "mL/min/1.73m²",
    },
    "alt": {
        "mean": 26, "sd": 18,
        "direction": "lower_is_better",
        "unit": "U/L",
    },
    "ast": {
        "mean": 27, "sd": 13,
        "direction": "lower_is_better",
        "unit": "U/L",
    },
    "bilirubin": {
        "mean": 0.70, "sd": 0.30,
        "direction": "lower_is_better",
        "unit": "mg/dL",
    },
    "albumin": {
        "mean": 4.2, "sd": 0.3,
        "direction": "higher_is_better",
        "unit": "g/dL",
    },
    "sodium": {
        "mean": 140, "sd": 2.5,
        "direction": "optimal_range",
        "optimal_min": 136, "optimal_max": 145,
        "unit": "mEq/L",
    },
    "potassium": {
        "mean": 4.0, "sd": 0.4,
        "direction": "optimal_range",
        "optimal_min": 3.5, "optimal_max": 5.0,
        "unit": "mEq/L",
    },
    "calcium": {
        "mean": 9.5, "sd": 0.4,
        "direction": "optimal_range",
        "optimal_min": 8.5, "optimal_max": 10.5,
        "unit": "mg/dL",
    },
    "tsh": {
        "mean": 2.5, "sd": 1.5,
        "direction": "optimal_range",
        "optimal_min": 0.4, "optimal_max": 4.0,
        "unit": "mIU/L",
    },
    "vitamin d": {
        "mean": 52, "sd": 22,
        "direction": "higher_is_better",
        "unit": "nmol/L",
    },
    "uric acid": {
        "mean": 5.5, "sd": 1.4,
        "direction": "lower_is_better",
        "unit": "mg/dL",
    },
    "iron": {
        "mean": 100, "sd": 35,
        "direction": "optimal_range",
        "optimal_min": 60, "optimal_max": 170,
        "unit": "ug/dL",
    },
}

# ---------------------------------------------------------------------------
# Alias map  (canonical key → list of accepted aliases, all lower-cased)
# ---------------------------------------------------------------------------

_ALIASES: dict[str, list[str]] = {
    "white blood cells": ["wbc", "white blood cell count", "leukocytes"],
    "hemoglobin":        ["hgb", "hb"],
    "hematocrit":        ["hct"],
    "platelets":         ["plt", "platelet count", "thrombocytes"],
    "total cholesterol": ["cholesterol", "chol", "tc"],
    "ldl cholesterol":   ["ldl", "ldl-c", "low density lipoprotein"],
    "hdl cholesterol":   ["hdl", "hdl-c", "high density lipoprotein"],
    "triglycerides":     ["tg", "trigs", "triglyceride"],
    "glucose":           ["blood glucose", "fasting glucose", "fbs", "fpg"],
    "hba1c":             ["a1c", "glycated hemoglobin", "glycohemoglobin", "hemoglobin a1c"],
    "creatinine":        ["serum creatinine", "cr", "cre"],
    "bun":               ["blood urea nitrogen", "urea nitrogen"],
    "egfr":              ["gfr", "estimated gfr", "estimated glomerular filtration rate"],
    "alt":               ["alanine aminotransferase", "alanine transaminase", "sgpt"],
    "ast":               ["aspartate aminotransferase", "aspartate transaminase", "sgot"],
    "bilirubin":         ["total bilirubin", "tbili", "bilirubin total"],
    "albumin":           ["serum albumin"],
    "sodium":            ["na", "serum sodium"],
    "potassium":         ["k", "serum potassium"],
    "calcium":           ["ca", "serum calcium", "total calcium"],
    "tsh":               ["thyroid stimulating hormone", "thyrotropin"],
    "vitamin d":         ["25-oh vitamin d", "25-hydroxyvitamin d", "vitamin d3", "vit d", "25(oh)d"],
    "uric acid":         ["serum uric acid", "urate"],
    "iron":              ["serum iron", "fe"],
}

# Build a single lookup: alias → canonical key
_ALIAS_LOOKUP: dict[str, str] = {}
for _canonical, _aliases in _ALIASES.items():
    for _a in _aliases:
        _ALIAS_LOOKUP[_a] = _canonical
    # the canonical itself also resolves to itself
    _ALIAS_LOOKUP[_canonical] = _canonical


# ---------------------------------------------------------------------------
# Interpretation helper
# ---------------------------------------------------------------------------

def _interpret(percentile_rank: float) -> str:
    if percentile_rank >= 80:
        return "excellent"
    if percentile_rank >= 60:
        return "good"
    if percentile_rank >= 40:
        return "fair"
    if percentile_rank >= 20:
        return "borderline"
    return "needs attention"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _resolve(test_name: str) -> str | None:
    """Return canonical POPULATION_STATS key for test_name, or None."""
    key = test_name.strip().lower()
    return _ALIAS_LOOKUP.get(key)


def get_percentile(test_name: str, value: float) -> dict | None:
    """
    Compute population percentile rank for a lab result.

    Parameters
    ----------
    test_name : str
        Name of the lab test (case-insensitive; aliases accepted).
    value : float
        The patient's measured value.

    Returns
    -------
    dict with keys:
        percentile_rank  – float 0-100, rounded to 1 dp
        interpretation   – str ("excellent" … "needs attention")
        z_score          – float (raw z-score, rounded to 2 dp)
        direction        – str (from POPULATION_STATS)
    None if the test is not found.
    """
    canonical = _resolve(test_name)
    if canonical is None:
        return None

    stats = POPULATION_STATS[canonical]
    mean = stats["mean"]
    sd = stats["sd"]
    direction = stats["direction"]

    z = (value - mean) / sd

    if direction == "lower_is_better":
        # High values are bad → higher z → lower percentile rank
        percentile_rank = (1 - _norm_cdf(z)) * 100
    elif direction == "higher_is_better":
        # High values are good → higher z → higher percentile rank
        percentile_rank = _norm_cdf(z) * 100
    else:
        # "optimal_range": closeness to midpoint of [optimal_min, optimal_max]
        opt_min = stats["optimal_min"]
        opt_max = stats["optimal_max"]
        midpoint = (opt_min + opt_max) / 2
        range_width = opt_max - opt_min
        score = max(0.0, 1.0 - abs(value - midpoint) / (range_width * 1.5)) * 100
        percentile_rank = min(100.0, score)

    percentile_rank = round(percentile_rank, 1)

    return {
        "percentile_rank": percentile_rank,
        "interpretation": _interpret(percentile_rank),
        "z_score": round(z, 2),
        "direction": direction,
    }
