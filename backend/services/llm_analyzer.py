import json
import logging
import re
from typing import Dict, Any

from services.llm_router import build_router, LLMRouter

logger = logging.getLogger(__name__)

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


# Input text budget: large multi-page reports (50+ results) can run well past
# 3000 chars — that was silently dropping everything after roughly page 2.
_MAX_INPUT_CHARS = 12000

# Output budget: a comprehensive report's JSON (patientInfo + dozens of
# results + categories) can exceed 2048 tokens, truncating the JSON mid-
# object. Providers that strictly validate response_format=json_object
# (e.g. Groq) reject the truncated output outright instead of returning it.
_MAX_OUTPUT_TOKENS = 4096


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
        """Return structured lab data extracted from *extracted_content*."""
        try:
            prompt = self._build_prompt(extracted_content)
            raw = self._get_router().generate(prompt, max_tokens=_MAX_OUTPUT_TOKENS)
            return self._parse_response(raw)
        except Exception as exc:
            logger.error("All LLM providers failed during analysis: %s", exc)
            return self._empty_result()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, extracted_content: Dict[str, Any]) -> str:
        text = extracted_content.get("text", "")[:_MAX_INPUT_CHARS]
        tables = extracted_content.get("tables", [])
        tables_str = json.dumps(tables[:5], indent=2) if tables else "No tables detected"
        return _EXTRACTION_PROMPT.format(text=text, tables=tables_str)

    def _parse_response(self, response: str) -> Dict[str, Any]:
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", response).strip()

        result = self._try_parse(cleaned)
        if result:
            return result

        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            result = self._try_parse(match.group())
            if result:
                return result

        logger.warning("Could not parse LLM response as valid medical JSON")
        return self._empty_result()

    def _try_parse(self, text: str) -> Dict[str, Any] | None:
        try:
            parsed = json.loads(text)
            return parsed if self._is_valid(parsed) else None
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _is_valid(data: object) -> bool:
        return isinstance(data, dict) and all(
            k in data for k in ("patientInfo", "latestResults", "testCategories")
        )

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
