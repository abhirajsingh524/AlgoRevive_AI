"""OpenAI-compatible LLM Provider implementation using httpx.

Works with OpenAI, Ollama (/v1), and vLLM.
Configured via:
- LLM_BASE_URL
- LLM_API_KEY
- LLM_MODEL
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

import httpx

from app.core.config import settings
from app.engines.optimizer.llm.base import (
    LLMProvider,
    LLMValidationError,
    OutputParser,
    PromptBuilder,
    check_forbidden_symbols,
    splice_candidate_function,
)
from app.engines.optimizer.templates.base import (
    TemplateResult,
    find_target_function_cst,
    run_shared_guards,
)
import libcst as cst

logger = logging.getLogger("optimizer.llm.provider")


class OpenAICompatibleProvider(LLMProvider):
    """LLM Provider targeting OpenAI-compatible /chat/completions endpoints."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_s: float = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.base_url = (base_url or settings.LLM_BASE_URL).rstrip("/")
        self.api_key = api_key or settings.LLM_API_KEY
        self.model = model or settings.LLM_MODEL
        self.timeout_s = timeout_s
        self.transport = transport

    def _call_api(self, messages: list[dict[str, str]]) -> str:
        """Call LLM API with request timeout and retry limit of 1."""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
        }

        last_err: Optional[Exception] = None
        for attempt in range(2):  # initial attempt + 1 retry
            try:
                with httpx.Client(timeout=self.timeout_s, transport=self.transport) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    choices = data.get("choices", [])
                    if not choices:
                        raise LLMValidationError("LLM API returned response with empty choices")
                    content = choices[0].get("message", {}).get("content", "")
                    if not content:
                        raise LLMValidationError("LLM API returned empty message content")
                    return content
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as e:
                last_err = e
                logger.warning(f"LLM API request attempt {attempt + 1} failed: {e}")
                if attempt == 1:
                    break

        raise RuntimeError(f"LLM API request failed after retry: {last_err}")

    def generate(
        self,
        source: str,
        function_name: str,
        function_range: Tuple[int, int],
        evidence: Dict[str, Any],
        recommendation: Dict[str, Any],
    ) -> TemplateResult:
        """Generate candidate function using LLM synthesis, strictly guarded."""
        # 1. Extract target function source
        try:
            mod_cst = cst.parse_module(source)
        except Exception as e:
            raise LLMValidationError(f"Original source failed CST parsing: {e}")

        fn_cst, _ = find_target_function_cst(
            mod_cst, function_name=function_name, function_range=function_range
        )
        if not fn_cst:
            raise LLMValidationError(f"Target function '{function_name}' not found in source")

        fn_source = cst.Module(body=[fn_cst]).code

        # 2. Build minimal prompt
        messages = PromptBuilder.build(
            function_source=fn_source,
            evidence=evidence,
            recommendation=recommendation,
        )

        # 3. Call LLM
        raw_output = self._call_api(messages)

        # 4. Strictly parse output: exactly one function, allowed imports
        fn_code, new_imports = OutputParser.parse(raw_output)

        # 5. Check forbidden symbols in candidate function
        import ast
        fn_ast = ast.parse(fn_code)
        forbidden_err = check_forbidden_symbols(fn_ast)
        if forbidden_err:
            raise LLMValidationError(forbidden_err)

        # 6. Splice candidate function back into original source
        candidate_source = splice_candidate_function(
            original_source=source,
            target_function_name=function_name,
            target_function_code=fn_code,
            new_imports=new_imports,
        )

        # 7. Run shared candidate guards
        guard = run_shared_guards(
            original_source=source,
            candidate_source=candidate_source,
            target_function_name=function_name,
        )
        if not guard.valid:
            raise LLMValidationError(f"LLM candidate failed safety guard: {guard.error}")

        rationale = (
            f"LLM candidate synthesized using model '{self.model}' targeting recommendation "
            f"'{recommendation.get('recommended_algorithm')}'."
        )
        safety_notes = (
            f"Synthesized by LLM ({self.model}). Passed all static security guards, AST signature checks, "
            f"and import allowlist validation. Full sandbox validation required."
        )

        return TemplateResult(
            candidate_source=candidate_source,
            rationale=rationale,
            safety_notes=safety_notes,
            changed_lines=guard.changed_lines,
            patch=guard.patch,
        )
