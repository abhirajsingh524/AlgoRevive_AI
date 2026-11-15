"""Configurable LLM Provider Package (Contract Phase 6)."""

from typing import Optional

from app.core.config import settings
from app.engines.optimizer.llm.base import (
    FORBIDDEN_SYMBOLS,
    LLMDisabledError,
    LLMProvider,
    LLMValidationError,
    NullProvider,
    OutputParser,
    PromptBuilder,
    check_forbidden_symbols,
    splice_candidate_function,
)
from app.engines.optimizer.llm.provider import OpenAICompatibleProvider


def get_llm_provider(
    provider_name: Optional[str] = None,
    **kwargs: object,
) -> LLMProvider:
    """Factory retrieving configured LLMProvider.

    Defaults to NullProvider when LLM_PROVIDER=none.
    """
    p_name = (provider_name or settings.LLM_PROVIDER).lower().strip()
    if p_name in ("none", "null", ""):
        return NullProvider()
    elif p_name in ("openai_compatible", "openai", "ollama", "vllm"):
        return OpenAICompatibleProvider(**kwargs)  # type: ignore[arg-type]
    else:
        raise ValueError(f"Unknown LLM provider '{p_name}'. Supported: 'none', 'openai_compatible'")


__all__ = [
    "FORBIDDEN_SYMBOLS",
    "LLMDisabledError",
    "LLMProvider",
    "LLMValidationError",
    "NullProvider",
    "OpenAICompatibleProvider",
    "OutputParser",
    "PromptBuilder",
    "check_forbidden_symbols",
    "get_llm_provider",
    "splice_candidate_function",
]
