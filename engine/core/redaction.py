"""
Secret redaction — scrub sensitive data before sending to the LLM.

DAGs and their SQL often embed connection strings, tokens, and passwords.
This module provides regex-based detection and reversible redaction so
secrets never reach the AI provider.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence


@dataclass
class Redaction:
    """A single redacted secret with its placeholder and original value."""
    placeholder: str
    original: str
    pattern_name: str
    start: int
    end: int


# ---------------------------------------------------------------------------
# Patterns that detect secrets in code / SQL / config
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Generic password assignments (Python / SQL / config)
    (
        "password",
        re.compile(
            r"""(?i)(?:password|passwd|pwd|secret|token|api[_-]?key|auth[_-]?token)"""
            r"""\s*[=:]\s*['"]([^'"]{4,})['"]""",
        ),
    ),
    # Connection strings (jdbc, mysql, postgres, etc.)
    (
        "connection_string",
        re.compile(
            r"""(?:jdbc:|mysql://|postgres(?:ql)?://|mssql://|mongodb://|redis://|amqp://)"""
            r"""[^\s'"\)]+""",
        ),
    ),
    # AWS access keys
    (
        "aws_key",
        re.compile(r"""(?:AKIA|ASIA)[A-Z0-9]{16}"""),
    ),
    # AWS secret keys (40 chars, base64-like)
    (
        "aws_secret",
        re.compile(
            r"""(?i)(?:aws_secret_access_key|secret_key)\s*[=:]\s*['"]?([A-Za-z0-9/+=]{40})['"]?""",
        ),
    ),
    # GCP service account JSON key snippets
    (
        "gcp_key",
        re.compile(
            r"""(?:"private_key"\s*:\s*"-----BEGIN [A-Z ]+ KEY-----)""",
        ),
    ),
    # Bearer / Basic auth headers
    (
        "auth_header",
        re.compile(
            r"""(?i)(?:Authorization|Bearer|Basic)\s*[=:]\s*['"]?([A-Za-z0-9._\-/+=]{20,})['"]?""",
        ),
    ),
    # Generic API keys (long alphanumeric strings assigned to key-like vars)
    (
        "api_key",
        re.compile(
            r"""(?i)(?:api[_-]?key|access[_-]?key|secret[_-]?key)\s*[=:]\s*['"]([A-Za-z0-9._\-]{20,})['"]""",
        ),
    ),
    # IP addresses with ports (potential internal endpoints)
    (
        "endpoint",
        re.compile(
            r"""\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b""",
        ),
    ),
]

_PLACEHOLDER_COUNTER = 0


def _next_placeholder(pattern_name: str) -> str:
    """Generate a unique placeholder string."""
    global _PLACEHOLDER_COUNTER
    _PLACEHOLDER_COUNTER += 1
    return f"<REDACTED_{pattern_name.upper()}_{_PLACEHOLDER_COUNTER}>"


def redact_secrets(text: str) -> tuple[str, list[Redaction]]:
    """
    Scan text for secrets and replace them with placeholders.

    Args:
        text: The text to scan (DAG code, SQL, config).

    Returns:
        Tuple of (redacted_text, list_of_redactions).
        The redactions list can be passed to restore_secrets() to reverse.
    """
    global _PLACEHOLDER_COUNTER
    _PLACEHOLDER_COUNTER = 0

    redactions: list[Redaction] = []
    result = text

    for pattern_name, pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(result):
            # Use the first captured group if it exists, otherwise the full match
            if match.lastindex and match.lastindex >= 1:
                secret = match.group(1)
                # Find the secret within the full match to get accurate positions
                secret_start = match.start() + match.group(0).index(secret)
                secret_end = secret_start + len(secret)
            else:
                secret = match.group(0)
                secret_start = match.start()
                secret_end = match.end()

            placeholder = _next_placeholder(pattern_name)

            redaction = Redaction(
                placeholder=placeholder,
                original=secret,
                pattern_name=pattern_name,
                start=secret_start,
                end=secret_end,
            )
            redactions.append(redaction)

    # Apply redactions in reverse order to preserve positions
    for redaction in sorted(redactions, key=lambda r: r.start, reverse=True):
        result = (
            result[:redaction.start]
            + redaction.placeholder
            + result[redaction.end:]
        )

    return result, redactions


def restore_secrets(
    text: str,
    redactions: Sequence[Redaction],
) -> str:
    """
    Restore redacted secrets in the text.

    Used after the LLM generates a fix — we put the real secrets back
    so the generated code is valid.

    Args:
        text:       Text with placeholders.
        redactions: List of redactions from redact_secrets().

    Returns:
        Text with placeholders replaced by original secrets.
    """
    result = text
    for redaction in redactions:
        result = result.replace(redaction.placeholder, redaction.original)
    return result
