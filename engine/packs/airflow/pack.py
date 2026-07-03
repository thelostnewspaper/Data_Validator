"""
Airflow Universal Pack — the flagship validation pack.

Validates Airflow DAG files using static analysis (Layer 1) and optional
live connections (Layer 2). This is the seed pack that all other packs
are modeled after.
"""

from __future__ import annotations

import re
from typing import Any

from engine.core.models import CheckResult, CheckStatus, SuggestedFix
from engine.core.fixes import (
    fuzzy_match_column,
    make_unified_diff,
    apply_column_rename,
    apply_column_removal,
)
from engine.packs.airflow.parser import (
    parse_dag_file,
    extract_columns_from_sql,
)
from engine.packs.airflow.static_checks import run_all_static_checks
from engine.packs.airflow.live_checks import run_all_live_checks


class AirflowUniversalPack:
    """
    Airflow Universal validation pack.

    Detects Airflow DAG files and runs 13 static checks + live checks
    (when connections are configured). Generates deterministic fix
    suggestions using fuzzy matching and pattern detection.
    """

    @property
    def id(self) -> str:
        return "airflow-universal"

    @property
    def name(self) -> str:
        return "Airflow Universal"

    @property
    def description(self) -> str:
        return (
            "Validates Airflow DAG files — syntax, structure, task integrity, "
            "SQL column checks, dependency cycles, and best practices."
        )

    def applies_to(self, file_path: str, content: str) -> bool:
        """
        Detect Airflow DAG files by looking for airflow imports.

        A file is considered an Airflow DAG if it contains:
        - 'from airflow' or 'import airflow'
        """
        return bool(
            re.search(r'(?:from\s+airflow|import\s+airflow)', content)
        )

    def static_checks(self, file_path: str, content: str) -> list[CheckResult]:
        """Run all Layer 1 static checks."""
        return run_all_static_checks(file_path, content)

    def live_checks(
        self,
        file_path: str,
        content: str,
        connections: dict[str, Any],
    ) -> list[CheckResult]:
        """Run all Layer 2 live checks."""
        return run_all_live_checks(file_path, content, connections)

    def suggest_fixes(
        self,
        file_path: str,
        content: str,
        checks: list[CheckResult],
    ) -> list[SuggestedFix]:
        """
        Generate deterministic fix suggestions.

        Handles:
        - Column renames via fuzzy matching (>= 0.80 confidence)
        - Duplicate column removal
        - Variable typo corrections
        - schedule_interval → schedule rename
        - Missing catchup=False insertion
        """
        fixes: list[SuggestedFix] = []

        for check in checks:
            if check.status == CheckStatus.PASS:
                continue

            # AFW002 — Variable typo corrections
            if check.id == "AFW002" and "did you mean" in check.message:
                fix = self._fix_variable_typo(content, check)
                if fix:
                    fixes.append(fix)

            # AFW005 — Duplicate task_id (can't auto-fix, but suggest)
            # AFW007 — Duplicate column removal
            elif check.id == "AFW007" and "Duplicate column" in check.message:
                fix = self._fix_duplicate_column(content, check)
                if fix:
                    fixes.append(fix)

            # AFW009 — schedule_interval → schedule
            elif check.id == "AFW009":
                fix = self._fix_schedule_deprecation(content, check)
                if fix:
                    fixes.append(fix)

            # AFW011 — Missing catchup=False
            elif check.id == "AFW011":
                fix = self._fix_missing_catchup(content, check)
                if fix:
                    fixes.append(fix)

            # AFW_LIVE_003 — Column name typo
            elif check.id == "AFW_LIVE_003" and "Did you mean" in check.message:
                fix = self._fix_column_typo(content, check)
                if fix:
                    fixes.append(fix)

        return fixes

    def ai_context(
        self,
        file_path: str,
        content: str,
        checks: list[CheckResult],
    ) -> dict[str, Any]:
        """
        Build grounding context for AI remediation.

        Returns structured information about the DAG that helps the LLM
        understand the file and generate accurate fixes.
        """
        dag_info = parse_dag_file(content)

        # Collect all SQL and extracted tables/columns
        sql_info: list[dict[str, Any]] = []
        for frag in dag_info.sql_fragments:
            columns = extract_columns_from_sql(frag.sql)
            sql_info.append({
                "task_id": frag.task_id,
                "operator": frag.operator,
                "sql": frag.sql[:500],  # Truncate very long SQL
                "columns": [c[0] for c in columns],
            })

        return {
            "file_type": "airflow_dag",
            "dag_id": dag_info.dag_id,
            "task_count": len(dag_info.tasks),
            "tasks": [
                {"task_id": t.task_id, "operator": t.operator_class, "line": t.line}
                for t in dag_info.tasks
            ],
            "dependencies": [
                {"upstream": d.upstream, "downstream": d.downstream}
                for d in dag_info.dependencies
            ],
            "sql_fragments": sql_info,
            "imports": [
                {"module": i.module, "names": i.names}
                for i in dag_info.imports
            ],
            "default_args": dag_info.default_args,
            "has_start_date": dag_info.has_start_date,
            "has_catchup": dag_info.has_catchup,
            "schedule_param": dag_info.schedule_param,
            "failed_checks": [
                {"id": c.id, "message": c.message, "line": c.line, "detail": c.detail}
                for c in checks
                if c.status in (CheckStatus.FAIL, CheckStatus.WARN)
            ],
        }

    # -------------------------------------------------------------------
    # Fix generators
    # -------------------------------------------------------------------

    def _fix_variable_typo(
        self, content: str, check: CheckResult
    ) -> SuggestedFix | None:
        """Generate a fix for a variable typo (AFW002)."""
        # Extract typo and correct name from the message
        match = re.search(r"'(\w+)'.*'(\w+)'", check.message)
        if not match:
            return None

        typo = match.group(1)
        correct = match.group(2)
        new_content = content.replace(typo, correct)

        if new_content == content:
            return None

        return SuggestedFix(
            check_id=check.id,
            description=f"Rename '{typo}' → '{correct}'",
            old_text=typo,
            new_text=correct,
            diff=make_unified_diff(content, new_content),
            confidence=0.95,
            line=check.line,
        )

    def _fix_duplicate_column(
        self, content: str, check: CheckResult
    ) -> SuggestedFix | None:
        """Generate a fix for duplicate columns (AFW007)."""
        match = re.search(r"'(\w+)'", check.message)
        if not match:
            return None

        col_name = match.group(1)
        new_content = apply_column_removal(content, col_name)

        if new_content == content:
            return None

        return SuggestedFix(
            check_id=check.id,
            description=f"Remove duplicate column '{col_name}'",
            old_text=col_name,
            new_text="",
            diff=make_unified_diff(content, new_content),
            confidence=0.90,
            line=check.line,
        )

    def _fix_schedule_deprecation(
        self, content: str, check: CheckResult
    ) -> SuggestedFix | None:
        """Generate a fix for schedule_interval → schedule (AFW009)."""
        new_content = re.sub(
            r'\bschedule_interval\s*=',
            'schedule=',
            content,
        )

        if new_content == content:
            return None

        return SuggestedFix(
            check_id=check.id,
            description="Replace 'schedule_interval' with 'schedule'",
            old_text="schedule_interval=",
            new_text="schedule=",
            diff=make_unified_diff(content, new_content),
            confidence=1.0,
            line=check.line,
        )

    def _fix_missing_catchup(
        self, content: str, check: CheckResult
    ) -> SuggestedFix | None:
        """Generate a fix for missing catchup=False (AFW011)."""
        # Find the DAG() call and add catchup=False
        # Look for the closing paren of DAG(...)
        dag_pattern = re.compile(
            r'((?:with\s+)?DAG\s*\([^)]*)',
            re.DOTALL,
        )
        match = dag_pattern.search(content)
        if not match:
            return None

        dag_call = match.group(1)
        # Add catchup=False before the closing paren
        new_dag_call = dag_call.rstrip() + ",\n    catchup=False"
        new_content = content[:match.start(1)] + new_dag_call + content[match.end(1):]

        return SuggestedFix(
            check_id=check.id,
            description="Add 'catchup=False' to DAG definition",
            old_text=dag_call,
            new_text=new_dag_call,
            diff=make_unified_diff(content, new_content),
            confidence=0.85,
            line=check.line,
        )

    def _fix_column_typo(
        self, content: str, check: CheckResult
    ) -> SuggestedFix | None:
        """Generate a fix for a column name typo (AFW_LIVE_003)."""
        # Extract bad name and suggestion from the message
        match = re.search(r"Column '(\w+)'.*Did you mean '(\w+)'", check.message)
        if not match:
            return None

        typo = match.group(1)
        correct = match.group(2)
        new_content = apply_column_rename(content, typo, correct)

        if new_content == content:
            return None

        return SuggestedFix(
            check_id=check.id,
            description=f"Rename column '{typo}' → '{correct}'",
            old_text=typo,
            new_text=correct,
            diff=make_unified_diff(content, new_content),
            confidence=0.90,
            line=check.line,
            column=check.column,
        )
