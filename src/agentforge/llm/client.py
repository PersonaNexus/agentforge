"""LLM client abstraction supporting Anthropic and OpenAI providers."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, TypeVar

import anthropic
import openai
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds

# Default models per provider
_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
}


def _detect_provider(api_key: str) -> str:
    """Detect LLM provider from API key prefix."""
    if api_key.startswith("sk-ant-"):
        return "anthropic"
    return "openai"


def _resolve_key_and_provider(
    api_key: str | None = None,
    provider: str | None = None,
) -> tuple[str, str]:
    """Resolve API key and provider from args, env vars, or config.

    Returns (api_key, provider) tuple.
    """
    # 1. Explicit key provided — detect provider from it
    if api_key:
        resolved_provider = provider or _detect_provider(api_key)
        return api_key, resolved_provider

    # 2. Explicit provider — look for matching env var
    if provider and provider != "auto":
        env_var = "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"
        key = os.environ.get(env_var, "")
        if key:
            return key, provider

    # 3. Check env vars (prefer ANTHROPIC_API_KEY for backward compat, then OPENAI)
    for env_var, prov in [
        ("ANTHROPIC_API_KEY", "anthropic"),
        ("OPENAI_API_KEY", "openai"),
    ]:
        key = os.environ.get(env_var, "")
        if key:
            return key, prov

    # 4. Fall back to config file
    try:
        from agentforge.config import load_config

        config = load_config()
        if config.api_key:
            cfg_provider = config.provider
            if cfg_provider == "auto":
                cfg_provider = _detect_provider(config.api_key)
            return config.api_key, cfg_provider
    except Exception:
        pass

    return "", provider or "auto"


class LLMClient:
    """Client for making structured LLM calls via Anthropic or OpenAI."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        provider: str | None = None,
    ):
        resolved_key, resolved_provider = _resolve_key_and_provider(api_key, provider)

        if not resolved_key:
            raise ValueError(
                "No API key found. Set ANTHROPIC_API_KEY or OPENAI_API_KEY, "
                "or run `agentforge init` to configure."
            )

        self.provider = resolved_provider
        self.model = model or _DEFAULT_MODELS.get(self.provider, "claude-sonnet-4-20250514")

        if self.provider == "openai":
            self._openai_client = openai.OpenAI(api_key=resolved_key)
            self._anthropic_client = None
        else:
            self._anthropic_client = anthropic.Anthropic(api_key=resolved_key)
            self._openai_client = None

    def extract_structured(
        self,
        prompt: str,
        output_schema: type[T],
        system: str | None = None,
        max_tokens: int = 4096,
    ) -> T:
        """Make a structured extraction call returning a validated Pydantic model.

        Uses tool/function calling to get reliably structured JSON output.
        Retries on transient errors with exponential backoff.
        """
        if self.provider == "openai":
            return self._extract_openai(prompt, output_schema, system, max_tokens)
        return self._extract_anthropic(prompt, output_schema, system, max_tokens)

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 4096,
    ) -> str:
        """Make a plain text generation call.

        Unlike extract_structured(), this returns raw text without
        tool/function calling.
        """
        if self.provider == "openai":
            return self._generate_openai(prompt, system, max_tokens)
        return self._generate_anthropic(prompt, system, max_tokens)

    def _generate_anthropic(
        self,
        prompt: str,
        system: str | None,
        max_tokens: int,
    ) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        response = self._call_anthropic_with_retry(**kwargs)
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return ""

    def _generate_openai(
        self,
        prompt: str,
        system: str | None,
        max_tokens: int,
    ) -> str:
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }

        response = self._call_openai_with_retry(**kwargs)
        choice = response.choices[0]
        return choice.message.content or ""

    # ------------------------------------------------------------------
    # Anthropic implementation
    # ------------------------------------------------------------------

    def _extract_anthropic(
        self,
        prompt: str,
        output_schema: type[T],
        system: str | None,
        max_tokens: int,
    ) -> T:
        tool_name = output_schema.__name__
        schema = output_schema.model_json_schema()
        _inline_refs(schema)

        tool = {
            "name": tool_name,
            "description": f"Extract structured {tool_name} data from the input.",
            "input_schema": schema,
        }

        messages = [{"role": "user", "content": prompt}]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "tools": [tool],
            "tool_choice": {"type": "tool", "name": tool_name},
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        response = self._call_anthropic_with_retry(**kwargs)

        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                return output_schema.model_validate(block.input)

        raise ValueError(f"No {tool_name} tool use found in response")

    def _call_anthropic_with_retry(self, **kwargs: Any) -> Any:
        """Call the Anthropic API with retry logic for transient errors."""
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                return self._anthropic_client.messages.create(**kwargs)
            except anthropic.RateLimitError as e:
                last_error = e
                delay = _RETRY_BASE_DELAY * (2**attempt)
                logger.warning(
                    "Rate limited (attempt %d/%d), retrying in %.1fs...",
                    attempt + 1,
                    _MAX_RETRIES,
                    delay,
                )
                time.sleep(delay)
            except anthropic.APIConnectionError as e:
                last_error = e
                delay = _RETRY_BASE_DELAY * (2**attempt)
                logger.warning(
                    "Connection error (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1,
                    _MAX_RETRIES,
                    delay,
                    e,
                )
                time.sleep(delay)
            except anthropic.AuthenticationError as e:
                raise ValueError(
                    "Invalid Anthropic API key. Run `agentforge init` to reconfigure."
                ) from e
            except anthropic.APIStatusError as e:
                raise RuntimeError(
                    f"LLM request failed (HTTP {e.status_code}): {e.message}"
                ) from e

        raise RuntimeError(
            f"LLM request failed after {_MAX_RETRIES} retries: {last_error}"
        )

    # ------------------------------------------------------------------
    # OpenAI implementation
    # ------------------------------------------------------------------

    def _extract_openai(
        self,
        prompt: str,
        output_schema: type[T],
        system: str | None,
        max_tokens: int,
    ) -> T:
        tool_name = output_schema.__name__
        schema = output_schema.model_json_schema()
        _inline_refs(schema)

        # OpenAI function calling format
        tool = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": f"Extract structured {tool_name} data from the input.",
                "parameters": schema,
            },
        }

        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "tools": [tool],
            "tool_choice": {"type": "function", "function": {"name": tool_name}},
            "messages": messages,
        }

        response = self._call_openai_with_retry(**kwargs)

        # Parse the function call result
        choice = response.choices[0]
        if choice.message.tool_calls:
            arguments = choice.message.tool_calls[0].function.arguments
            data = json.loads(arguments)
            return output_schema.model_validate(data)

        raise ValueError(f"No {tool_name} function call found in response")

    def _call_openai_with_retry(self, **kwargs: Any) -> Any:
        """Call the OpenAI API with retry logic for transient errors."""
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                return self._openai_client.chat.completions.create(**kwargs)
            except openai.RateLimitError as e:
                last_error = e
                delay = _RETRY_BASE_DELAY * (2**attempt)
                logger.warning(
                    "Rate limited (attempt %d/%d), retrying in %.1fs...",
                    attempt + 1,
                    _MAX_RETRIES,
                    delay,
                )
                time.sleep(delay)
            except openai.APIConnectionError as e:
                last_error = e
                delay = _RETRY_BASE_DELAY * (2**attempt)
                logger.warning(
                    "Connection error (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1,
                    _MAX_RETRIES,
                    delay,
                    e,
                )
                time.sleep(delay)
            except openai.AuthenticationError as e:
                raise ValueError(
                    "Invalid OpenAI API key. Run `agentforge init` to reconfigure."
                ) from e
            except openai.APIStatusError as e:
                raise RuntimeError(
                    f"LLM request failed (HTTP {e.status_code}): {e.message}"
                ) from e

        raise RuntimeError(
            f"LLM request failed after {_MAX_RETRIES} retries: {last_error}"
        )


def _inline_refs(schema: dict[str, Any]) -> None:
    """Inline $ref references from $defs into the schema (in-place).

    Both Anthropic's tool_use and OpenAI's function calling support nested
    objects directly, so we resolve $ref pointers into inline definitions.
    """
    defs = schema.pop("$defs", None) or schema.pop("definitions", None)
    if not defs:
        return

    def _resolve(obj: Any) -> Any:
        if isinstance(obj, dict):
            if "$ref" in obj:
                ref_path = obj["$ref"]  # e.g. "#/$defs/ExtractedSkill"
                ref_name = ref_path.rsplit("/", 1)[-1]
                if ref_name in defs:
                    resolved = defs[ref_name].copy()
                    # Recursively resolve nested refs
                    return _resolve(resolved)
                return obj
            return {k: _resolve(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_resolve(item) for item in obj]
        return obj

    resolved = _resolve(schema)
    schema.clear()
    schema.update(resolved)
