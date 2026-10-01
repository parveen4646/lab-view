# Absolute biological limits for common lab biomarkers.
# Values outside these ranges are almost certainly extraction errors, not real results.
# Units match the most common reporting convention for each test.
#
# Format: { normalised_test_name: (absolute_min, absolute_max) }
# Normalise: lower-case, spaces → underscores, strip punctuation.

BIOLOGICAL_LIMITS: dict[str, tuple[float, float]] = {
    # Haematology
    "hemoglobin":           (1.0,    25.0),   # g/dL
    "haemoglobin":          (1.0,    25.0),
    "hematocrit":           (5.0,    75.0),   # %
    "haematocrit":          (5.0,    75.0),
    "rbc":                  (0.5,    10.0),   # M/µL
    "wbc":                  (0.1,   100.0),   # K/µL
    "platelets":            (1.0,  1500.0),   # K/µL
    "mcv":                  (50.0,  130.0),   # fL
    "mch":                  (10.0,   50.0),   # pg
    "mchc":                 (20.0,   45.0),   # g/dL
    "rdw":                  (5.0,    30.0),   # %
    "neutrophils":          (0.0,    90.0),   # %
    "lymphocytes":          (0.0,    90.0),   # %

    # Metabolic / electrolytes
    "glucose":              (10.0,  1000.0),  # mg/dL
    "sodium":               (100.0,  180.0),  # mEq/L
    "potassium":            (1.5,    10.0),   # mEq/L
    "chloride":             (70.0,   130.0),  # mEq/L
    "bicarbonate":          (5.0,    50.0),   # mEq/L
    "calcium":              (4.0,    16.0),   # mg/dL
    "phosphorus":           (0.5,    10.0),   # mg/dL
    "magnesium":            (0.5,     5.0),   # mg/dL
    "urea":                 (2.0,   200.0),   # mg/dL
    "bun":                  (2.0,   200.0),   # mg/dL
    "creatinine":           (0.1,    20.0),   # mg/dL
    "uric_acid":            (0.5,    20.0),   # mg/dL

    # Lipid panel
    "ldl":                  (10.0,   500.0),  # mg/dL
    "hdl":                  (5.0,    200.0),  # mg/dL
    "triglycerides":        (10.0,  3000.0),  # mg/dL
    "total_cholesterol":    (50.0,   600.0),  # mg/dL
    "cholesterol":          (50.0,   600.0),

    # Liver function
    "alt":                  (1.0,   5000.0),  # U/L
    "ast":                  (1.0,   5000.0),  # U/L
    "alp":                  (10.0,  3000.0),  # U/L
    "ggt":                  (1.0,   3000.0),  # U/L
    "bilirubin":            (0.1,    30.0),   # mg/dL
    "direct_bilirubin":     (0.0,    20.0),
    "albumin":              (1.0,     6.0),   # g/dL
    "total_protein":        (3.0,    12.0),   # g/dL

    # Thyroid
    "tsh":                  (0.001,  100.0),  # µIU/mL
    "t3":                   (0.5,    15.0),   # pg/mL (free)
    "t4":                   (0.2,    10.0),   # ng/dL (free)

    # Diabetes
    "hba1c":                (3.0,    20.0),   # %
    "fasting_glucose":      (10.0,  1000.0),

    # Iron studies
    "ferritin":             (1.0,  5000.0),   # ng/mL
    "iron":                 (5.0,   500.0),   # µg/dL
    "tibc":                 (100.0,  600.0),  # µg/dL

    # Vitamins
    "vitamin_d":            (1.0,   200.0),   # ng/mL
    "vitamin_b12":          (50.0,  5000.0),  # pg/mL
    "folate":               (0.5,   100.0),   # ng/mL

    # Hormones
    "testosterone":         (0.1,  1500.0),   # ng/dL
    "estradiol":            (0.5,  5000.0),   # pg/mL
    "cortisol":             (0.5,   100.0),   # µg/dL
    "insulin":              (0.5,   500.0),   # µIU/mL

    # Kidney / urine
    "egfr":                 (1.0,   150.0),   # mL/min/1.73m²
    "microalbumin":         (0.1,  3000.0),   # mg/L
}


def normalise(name: str) -> str:
    """Convert a test name to the normalised key used in BIOLOGICAL_LIMITS."""
    return name.lower().replace(" ", "_").replace("-", "_").replace("/", "_")


def get_limit(test_name: str) -> tuple[float, float] | None:
    """Return (min, max) absolute biological limits for a test, or None if unknown."""
    return BIOLOGICAL_LIMITS.get(normalise(test_name))


def derive_status(value: float, ref_min: float | None, ref_max: float | None) -> str:
    """Normal/low/high from a value against a reference range — each bound
    checked independently, so a one-sided range (e.g. HDL "> 40", no upper
    bound) is still evaluated correctly rather than requiring both ends."""
    if ref_min is not None and value < ref_min:
        return "low"
    if ref_max is not None and value > ref_max:
        return "high"
    return "normal"
