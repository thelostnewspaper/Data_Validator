"""
Claude AI provider — Anthropic SDK implementation.

Uses structured outputs via output_config.format with JSON schema,
adaptive thinking, and streaming support.

Phase 4: Full implementation. Requires 'anthropic' package.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterator

logger = logging.getLogger(__name__)


class ClaudeProvider:
    """
    Anthropic Claude provider.

    Supports:
    - Structured output via output_config.format (JSON schema)
    - Adaptive thinking (thinking: {type: "adaptive"})
    - Streaming via messages.stream()
    """

    def __init__(self, api_key: str, model: str = "claude-opus-4-8"):
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "The 'anthropic' package is required for Claude AI fixes. "
                "Install it with: pip install anthropic"
            )

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def generate(
        self,
        prompt: str,
        system: str,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Generate a structured response from Claude.

        Uses output_config.format for guaranteed JSON schema conformance.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 16384,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
            "thinking": {"type": "adaptive"},
        }

        # Add structured output schema if provided
        if schema:
            kwargs["output_config"] = {
                "format": {
                    "type": "json_schema",
                    "schema": schema,
                }
            }

        response = self.client.messages.create(**kwargs)

        # Extract the text content
        result_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                result_text = block.text
                break

        # Parse as JSON if schema was provided
        if schema:
            try:
                return json.loads(result_text)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse Claude response as JSON: {result_text[:200]}")
                return {"error": "Failed to parse response", "raw": result_text}

        return {"text": result_text}

    def stream(
        self,
        prompt: str,
        system: str,
        schema: dict[str, Any] | None = None,
    ) -> Iterator[str]:
        """
        Stream a response from Claude token by token.

        Uses messages.stream() for real-time output.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 16384,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
            "thinking": {"type": "adaptive"},
        }

        if schema:
            kwargs["output_config"] = {
                "format": {
                    "type": "json_schema",
                    "schema": schema,
                }
            }

        with self.client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield text
