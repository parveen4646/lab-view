"""
LLM fallback router.

Tries providers in order; any failure (rate limit, bad auth, deprecated
model, billing) moves to the next one. Only raises once every provider in
the chain has failed.

Default chain (configured via env vars):
  1. Groq free tier           (GROQ_API_KEY)
  2. Google Gemini free tier  (GOOGLE_API_KEY)
  3. DeepSeek V3              (DEEPSEEK_API_KEY)
  4. Claude Haiku             (ANTHROPIC_API_KEY — uses Anthropic SDK directly)
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ── Provider base ─────────────────────────────────────────────────────────────

class _Provider:
    name: str

    def complete(self, prompt: str, max_tokens: int = 2048, json_mode: bool = True) -> str:
        raise NotImplementedError

    def complete_structured(self, prompt: str, response_model: type[BaseModel], max_tokens: int = 2048) -> BaseModel:
        raise NotImplementedError


class _OpenAICompatProvider(_Provider):
    """Covers Groq, Google Gemini (OpenAI-compat endpoint), and DeepSeek."""

    def __init__(self, name: str, model: str, base_url: str, api_key: str) -> None:
        import instructor
        from openai import OpenAI

        self.name = name
        self._model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        # JSON mode (not TOOLS) — matches what we've verified these
        # OpenAI-compatible endpoints actually support reliably.
        self._structured_client = instructor.from_openai(self._client, mode=instructor.Mode.JSON)

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

    def complete_structured(self, prompt: str, response_model: type[BaseModel], max_tokens: int = 2048) -> BaseModel:
        return self._structured_client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.1,
            response_model=response_model,
            max_retries=2,
        )


class _ClaudeProvider(_Provider):
    """Fallback to Anthropic SDK (original implementation)."""

    def __init__(self, model: str, api_key: str) -> None:
        import anthropic
        import instructor

        self.name = "claude"
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key)
        self._structured_client = instructor.from_anthropic(self._client)

    def complete(self, prompt: str, max_tokens: int = 2048, json_mode: bool = True) -> str:
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text

    def complete_structured(self, prompt: str, response_model: type[BaseModel], max_tokens: int = 2048) -> BaseModel:
        return self._structured_client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            response_model=response_model,
            max_retries=2,
        )


# ── Router ────────────────────────────────────────────────────────────────────

class LLMRouter:
    """
    Try each provider in order. Any failure — rate limit, bad auth,
    deprecated model, billing, failed structured-output validation —
    falls through to the next provider; only raises once every provider
    in the chain has failed.
    """

    def __init__(self, providers: list[_Provider]) -> None:
        if not providers:
            raise ValueError("LLMRouter requires at least one provider")
        self._providers = providers

    def _try_each(self, call: Callable[[_Provider], Any]) -> tuple[Any, str]:
        last_exc: Exception | None = None
        for i, provider in enumerate(self._providers):
            try:
                result = call(provider)
                if i > 0:
                    logger.info("LLM fallback succeeded via %s", provider.name)
                return result, provider.name
            except Exception as exc:
                logger.warning("%s failed (%s) — trying next provider", provider.name, exc)
                last_exc = exc

        raise last_exc or RuntimeError("All LLM providers exhausted")

    def complete(self, prompt: str, max_tokens: int = 2048, json_mode: bool = True) -> tuple[str, str]:
        """Returns (text, provider_name)."""
        return self._try_each(lambda p: p.complete(prompt, max_tokens, json_mode=json_mode))

    def complete_structured(
        self, prompt: str, response_model: type[BaseModel], max_tokens: int = 2048
    ) -> tuple[BaseModel, str]:
        """Returns (validated_model_instance, provider_name). Each provider
        gets its own internal retries (via instructor) before this falls
        through to the next provider in the chain."""
        return self._try_each(lambda p: p.complete_structured(prompt, response_model, max_tokens))

    # Convenience: just the text
    def generate(self, prompt: str, max_tokens: int = 2048, json_mode: bool = True) -> str:
        text, _ = self.complete(prompt, max_tokens, json_mode=json_mode)
        return text


# ── Factory: build router from Config ─────────────────────────────────────────

def build_router(claude_model: Optional[str] = None) -> LLMRouter:
    """
    Build the provider chain from Config.
    Any provider whose API key is absent is skipped silently.
    Chain order: Groq → Gemini → DeepSeek → Claude.

    claude_model overrides Config.CLAUDE_EXTRACTION_MODEL for the Claude leg —
    used by the Q&A path to request the (larger) CLAUDE_QA_MODEL instead.
    """
    from config import Config

    providers: list[_Provider] = []

    # 1. Groq (free tier, OpenAI-compatible, fast)
    if Config.GROQ_API_KEY:
        providers.append(
            _OpenAICompatProvider(
                name="groq",
                model=Config.GROQ_MODEL,
                base_url="https://api.groq.com/openai/v1",
                api_key=Config.GROQ_API_KEY,
            )
        )
        logger.info("LLM chain: added Groq (%s)", Config.GROQ_MODEL)

    # 2. Google Gemini (free tier endpoint via AI Studio key)
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

    # 3. DeepSeek V3 (paid, very cheap)
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

    # 4. Claude (original fallback — only if key present)
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
