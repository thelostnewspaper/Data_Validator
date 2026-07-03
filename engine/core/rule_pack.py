"""
RulePack interface — the contract every validation pack implements.

Each pack is a self-contained validator for a specific file type / domain.
The registry selects the right pack via applies_to() and delegates all
validation logic to it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable, Any

from engine.core.models import CheckResult, SuggestedFix


@runtime_checkable
class RulePack(Protocol):
    """
    Protocol for validation rule packs.

    Every pack must implement this interface. The registry calls these methods
    in order: applies_to → static_checks → live_checks → suggest_fixes.

    Properties:
        id:          Unique pack identifier (e.g. "airflow-universal").
        name:        Human-readable display name.
        description: One-line description for the settings UI.
    """

    @property
    def id(self) -> str:
        """Unique pack identifier."""
        ...

    @property
    def name(self) -> str:
        """Human-readable display name."""
        ...

    @property
    def description(self) -> str:
        """One-line description for the settings UI."""
        ...

    def applies_to(self, file_path: str, content: str) -> bool:
        """
        Detect whether this pack should handle the given file.

        Args:
            file_path: Absolute path to the file.
            content:   Full file content as a string.

        Returns:
            True if this pack's validators are relevant for this file.
        """
        ...

    def static_checks(self, file_path: str, content: str) -> list[CheckResult]:
        """
        Layer 1 — static analysis, no network.

        Args:
            file_path: Absolute path to the file.
            content:   Full file content.

        Returns:
            List of check results (pass/warn/fail).
        """
        ...

    def live_checks(
        self,
        file_path: str,
        content: str,
        connections: dict[str, Any],
    ) -> list[CheckResult]:
        """
        Layer 2 — live checks requiring network connections.

        Only called if static_checks had no FAIL-severity results and the
        user has configured connection profiles.

        Args:
            file_path:   Absolute path to the file.
            content:     Full file content.
            connections: Dict of connection profiles keyed by name.

        Returns:
            List of check results from live validation.
        """
        ...

    def suggest_fixes(
        self,
        file_path: str,
        content: str,
        checks: list[CheckResult],
    ) -> list[SuggestedFix]:
        """
        Generate deterministic fix suggestions for the given check results.

        Uses fuzzy matching, pattern detection, and structural analysis —
        NO LLM involved. These fixes are fast, free, and trustworthy.

        Args:
            file_path: Absolute path to the file.
            content:   Full file content.
            checks:    Check results to generate fixes for.

        Returns:
            List of suggested fixes.
        """
        ...

    def ai_context(
        self,
        file_path: str,
        content: str,
        checks: list[CheckResult],
    ) -> dict[str, Any]:
        """
        Build grounding context for the AI remediation prompt.

        Returns a dict of domain-specific context (check details, schema info,
        structural patterns) that the remediator includes in the LLM prompt.

        Args:
            file_path: Absolute path to the file.
            content:   Full file content.
            checks:    Check results to include in context.

        Returns:
            Dict of context data for prompt construction.
        """
        ...
