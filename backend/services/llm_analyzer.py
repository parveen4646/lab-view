import json
import logging
from typing import Dict, Any, List, Optional

import tiktoken
from pydantic import BaseModel

from services.llm_router import build_router, LLMRouter

logger = logging.getLogger(__name__)

_ENCODING = tiktoken.get_encoding("cl100k_base")


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate by actual token count, not a chars-per-token guess — the
    guess is what blew past Groq's free-tier TPM limit (see _MAX_INPUT_TOKENS)."""
    tokens = _ENCODING.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return _ENCODING.decode(tokens[:max_tokens])


# ── Expected extraction shape ───────────────────────────────────────────────
# Passed to instructor as response_model: the provider's structured-output
# mode (or instructor's own validation retry) enforces this directly,
# replacing the old approach of regex-extracting a JSON blob from free text
# and hoping it matched the right shape.

class _ReferenceRange(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None


class _PatientInfo(BaseModel):
    id: str = "unknown"
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    dateOfBirth: Optional[str] = None
    lastTestDate: Optional[str] = None


class _LabResultItem(BaseModel):
    id: str
    testName: str
    value: float
    unit: str
    referenceRange: _ReferenceRange = _ReferenceRange()
    status: str
    date: Optional[str] = None
    category: str


class _TestCategory(BaseModel):
    id: str
    name: str
    description: str
    color: str
    tests: List[str] = []


class _ExtractionResult(BaseModel):
    patientInfo: _PatientInfo
    latestResults: List[_LabResultItem] = []
    testCategories: List[_TestCategory] = []


_EXTRACTION_PROMPT = """\
You are a medical data analyst. Analyze the following medical lab report and extract \
structured information.

TEXT CONTENT:
{text}

TABLE DATA:
{tables}

Respond with ONLY a valid JSON object in this exact format:
{{
  "patientInfo": {{
    "id": "extracted_or_generated_id",
    "name": "Patient Name or null",
    "age": null,
    "gender": null,
    "dateOfBirth": null,
    "lastTestDate": "YYYY-MM-DD"
  }},
  "latestResults": [
    {{
      "id": "unique_id",
      "testName": "Test Name",
      "value": 0.0,
      "unit": "unit",
      "referenceRange": {{"min": 0.0, "max": 0.0}},
      "status": "normal|high|low|critical",
      "date": "YYYY-MM-DD",
      "category": "blood|lipid|liver|kidney|metabolic"
    }}
  ],
  "testCategories": [
    {{
      "id": "category_id",
      "name": "Category Name",
      "description": "Category Description",
      "color": "hsl(var(--chart-primary))",
      "tests": ["test1", "test2"]
    }}
  ]
}}

Rules:
- Extract every lab test result with its value, unit, and reference range
- Determine status from reference ranges: normal, high, low, or critical
- Categorize tests into: blood, lipid, liver, kidney, or metabolic
- Use null for missing patient details; never fabricate numeric values
- Return ONLY valid JSON — no prose, no markdown fences\
"""


# Groq's free tier caps openai/gpt-oss-20b at 8000 tokens/minute, covering
# BOTH the prompt and the reserved output budget in one bucket — confirmed
# via a live 413 ("Requested 12083", limit 8000) against the real API.
# ~500 tokens of fixed prompt/instructions overhead leaves this split:
_MAX_INPUT_TOKENS = 4000
_MAX_OUTPUT_TOKENS = 3000


class ClaudeAnalyzer:
    """
    Analyze extracted PDF content using the smart LLM router.

    Tries providers in order (Gemini → DeepSeek → Claude) and falls back
    automatically on rate-limit errors.  The class name is kept for
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

    def analyze_medical_data(self, extracted_content: Dict[str, Any]) -> Dict[str, Any]:
        """Return structured lab data extracted from *extracted_content*.

        Uses instructor's response_model validation instead of manually
        regex-extracting JSON from free text — a provider returning
        malformed or wrong-shape output triggers instructor's own retry
        (same provider, corrective reprompt) before this falls through to
        the next provider in the chain."""
        try:
            prompt = self._build_prompt(extracted_content)
            result, provider = self._get_router().complete_structured(
                prompt, _ExtractionResult, max_tokens=_MAX_OUTPUT_TOKENS
            )
            logger.info("Extraction succeeded via %s", provider)
            return result.model_dump()
        except Exception as exc:
            logger.error("All LLM providers failed during analysis: %s", exc)
            return self._empty_result()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, extracted_content: Dict[str, Any]) -> str:
        text = _truncate_to_tokens(extracted_content.get("text", ""), _MAX_INPUT_TOKENS)
        tables = extracted_content.get("tables", [])
        tables_str = json.dumps(tables[:5], indent=2) if tables else "No tables detected"
        return _EXTRACTION_PROMPT.format(text=text, tables=tables_str)

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
