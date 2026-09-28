"""
Input and output guardrails for the lab-report pipeline.

InputGuardrails   — validates the PDF extraction result BEFORE sending to Claude.
OutputGuardrails  — validates and cleans Claude's structured output BEFORE it
                    reaches the frontend.  Never raises; degrades gracefully.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException

from utils.medical_limits import get_limit

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────

_MIN_TEXT_LENGTH = 50   # chars; below this the PDF is probably empty / image-only
_MIN_KEYWORD_HITS = 2   # need at least 2 lab keywords to pass the relevance check

_LAB_KEYWORDS = {
    "reference", "range", "result", "test", "lab", "laboratory",
    "mg/dl", "mmol", "iu/l", "g/dl", "u/l", "normal", "abnormal",
    "blood", "serum", "plasma", "urine", "specimen", "patient",
    "panel", "count", "level", "hba1c", "glucose", "cholesterol",
    "hemoglobin", "haemoglobin", "creatinine", "sodium", "potassium",
    "triglyceride", "bilirubin", "albumin", "platelet", "white blood",
}

_ALLOWED_STATUSES = {"normal", "high", "low", "critical"}
_ALLOWED_CATEGORIES = {"blood", "lipid", "liver", "kidney", "metabolic"}


# ── Input guardrails ──────────────────────────────────────────────────────────

class InputGuardrails:

    def validate_pdf_content(self, extracted: dict[str, Any]) -> None:
        """Raise HTTP 422 if the extracted content is unusable."""
        text: str = extracted.get("text", "")

        if len(text.strip()) < _MIN_TEXT_LENGTH:
            raise HTTPException(
                status_code=422,
                detail=(
                    "No readable text found in this PDF. "
                    "If it is a scanned document, please use a text-based PDF. "
                    "OCR support is planned for a future release."
                ),
            )

        text_lower = text.lower()
        hits = sum(1 for kw in _LAB_KEYWORDS if kw in text_lower)
        if hits < _MIN_KEYWORD_HITS:
            logger.warning(
                "PDF may not be a lab report — only %d keyword(s) matched. "
                "Proceeding anyway.",
                hits,
            )
            # Warn only; do not hard-reject. Some valid reports are terse.


# ── Output guardrails ─────────────────────────────────────────────────────────

class OutputGuardrails:

    def validate_and_clean(
        self, data: dict[str, Any]
    ) -> tuple[dict[str, Any], list[str], int]:
        """
        Return (cleaned_data, issues, drop_count).

        issues      — human-readable list of every correction made
        drop_count  — number of result rows dropped entirely
        """
        issues: list[str] = []
        data = self._ensure_structure(data, issues)
        data["latestResults"], dropped = self._clean_results(data["latestResults"], issues)
        data["patientInfo"] = self._clean_patient(data["patientInfo"], issues)
        return data, issues, dropped

    # ------------------------------------------------------------------

    def _ensure_structure(
        self, data: dict[str, Any], issues: list[str]
    ) -> dict[str, Any]:
        if not isinstance(data.get("patientInfo"), dict):
            issues.append("patientInfo was missing — inserted empty record")
            data["patientInfo"] = {"id": "unknown", "name": None, "lastTestDate": None}
        if not isinstance(data.get("latestResults"), list):
            issues.append("latestResults was missing — inserted empty list")
            data["latestResults"] = []
        if not isinstance(data.get("testCategories"), list):
            data["testCategories"] = []
        return data

    def _clean_results(
        self, results: list[dict[str, Any]], issues: list[str]
    ) -> tuple[list[dict[str, Any]], int]:
        clean: list[dict[str, Any]] = []
        dropped = 0
        for r in results:
            r, keep = self._clean_one(r, issues)
            if keep:
                clean.append(r)
            else:
                dropped += 1
        return clean, dropped

    def _clean_one(
        self, r: dict[str, Any], issues: list[str]
    ) -> tuple[dict[str, Any], bool]:
        name = r.get("testName") or "unknown"

        # ── Value must be numeric ──────────────────────────────────────
        value = r.get("value")
        if value is None or not isinstance(value, (int, float)):
            issues.append(f"Dropped '{name}': non-numeric value ({value!r})")
            return r, False

        # ── Biological absolute limits ─────────────────────────────────
        limit = get_limit(name)
        if limit:
            lo, hi = limit
            if not lo <= value <= hi:
                issues.append(
                    f"Dropped '{name}': value {value} outside biological limits "
                    f"[{lo}, {hi}]"
                )
                return r, False

        # ── Status ────────────────────────────────────────────────────
        if r.get("status") not in _ALLOWED_STATUSES:
            corrected = self._derive_status(value, r.get("referenceRange"))
            issues.append(
                f"'{name}': invalid status {r.get('status')!r} → corrected to '{corrected}'"
            )
            r["status"] = corrected

        # ── Status vs reference range consistency ──────────────────────
        ref = r.get("referenceRange") or {}
        rmin, rmax = ref.get("min"), ref.get("max")
        if rmin is not None and rmax is not None:
            if value < rmin and r["status"] == "normal":
                r["status"] = "low"
                issues.append(f"'{name}': corrected status normal→low (value {value} < {rmin})")
            elif value > rmax and r["status"] == "normal":
                r["status"] = "high"
                issues.append(f"'{name}': corrected status normal→high (value {value} > {rmax})")

        # ── Category ──────────────────────────────────────────────────
        if r.get("category") not in _ALLOWED_CATEGORIES:
            r["category"] = "blood"

        # ── Reference range shape ──────────────────────────────────────
        if not isinstance(r.get("referenceRange"), dict):
            r["referenceRange"] = {"min": None, "max": None}
        else:
            r["referenceRange"].setdefault("min", None)
            r["referenceRange"].setdefault("max", None)

        return r, True

    @staticmethod
    def _derive_status(value: float, ref: Any) -> str:
        if isinstance(ref, dict):
            rmin, rmax = ref.get("min"), ref.get("max")
            if rmin is not None and value < rmin:
                return "low"
            if rmax is not None and value > rmax:
                return "high"
        return "normal"

    def _clean_patient(
        self, info: dict[str, Any], issues: list[str]
    ) -> dict[str, Any]:
        age = info.get("age")
        if age is not None and not (0 <= int(age) <= 130):
            issues.append(f"Patient age {age} implausible — cleared")
            info["age"] = None
        return info


# Singletons
input_guardrails = InputGuardrails()
output_guardrails = OutputGuardrails()
