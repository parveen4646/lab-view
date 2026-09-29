"""
LLM fallback router.

Tries providers in order; on a rate-limit (429) it moves to the next one.
Auth errors and hard failures bubble up immediately from whichever provider
was attempted.

Default chain (configured via env vars):
  1. Google Gemini free tier  (GOOGLE_API_KEY)
  2. DeepSeek V3              (DEEPSEEK_API_KEY)
  3. Claude Haiku             (ANTHROPIC_API_KEY — uses Anthropic SDK directly)
"""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── Provider base ─────────────────────────────────────────────────────────────

class _Provider:
    name: str

    def complete(self, prompt: str, max_tokens: int = 2048, json_mode: bool = True) -> str:
        raise NotImplementedError


class _OpenAICompatProvider(_Provider):
    """Covers Google Gemini (OpenAI-compat endpoint) and DeepSeek."""

    def __init__(self, name: str, model: str, base_url: str, api_key: str) -> None:
        from openai import OpenAI
        self.name = name
        self._model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def complete(self, prompt: str, max_tokens: int = 2048, json_mode: bool = True) -> str:
        kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.1,
            **kwargs,
        )
        return resp.choices[0].message.content or ""


class _ClaudeProvider(_Provider):
    """Fallback to Anthropic SDK (original implementation)."""

    def __init__(self, model: str, api_key: str) -> None:
        import anthropic
        self.name = "claude"
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, prompt: str, max_tokens: int = 2048, json_mode: bool = True) -> str:
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text


# ── Router ────────────────────────────────────────────────────────────────────

class LLMRouter:
    """
    Try each provider in order.
    Rate-limit (429) → move to next provider.
    Any other error from the *active* provider → raise immediately.
    """

    def __init__(self, providers: list[_Provider]) -> None:
        if not providers:
            raise ValueError("LLMRouter requires at least one provider")
        self._providers = providers

    def complete(self, prompt: str, max_tokens: int = 2048, json_mode: bool = True) -> tuple[str, str]:
        """Returns (text, provider_name)."""
        from openai import RateLimitError as OpenAIRateLimitError

        for i, provider in enumerate(self._providers):
            try:
                text = provider.complete(prompt, max_tokens, json_mode=json_mode)
                if i > 0:
                    logger.info("LLM fallback succeeded via %s", provider.name)
                return text, provider.name
            except OpenAIRateLimitError:
                logger.warning("Rate limited on %s — trying next provider", provider.name)
                if i == len(self._providers) - 1:
                    raise
            except Exception as exc:
                # For Anthropic rate limits (status 429 in their SDK)
                if _is_rate_limit(exc):
                    logger.warning("Rate limited on %s — trying next provider", provider.name)
                    if i == len(self._providers) - 1:
                        raise
                else:
                    raise

        raise RuntimeError("All LLM providers exhausted")  # unreachable

    # Convenience: just the text
    def generate(self, prompt: str, max_tokens: int = 2048, json_mode: bool = True) -> str:
        text, _ = self.complete(prompt, max_tokens, json_mode=json_mode)
        return text


def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg or "rate_limit" in msg


# ── Factory: build router from Config ─────────────────────────────────────────

def build_router(claude_model: Optional[str] = None) -> LLMRouter:
    """
    Build the provider chain from Config.
    Any provider whose API key is absent is skipped silently.
    Chain order: Gemini → DeepSeek → Claude.

    claude_model overrides Config.CLAUDE_EXTRACTION_MODEL for the Claude leg —
    used by the Q&A path to request the (larger) CLAUDE_QA_MODEL instead.
    """
    from config import Config

    providers: list[_Provider] = []

    # 1. Google Gemini (free tier endpoint via AI Studio key)
    if Config.GOOGLE_API_KEY:
        providers.append(
            _OpenAICompatProvider(
                name="gemini-free",
                model=Config.GEMINI_MODEL,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_key=Config.GOOGLE_API_KEY,
            )
        )
        logger.info("LLM chain: added Gemini (%s)", Config.GEMINI_MODEL)

    # 2. DeepSeek V3 (paid, very cheap)
    if Config.DEEPSEEK_API_KEY:
        providers.append(
            _OpenAICompatProvider(
                name="deepseek",
                model=Config.DEEPSEEK_MODEL,
                base_url="https://api.deepseek.com/v1",
                api_key=Config.DEEPSEEK_API_KEY,
            )
        )
        logger.info("LLM chain: added DeepSeek (%s)", Config.DEEPSEEK_MODEL)

    # 3. Claude (original fallback — only if key present)
    if Config.ANTHROPIC_API_KEY:
        model = claude_model or Config.CLAUDE_EXTRACTION_MODEL
        providers.append(_ClaudeProvider(model, Config.ANTHROPIC_API_KEY))
        logger.info("LLM chain: added Claude (%s)", model)

    if not providers:
        raise RuntimeError(
            "No LLM API keys configured. Set at least one of: "
            "GOOGLE_API_KEY, DEEPSEEK_API_KEY, ANTHROPIC_API_KEY"
        )

    return LLMRouter(providers)
