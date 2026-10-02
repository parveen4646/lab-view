import json
import logging
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

import tiktoken
from pydantic import BaseModel

from services.llm_router import build_router, LLMRouter
from services.population_stats import CANONICAL_TEST_NAMES, resolve_canonical_name
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
    # Deliberately Optional[str], NOT a Literal/Enum restricted to
    # CANONICAL_TEST_NAMES: instructor retries the ENTIRE structured-output
    # call on any validation failure, and a single bad enum value must never
    # be able to blow up a whole extraction's rate-limit budget via a retry
    # (see _MAX_INPUT_TOKENS/_MAX_OUTPUT_TOKENS — Groq free tier, 8000 TPM).
    # Validated against the known vocabulary in _expand() instead of at the
    # schema level.
    canonicalName: Optional[str] = None


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
- Use null for missing patient details; never fabricate numeric values
- For canonicalName: if a test's name clearly matches one of these common biomarker \
names: {canonical_names}, then set canonicalName to that exact name (verbatim, \
lowercase, copied from this list). Otherwise set canonicalName to null. Never invent \
a name that is not in this list\
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
# tokens. Fixed prompt/instructions overhead was ~350 tokens.
#
# Adding canonicalName (for cross-report test-name grouping) cost tokens in
# two places, measured with _ENCODING.encode(...) directly:
#   - the new prompt rule + injected ", ".join(CANONICAL_TEST_NAMES) vocab
#     string (73 tokens for the current 24-name list) together add ~130
#     tokens to the fixed prompt text (54 → 184 tokens for the rules block);
#   - instructor (Mode.JSON) also injects the _SlimExtraction response_model
#     schema into the request; the `instructor` package isn't installed in
#     this dev venv so its exact wrapper text couldn't be inspected, but
#     comparing the full nested schema's own JSON before/after canonicalName
#     (json.dumps(_SlimExtraction.model_json_schema())) gives +29 tokens
#     compact / +48 tokens pretty-printed (indent=2) — call it ~50 tokens,
#     taking the conservative (larger) figure;
#   - output side: one extra `"canonicalName": "<name>"` key costs ~8 tokens
#     per result (43 → 51 tokens for a representative result object), so
#     per-result output cost is now ~71 tokens, not ~63 — output headroom
#     within the unchanged 4400-token reservation drops from ~70 results to
#     ~62 results, still comfortably above the ~56-result reference report.
#
# Total added fixed overhead: ~130 + 50 = ~180 tokens (350 → ~530). To keep
# input + overhead + output comfortably under 8000 with the original
# ~250-token safety margin intact, _MAX_INPUT_TOKENS (not the output
# budget — shrinking that caused real truncation bugs earlier) is lowered
# from 3000 to 2800:
# 2800 + 530 + 4400 = 7730, leaving a ~270-token safety margin even in a
# cold rate-limit window — at least as large as the original ~250.
_MAX_INPUT_TOKENS = 2800
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
        prompt = _EXTRACTION_PROMPT.format(
            text=text, tables=tables_str, canonical_names=", ".join(CANONICAL_TEST_NAMES)
        )
        return prompt, input_truncated

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
                "canonicalName": ClaudeAnalyzer._resolve_canonical(r),
            }
            for i, r in enumerate(slim.latestResults)
        ]
        return {
            "patientInfo": {"id": "unknown", **slim.patientInfo.model_dump()},
            "latestResults": results,
            "testCategories": [],
        }

    @staticmethod
    def _resolve_canonical(r: "_SlimResult") -> Optional[str]:
        """Canonical key precedence: deterministic resolver first (trusted),
        then the LLM's own guess — but only if it's actually in the known
        vocabulary, since the model can still hallucinate outside the list
        despite prompt instructions (canonicalName is Optional[str], not an
        enum, precisely so a bad value here never fails schema validation)."""
        deterministic = resolve_canonical_name(r.testName)
        if deterministic is not None:
            return deterministic
        if r.canonicalName in CANONICAL_TEST_NAMES:
            return r.canonicalName
        return None

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
