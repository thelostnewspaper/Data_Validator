"""Tests for AI provider routing and execution."""

import sys
from unittest.mock import MagicMock

# Inject mock modules for the AI SDKs
mock_anthropic = MagicMock()
sys.modules["anthropic"] = mock_anthropic

mock_genai = MagicMock()
sys.modules["google.generativeai"] = mock_genai
if "google" in sys.modules:
    sys.modules["google"].generativeai = mock_genai
else:
    mock_google = MagicMock()
    mock_google.generativeai = mock_genai
    sys.modules["google"] = mock_google

from engine.ai.provider import make_llm
from engine.ai.claude import ClaudeProvider
from engine.ai.gemini import GeminiProvider
from engine.core.models import FixImpact


class TestAiProviders:
    def test_routing_claude(self):
        llm = make_llm(provider="claude", api_key="test_key")
        assert isinstance(llm, ClaudeProvider)
        assert llm.model == "claude-opus-4-8"

    def test_routing_gemini(self):
        llm = make_llm(provider="gemini", api_key="test_key")
        assert isinstance(llm, GeminiProvider)
        assert llm.model_name == "gemini-2.5-pro"

    def test_claude_generate(self):
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_block = MagicMock()
        mock_block.text = '{"variants": []}'
        mock_message.content = [mock_block]
        mock_client.messages.create.return_value = mock_message
        mock_anthropic.Anthropic.return_value = mock_client

        provider = ClaudeProvider(api_key="key")
        res = provider.generate(prompt="prompt", system="system", schema={"type": "object"})
        assert res == {"variants": []}

    def test_gemini_generate(self):
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"variants": []}'
        mock_model.generate_content.return_value = mock_response

        provider = GeminiProvider(api_key="key")
        provider.genai.GenerativeModel = MagicMock(return_value=mock_model)
        
        res = provider.generate(prompt="prompt", system="system", schema={"type": "object"})
        assert res == {"variants": []}
