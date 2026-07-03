"""
Gemini AI provider — Google Generative AI SDK implementation.

Uses structured outputs via response_schema and response_mime_type.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterator

logger = logging.getLogger(__name__)


class GeminiProvider:
    """
    Google Gemini provider using google-generativeai.
    """

    def __init__(self, api_key: str, model: str = "gemini-2.5-pro") -> None:
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError(
                "The 'google-generativeai' package is required for Gemini AI fixes. "
                "Install it with: pip install google-generativeai"
            )

        genai.configure(api_key=api_key)
        self.model_name = model or "gemini-2.5-pro"
        self.genai = genai

    def generate(
        self,
        prompt: str,
        system: str,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Generate a structured response from Gemini.
        """
        generation_config: dict[str, Any] = {}
        
        if schema:
            # Clean schema for Gemini if needed (Gemini has strict schema parser)
            cleaned_schema = self._clean_schema(schema)
            generation_config = {
                "response_mime_type": "application/json",
                "response_schema": cleaned_schema,
            }

        # Legacy google-generativeai uses system_instruction in GenerativeModel init
        model = self.genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=system,
        )

        response = model.generate_content(
            prompt,
            generation_config=generation_config,
        )

        result_text = response.text

        if schema:
            try:
                # Remove markdown code blocks if the model wrapped JSON
                cleaned_text = result_text.strip()
                if cleaned_text.startswith("```"):
                    # Strip ```json ... ``` wrapper
                    lines = cleaned_text.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    cleaned_text = "\n".join(lines).strip()
                
                return json.loads(cleaned_text)
            except Exception as e:
                logger.error(f"Failed to parse Gemini response as JSON: {e}\nRaw response: {result_text[:500]}")
                return {"error": f"Failed to parse response: {e}", "raw": result_text}

        return {"text": result_text}

    def stream(
        self,
        prompt: str,
        system: str,
        schema: dict[str, Any] | None = None,
    ) -> Iterator[str]:
        """
        Stream a response from Gemini.
        """
        generation_config: dict[str, Any] = {}
        if schema:
            cleaned_schema = self._clean_schema(schema)
            generation_config = {
                "response_mime_type": "application/json",
                "response_schema": cleaned_schema,
            }

        model = self.genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=system,
        )

        response = model.generate_content(
            prompt,
            generation_config=generation_config,
            stream=True,
        )

        for chunk in response:
            if chunk.text:
                yield chunk.text

    def _clean_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        """
        Recursively clean JSON schema for compatibility with the Gemini API.
        
        Gemini schemas do not support certain fields like 'additionalProperties'
        in all versions, or require strict formatting.
        """
        if not isinstance(schema, dict):
            return schema

        cleaned = {}
        for k, v in schema.items():
            if k == "additionalProperties":
                continue  # Omit additionalProperties for safety
            
            if isinstance(v, dict):
                cleaned[k] = self._clean_schema(v)
            elif isinstance(v, list):
                cleaned[k] = [
                    self._clean_schema(item) if isinstance(item, dict) else item 
                    for item in v
                ]
            else:
                cleaned[k] = v
                
        return cleaned
