"""
AI provider interface — swappable backend for Claude / Gemini / OpenAI.

Phase 4 stub. Provides the make_llm() factory and LLMProvider protocol.
"""

from __future__ import annotations

from typing import Any, Protocol, Iterator, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for AI providers."""

    def generate(
        self,
        prompt: str,
        system: str,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate a structured response."""
        ...

    def stream(
        self,
        prompt: str,
        system: str,
        schema: dict[str, Any] | None = None,
    ) -> Iterator[str]:
        """Stream a response token by token."""
        ...


def make_llm(
    provider: str = "claude",
    model: str = "",
    api_key: str = "",
) -> LLMProvider:
    """
    Factory for AI providers.

    Args:
        provider: "claude", "gemini", or "openai"
        model:    Model name (empty for provider default)
        api_key:  API key for the provider

    Returns:
        An LLMProvider instance.

    Raises:
        ImportError if the required SDK is not installed.
        ValueError for unknown providers.
    """
    if provider == "claude":
        from engine.ai.claude import ClaudeProvider
        return ClaudeProvider(api_key=api_key, model=model or "claude-opus-4-8")
    elif provider == "gemini":
        from engine.ai.gemini import GeminiProvider
        return GeminiProvider(api_key=api_key, model=model or "gemini-2.5-pro")
    elif provider == "openai":
        raise ImportError(
            "OpenAI provider not yet implemented. Install 'openai' "
            "and implement engine/ai/openai.py"
        )
    else:
        raise ValueError(f"Unknown AI provider: {provider}")
