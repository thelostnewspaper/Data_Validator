"""
AI remediator — orchestrates AI-powered fix generation.

Builds a grounded prompt from checks + fixes + schema context,
calls the AI provider, and applies the static-check GATE to ensure
generated code passes ast.parse() + static_checks before being shown.

Phase 4: Full implementation with streaming variants.
"""

from __future__ import annotations

import ast
import logging
from typing import Any, Iterator

from engine.core.models import (
    CheckResult,
    CheckStatus,
    FixImpact,
    RemediationOption,
    CodeChange,
)
from engine.core.fixes import make_unified_diff
from engine.core.redaction import redact_secrets, restore_secrets
from engine.ai.provider import make_llm

logger = logging.getLogger(__name__)

# JSON schema for structured output from Claude
REMEDIATION_SCHEMA = {
    "type": "object",
    "properties": {
        "variants": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "impact": {"type": "string", "enum": ["low", "medium", "high"]},
                    "title": {"type": "string"},
                    "root_cause": {"type": "string"},
                    "fix_explanation": {"type": "string"},
                    "dag_code": {"type": "string"},
                },
                "required": ["impact", "title", "root_cause", "fix_explanation", "dag_code"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["variants"],
    "additionalProperties": False,
}


def remediate(
    file_path: str,
    content: str,
    checks: list[CheckResult],
    fixes_data: list[dict[str, Any]],
    api_key: str,
    provider: str = "claude",
    model: str = "",
) -> Iterator[RemediationOption]:
    """
    Generate AI fix variants for the given checks.

    Yields RemediationOption variants (low/medium/high impact).
    Each variant MUST pass the static-check gate before being yielded
    as non-failed.

    Args:
        file_path:  Path to the file being fixed.
        content:    Original file content.
        checks:     Check results to fix.
        fixes_data: Existing deterministic fixes (for context).
        api_key:    AI provider API key.
        provider:   AI provider name.
        model:      Model name (empty for default).

    Yields:
        RemediationOption for each variant.
    """
    # Redact secrets before sending to the LLM
    redacted_content, redactions = redact_secrets(content)

    # Build the prompt
    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(
        redacted_content, checks, fixes_data, file_path
    )

    # Create the LLM provider
    llm = make_llm(provider=provider, model=model, api_key=api_key)

    try:
        # Generate structured response
        response = llm.generate(
            prompt=user_prompt,
            system=system_prompt,
            schema=REMEDIATION_SCHEMA,
        )

        variants = response.get("variants", [])

        for variant_data in variants:
            impact_str = variant_data.get("impact", "medium")
            try:
                impact = FixImpact(impact_str)
            except ValueError:
                impact = FixImpact.MEDIUM

            dag_code = variant_data.get("dag_code", "")

            # Restore secrets in the generated code
            dag_code = restore_secrets(dag_code, redactions)

            # --- STATIC-CHECK GATE ---
            # The model doesn't get to bypass the static layer
            failed = False
            failure_reason = ""

            # Gate 1: ast.parse must succeed
            try:
                ast.parse(dag_code)
            except SyntaxError as e:
                failed = True
                failure_reason = f"Generated code has syntax error: {e}"
                logger.warning(f"Gate failed (syntax): {failure_reason}")

            # Gate 2: static checks must not introduce new failures
            if not failed:
                from engine.packs.airflow.static_checks import run_all_static_checks
                new_checks = run_all_static_checks(file_path, dag_code)
                new_failures = [
                    c for c in new_checks
                    if c.status == CheckStatus.FAIL and c.id != "AFW001"
                ]
                original_failures = {c.id for c in checks if c.status == CheckStatus.FAIL}
                truly_new = [c for c in new_failures if c.id not in original_failures]

                if truly_new:
                    failed = True
                    failure_reason = (
                        f"Generated code introduces {len(truly_new)} new failure(s): "
                        + ", ".join(c.message for c in truly_new[:3])
                    )
                    logger.warning(f"Gate failed (new failures): {failure_reason}")

            # Build the diff
            diff = make_unified_diff(content, dag_code)

            # Build checks_after for cascade display
            checks_after = []
            if not failed:
                from engine.packs.airflow.static_checks import run_all_static_checks
                after_checks = run_all_static_checks(file_path, dag_code)
                checks_after = [c.to_dict() for c in after_checks]

            yield RemediationOption(
                impact=impact,
                title=variant_data.get("title", f"{impact_str.title()} impact fix"),
                root_cause=variant_data.get("root_cause", ""),
                fix_explanation=variant_data.get("fix_explanation", ""),
                changes=[CodeChange(
                    file_path=file_path,
                    old_content=content,
                    new_content=dag_code,
                    description=variant_data.get("fix_explanation", ""),
                )],
                dag_code=dag_code,
                diff=diff,
                failed=failed,
                failure_reason=failure_reason,
                checks_after=checks_after,
            )

    except Exception as e:
        logger.error(f"AI remediation failed: {e}")
        yield RemediationOption(
            impact=FixImpact.MEDIUM,
            title="AI remediation failed",
            root_cause=str(e),
            fix_explanation="The AI provider returned an error.",
            failed=True,
            failure_reason=str(e),
        )


def _build_system_prompt() -> str:
    """Build the system prompt for AI remediation."""
    return """You are an expert Airflow DAG validator and fixer. Your job is to fix
validation issues in Airflow DAG files.

RULES:
1. You MUST return valid Python code that passes ast.parse().
2. You MUST preserve the original DAG's intent and structure.
3. You MUST NOT add new imports that aren't needed.
4. You MUST NOT change business logic unless the check specifically requires it.
5. You MUST preserve all comments and docstrings.
6. Return 3 variants: low (minimal fix), medium (fix + improve), high (restructure if beneficial).
7. Each variant MUST be a complete, runnable DAG file — not a partial diff.
8. If a placeholder like <REDACTED_...> appears, preserve it exactly as-is.

IMPORTANT: Never execute the DAG. Only fix the static issues identified."""


def _build_user_prompt(
    content: str,
    checks: list[CheckResult],
    fixes_data: list[dict[str, Any]],
    file_path: str,
) -> str:
    """Build the user prompt with check details and context."""
    failed_checks = [c for c in checks if c.status in (CheckStatus.FAIL, CheckStatus.WARN)]

    checks_text = "\n".join(
        f"- [{c.id}] {c.status.value.upper()}: {c.message}"
        + (f"\n  Detail: {c.detail}" if c.detail else "")
        + (f"\n  Line: {c.line}" if c.line else "")
        for c in failed_checks
    )

    existing_fixes = ""
    if fixes_data:
        existing_fixes = "\n\nExisting deterministic fixes (already available, may help you):\n"
        for f in fixes_data:
            existing_fixes += f"- {f.get('description', 'Unknown fix')}\n"

    return f"""Fix the following Airflow DAG file.

FILE: {file_path}

VALIDATION ISSUES:
{checks_text}
{existing_fixes}

DAG CODE:
```python
{content}
```

Generate 3 fix variants (low/medium/high impact). Each variant must include
the COMPLETE fixed DAG code, not just the changed lines."""
