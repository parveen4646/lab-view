import json
import logging
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

import tiktoken
from pydantic import BaseModel

from services.llm_router import build_router, LLMRouter
from utils.medical_limits import derive_status

logger = logging.getLogger(__name__)

_ENCODING = tiktoken.get_encoding("cl100k_base")


def _truncate_to_tokens(text: str, max_tokens: int) -> tuple[str, bool]:
    """Truncate by actual token count, not a chars-per-token guess — the
    guess is what blew past Groq's free-tier TPM limit (see _MAX_INPUT_TOKENS).
    Returns (text, was_truncated)."""
    tokens = _ENCODING.encode(text)
    if len(tokens) <= max_tokens:
        return text, False
    return _ENCODING.decode(tokens[:max_tokens]), True


# ── LLM-facing extraction shape ─────────────────────────────────────────────
# Deliberately slim: id/status/date are cheap to compute in code (status is
# then re-derived against the reference range by output guardrails anyway),
# so leaving them out of what the model has to generate roughly halves the
# per-result token cost — the actual bottleneck against Groq's free-tier
# 8000 TPM cap, confirmed by watching a real extraction get cut off mid-list
# at the old verbose schema's token budget.

class _PatientInfo(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    dateOfBirth: Optional[str] = None
    lastTestDate: Optional[str] = None


class _SlimResult(BaseModel):
    testName: str
    value: float
    unit: str
    min: Optional[float] = None
    max: Optional[float] = None
    category: str


class _SlimExtraction(BaseModel):
    patientInfo: _PatientInfo
    latestResults: List[_SlimResult] = []


_EXTRACTION_PROMPT = """\
You are a medical data analyst. Analyze the following medical lab report and extract \
structured information as JSON: the patient's info and every lab test result (name, \
value, unit, reference range, category).

TEXT CONTENT:
{text}

TABLE DATA:
{tables}

Rules:
- Extract every lab test result with its value, unit, and reference range (min/max)
- Categorize each test into one of: blood, lipid, liver, kidney, metabolic
- Use null for missing patient details; never fabricate numeric values\
"""


@dataclass
class AnalysisResult:
    data: Dict[str, Any]
    provider: str
    input_truncated: bool


# Groq's free tier caps this account at 8000 tokens/minute (confirmed via
# the x-ratelimit-limit-tokens response header), covering BOTH the prompt
# and the reserved output budget together. Measured real cost: ~63 output
# tokens/result (patientInfo + simplified per-result fields, no
# testCategories) — a comprehensive ~56-result report needs ~3650 output
# tokens. Fixed prompt/instructions overhead is ~350 tokens, so
# input + overhead + output must stay under 8000:
# 3000 + 350 + 4400 = 7750, leaving a ~250-token safety margin even in a
# cold rate-limit window, with output sized for ~70 results of headroom.
_MAX_INPUT_TOKENS = 3000
_MAX_OUTPUT_TOKENS = 4400


class ClaudeAnalyzer:
    """
    Analyze extracted PDF content using the smart LLM router.

    Tries providers in order (Groq → Gemini → DeepSeek → Claude) and falls
    back automatically on any failure. The class name is kept for
    backwards-compatibility with existing imports in app.py.
    """

    def __init__(self) -> None:
        self._router: LLMRouter | None = None

    def _get_router(self) -> LLMRouter:
        if self._router is None:
            self._router = build_router()
        return self._router

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_medical_data(self, extracted_content: Dict[str, Any]) -> AnalysisResult:
        """Return structured lab data extracted from *extracted_content*.

        Uses instructor's response_model validation instead of manually
        regex-extracting JSON from free text — a provider returning
        malformed or wrong-shape output triggers instructor's own retry
        (same provider, corrective reprompt) before this falls through to
        the next provider in the chain."""
        try:
            prompt, input_truncated = self._build_prompt(extracted_content)
            slim, provider = self._get_router().complete_structured(
                prompt, _SlimExtraction, max_tokens=_MAX_OUTPUT_TOKENS
            )
            logger.info("Extraction succeeded via %s", provider)
            return AnalysisResult(
                data=self._expand(slim), provider=provider, input_truncated=input_truncated
            )
        except Exception as exc:
            logger.error("All LLM providers failed during analysis: %s", exc)
            return AnalysisResult(data=self._empty_result(), provider="none", input_truncated=False)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, extracted_content: Dict[str, Any]) -> tuple[str, bool]:
        text, input_truncated = _truncate_to_tokens(extracted_content.get("text", ""), _MAX_INPUT_TOKENS)
        tables = extracted_content.get("tables", [])
        tables_str = json.dumps(tables[:5], indent=2) if tables else "No tables detected"
        return _EXTRACTION_PROMPT.format(text=text, tables=tables_str), input_truncated

    @staticmethod
    def _expand(slim: _SlimExtraction) -> Dict[str, Any]:
        """Fill in the fields the model wasn't asked to generate — id and
        date are cheap to assign here; status must be computed (not just
        defaulted to "normal"), since a one-sided reference range like
        HDL "> 40" is never corrected by output guardrails otherwise —
        guardrails' range-consistency check only fires when a status is
        already invalid, and only overrides when BOTH min and max are
        present. testCategories is left for data_formatter, which already
        falls back to its fixed default category list on an empty one —
        no need for the model to regenerate that duplicated metadata."""
        last_date = slim.patientInfo.lastTestDate
        results = [
            {
                "id": f"result-{i + 1}",
                "testName": r.testName,
                "value": r.value,
                "unit": r.unit,
                "referenceRange": {"min": r.min, "max": r.max},
                "status": derive_status(r.value, r.min, r.max),
                "date": last_date,
                "category": r.category,
            }
            for i, r in enumerate(slim.latestResults)
        ]
        return {
            "patientInfo": {"id": "unknown", **slim.patientInfo.model_dump()},
            "latestResults": results,
            "testCategories": [],
        }

    @staticmethod
    def _empty_result() -> Dict[str, Any]:
        return {
            "patientInfo": {
                "id": "unknown",
                "name": None,
                "age": None,
                "gender": None,
                "dateOfBirth": None,
                "lastTestDate": None,
            },
            "latestResults": [],
            "testCategories": [],
        }
