"""
Extraction quality evaluator.

Scores each Claude extraction on two axes:
  - completeness  : how many expected fields / tests / ranges were returned
  - plausibility  : are the returned values biologically sensible?

The result is attached to processing_metadata in the API response and also
recorded in MetricsStore so it shows up in /api/stats and /metrics.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Any

from utils.medical_limits import get_limit

logger = logging.getLogger(__name__)

_PATIENT_FIELDS = {"id", "name", "lastTestDate"}
_RESULT_FIELDS = {
    "id", "testName", "value", "unit",
    "referenceRange", "status", "date", "category",
}


@dataclass
class EvaluationResult:
    completeness_score: float   # 0.0 – 1.0
    plausibility_score: float   # 0.0 – 1.0
    overall_quality: str        # "high" | "medium" | "low" | "failed"
    tests_extracted: int
    tests_with_ranges: int
    tests_with_status: int
    patient_fields_present: int
    warnings: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExtractionEvaluator:
    """Score a ClaudeAnalyzer result dict."""

    def evaluate(self, data: dict[str, Any]) -> EvaluationResult:
        warnings: list[str] = []

        patient = data.get("patientInfo") or {}
        results = data.get("latestResults") or []
        categories = data.get("testCategories") or []

        # ── Patient completeness ────────────────────────────────────────
        patient_fields_present = sum(
            1 for f in _PATIENT_FIELDS if patient.get(f) is not None
        )

        # ── Result-level stats ──────────────────────────────────────────
        n = len(results)
        tests_with_ranges = sum(
            1 for r in results
            if isinstance(r.get("referenceRange"), dict)
            and r["referenceRange"].get("min") is not None
            and r["referenceRange"].get("max") is not None
        )
        tests_with_status = sum(
            1 for r in results
            if r.get("status") in ("normal", "high", "low", "critical")
        )

        # ── Completeness score ──────────────────────────────────────────
        if n == 0:
            completeness = 0.0
            warnings.append("No lab tests extracted from the document")
        else:
            field_cov = (
                sum(
                    len(_RESULT_FIELDS & set(r.keys())) / len(_RESULT_FIELDS)
                    for r in results
                )
                / n
            )
            range_cov = tests_with_ranges / n
            status_cov = tests_with_status / n
            completeness = round((field_cov + range_cov + status_cov) / 3, 3)

        if n > 0 and tests_with_ranges < n * 0.5:
            warnings.append(
                f"Reference ranges missing for {n - tests_with_ranges} of {n} tests"
            )
        if not categories:
            warnings.append("No test categories returned")
        if not patient.get("lastTestDate"):
            warnings.append("Test date not extracted")

        # ── Plausibility score ──────────────────────────────────────────
        plausibility = self._plausibility(results, warnings)

        # ── Overall quality ─────────────────────────────────────────────
        avg = (completeness + plausibility) / 2
        if n == 0:
            quality = "failed"
        elif avg >= 0.80:
            quality = "high"
        elif avg >= 0.55:
            quality = "medium"
        else:
            quality = "low"

        return EvaluationResult(
            completeness_score=completeness,
            plausibility_score=plausibility,
            overall_quality=quality,
            tests_extracted=n,
            tests_with_ranges=tests_with_ranges,
            tests_with_status=tests_with_status,
            patient_fields_present=patient_fields_present,
            warnings=warnings,
        )

    # ------------------------------------------------------------------

    def _plausibility(
        self, results: list[dict[str, Any]], warnings: list[str]
    ) -> float:
        if not results:
            return 0.0
        ok = 0
        for r in results:
            issues = self._check(r)
            if issues:
                warnings.extend(issues)
            else:
                ok += 1
        return round(ok / len(results), 3)

    @staticmethod
    def _check(r: dict[str, Any]) -> list[str]:
        issues: list[str] = []
        name = r.get("testName", "unknown")
        value = r.get("value")

        if value is None:
            return [f"{name}: value is None"]
        if not isinstance(value, (int, float)):
            return [f"{name}: value is not numeric ({value!r})"]
        if value < 0:
            issues.append(f"{name}: negative value ({value})")

        # Biological absolute limits
        limit = get_limit(name)
        if limit:
            lo, hi = limit
            if not lo <= value <= hi:
                issues.append(
                    f"{name}: {value} is outside biological limits [{lo}, {hi}]"
                )

        # Status vs reference range consistency
        ref = r.get("referenceRange") or {}
        rmin, rmax = ref.get("min"), ref.get("max")
        stated = r.get("status")
        if rmin is not None and rmax is not None and stated == "normal":
            if value < rmin:
                issues.append(f"{name}: value {value} < ref_min {rmin} but status=normal")
            elif value > rmax:
                issues.append(f"{name}: value {value} > ref_max {rmax} but status=normal")

        return issues


# Singleton
evaluator = ExtractionEvaluator()
