import json
import logging
import re
from typing import Dict, Any

import anthropic

from config import Config

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


class ClaudeAnalyzer:
    """Analyze extracted PDF content using the Claude API."""

    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        self._model = Config.CLAUDE_EXTRACTION_MODEL

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_medical_data(self, extracted_content: Dict[str, Any]) -> Dict[str, Any]:
        """Return structured lab data extracted from *extracted_content*."""
        try:
            prompt = self._build_prompt(extracted_content)
            raw = self._call_claude(prompt)
            return self._parse_response(raw)
        except anthropic.APIError as exc:
            logger.error("Claude API error during analysis: %s", exc)
            return self._empty_result()
        except Exception as exc:
            logger.error("Unexpected error during analysis: %s", exc)
            return self._empty_result()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, extracted_content: Dict[str, Any]) -> str:
        text = extracted_content.get("text", "")[:3000]
        tables = extracted_content.get("tables", [])
        tables_str = json.dumps(tables[:5], indent=2) if tables else "No tables detected"
        return _EXTRACTION_PROMPT.format(text=text, tables=tables_str)

    def _call_claude(self, prompt: str) -> str:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    def _parse_response(self, response: str) -> Dict[str, Any]:
        # Strip any markdown fences Claude may have added despite instructions
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", response).strip()

        result = self._try_parse(cleaned)
        if result:
            return result

        # Last resort: find the first {...} block in the response
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            result = self._try_parse(match.group())
            if result:
                return result

        logger.warning("Could not parse Claude response as valid medical JSON")
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
