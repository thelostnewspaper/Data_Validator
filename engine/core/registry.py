"""
Pack registry — discovers packs, selects the right one via applies_to(),
and orchestrates the layer1 → layer2 → suggest_fixes pipeline.
"""

from __future__ import annotations

import sys
import logging
from typing import Any

from engine.core.models import (
    CheckResult,
    CheckStatus,
    SuggestedFix,
    ValidationResult,
)
from engine.core.rule_pack import RulePack

logger = logging.getLogger(__name__)


class PackRegistry:
    """
    Central registry of validation packs.

    Packs are registered at startup. When a file needs validation, the
    registry iterates registered packs and delegates to the first one
    whose applies_to() returns True.
    """

    def __init__(self) -> None:
        self._packs: list[RulePack] = []

    def register(self, pack: RulePack) -> None:
        """Register a pack. First-registered wins on applies_to() ties."""
        self._packs.append(pack)
        logger.info(f"Registered pack: {pack.id} ({pack.name})")

    def get_packs(self) -> list[dict[str, str]]:
        """Return metadata for all registered packs."""
        return [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
            }
            for p in self._packs
        ]

    def detect_pack(self, file_path: str, content: str) -> RulePack | None:
        """
        Find the first pack that applies to the given file.

        Args:
            file_path: Absolute path to the file.
            content:   Full file content.

        Returns:
            The matching RulePack, or None if no pack applies.
        """
        for pack in self._packs:
            try:
                if pack.applies_to(file_path, content):
                    logger.info(f"Pack '{pack.id}' applies to {file_path}")
                    return pack
            except Exception as e:
                logger.error(f"Error in {pack.id}.applies_to(): {e}")

        logger.info(f"No pack applies to {file_path}")
        return None

    def validate(
        self,
        file_path: str,
        content: str,
        connections: dict[str, Any] | None = None,
        enabled_packs: list[str] | None = None,
    ) -> ValidationResult:
        """
        Full validation pipeline: detect pack → static → live → fixes.

        The two-layer model:
        1. Layer 1 (static_checks): AST-based, no network. Always runs.
        2. Layer 2 (live_checks): Network-dependent. Only runs if:
           - Layer 1 has no FAIL-severity results
           - Connection profiles are provided

        Args:
            file_path:     Absolute path to the file.
            content:       Full file content.
            connections:   Optional dict of connection profiles.
            enabled_packs: Optional list of pack IDs to restrict detection to.

        Returns:
            ValidationResult with checks, fixes, and summary.
        """
        result = ValidationResult(file_path=file_path)

        # Detect the right pack
        pack = self.detect_pack(file_path, content)
        if pack is None:
            return result

        # Filter by enabled packs if specified
        if enabled_packs and pack.id not in enabled_packs:
            logger.info(f"Pack '{pack.id}' not in enabled list, skipping")
            return result

        # --- Layer 1: static checks ---
        try:
            static_results = pack.static_checks(file_path, content)
            result.checks.extend(static_results)
        except Exception as e:
            logger.error(f"Error in {pack.id}.static_checks(): {e}")
            result.checks.append(
                CheckResult(
                    id="ENGINE_ERR",
                    status=CheckStatus.FAIL,
                    category="syntax",
                    message=f"Internal error during static checks: {e}",
                )
            )
            result.compute_summary()
            return result

        # --- Gate: proceed to Layer 2 only if no failures ---
        has_failures = any(
            c.status == CheckStatus.FAIL for c in result.checks
        )

        if not has_failures and connections:
            # --- Layer 2: live checks ---
            try:
                live_results = pack.live_checks(
                    file_path, content, connections
                )
                result.checks.extend(live_results)
            except Exception as e:
                logger.error(f"Error in {pack.id}.live_checks(): {e}")
                result.checks.append(
                    CheckResult(
                        id="ENGINE_ERR",
                        status=CheckStatus.WARN,
                        category="connections",
                        message=f"Live check error: {e}",
                    )
                )

        # --- Generate deterministic fixes ---
        try:
            fixes = pack.suggest_fixes(file_path, content, result.checks)
            result.fixes.extend(fixes)
        except Exception as e:
            logger.error(f"Error in {pack.id}.suggest_fixes(): {e}")

        result.compute_summary()
        return result

    def get_ai_context(
        self,
        file_path: str,
        content: str,
        checks: list[CheckResult],
    ) -> dict[str, Any]:
        """
        Get AI grounding context from the matching pack.

        Args:
            file_path: Absolute path to the file.
            content:   Full file content.
            checks:    Check results to include in context.

        Returns:
            Dict of domain-specific context for the LLM prompt.
        """
        pack = self.detect_pack(file_path, content)
        if pack is None:
            return {}

        try:
            return pack.ai_context(file_path, content, checks)
        except Exception as e:
            logger.error(f"Error in {pack.id}.ai_context(): {e}")
            return {}


# ---------------------------------------------------------------------------
# Singleton registry — packs register here at import time
# ---------------------------------------------------------------------------

_registry = PackRegistry()


def get_registry() -> PackRegistry:
    """Get the global pack registry."""
    return _registry


def register_pack(pack: RulePack) -> None:
    """Register a pack in the global registry."""
    _registry.register(pack)


def register_all_packs() -> None:
    """
    Import and register all built-in packs.

    Each pack module registers itself when imported.
    """
    try:
        from engine.packs.airflow.pack import AirflowUniversalPack
        register_pack(AirflowUniversalPack())
    except ImportError as e:
        logger.warning(f"Failed to import airflow pack: {e}")

    # Future packs:
    # from engine.packs.dbt.pack import DbtPack
    # register_pack(DbtPack())
    # from engine.packs.sql_migration.pack import SqlMigrationPack
    # register_pack(SqlMigrationPack())
    # from engine.packs.cicd.pack import CicdPack
    # register_pack(CicdPack())
    # from engine.packs.k8s.pack import K8sPack
    # register_pack(K8sPack())
    # from engine.packs.streaming.pack import StreamingPack
    # register_pack(StreamingPack())
