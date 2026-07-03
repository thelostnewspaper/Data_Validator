"""Tests for engine/packs/airflow/static_checks.py — each check rule."""

from engine.core.models import CheckStatus
from engine.packs.airflow.static_checks import run_all_static_checks
from engine.tests.conftest import (
    VALID_DAG,
    SYNTAX_ERROR_DAG,
    VARIABLE_TYPO_DAG,
    NO_DAG_DEFINITION,
    UNUSED_IMPORT_DAG,
    DUPLICATE_TASK_ID_DAG,
    CIRCULAR_DEP_DAG,
    MISSING_START_DATE_DAG,
    DEPRECATED_SCHEDULE_DAG,
    MISSING_CATCHUP_DAG,
    SQL_DUPLICATE_COLUMNS_DAG,
    TOP_LEVEL_CODE_DAG,
)


def _get_check(results, check_id):
    """Get the first check result with the given ID."""
    return next((c for c in results if c.id == check_id), None)


def _get_checks(results, check_id):
    """Get all check results with the given ID."""
    return [c for c in results if c.id == check_id]


class TestAFW001Syntax:
    def test_valid_dag_passes(self):
        results = run_all_static_checks("/test.py", VALID_DAG)
        check = _get_check(results, "AFW001")
        assert check is not None
        assert check.status == CheckStatus.PASS

    def test_syntax_error_fails(self):
        results = run_all_static_checks("/test.py", SYNTAX_ERROR_DAG)
        check = _get_check(results, "AFW001")
        assert check is not None
        assert check.status == CheckStatus.FAIL
        assert check.line > 0

    def test_syntax_error_stops_other_checks(self):
        results = run_all_static_checks("/test.py", SYNTAX_ERROR_DAG)
        # Only AFW001 should be present since other checks can't run
        assert len(results) == 1


class TestAFW002VariableIntegrity:
    def test_valid_dag_passes(self):
        results = run_all_static_checks("/test.py", VALID_DAG)
        checks = _get_checks(results, "AFW002")
        assert all(c.status == CheckStatus.PASS for c in checks)

    def test_typo_detected(self):
        results = run_all_static_checks("/test.py", VARIABLE_TYPO_DAG)
        checks = _get_checks(results, "AFW002")
        fails = [c for c in checks if c.status == CheckStatus.FAIL]
        assert len(fails) >= 1
        assert "defdefault_args" in fails[0].message


class TestAFW003RequiredStructure:
    def test_valid_dag_passes(self):
        results = run_all_static_checks("/test.py", VALID_DAG)
        check = _get_check(results, "AFW003")
        assert check.status == CheckStatus.PASS

    def test_no_dag_warns(self):
        results = run_all_static_checks("/test.py", NO_DAG_DEFINITION)
        check = _get_check(results, "AFW003")
        assert check.status == CheckStatus.WARN


class TestAFW004OperatorImports:
    def test_all_used_passes(self):
        results = run_all_static_checks("/test.py", VALID_DAG)
        checks = _get_checks(results, "AFW004")
        assert all(c.status == CheckStatus.PASS for c in checks)

    def test_unused_warns(self):
        results = run_all_static_checks("/test.py", UNUSED_IMPORT_DAG)
        checks = _get_checks(results, "AFW004")
        warns = [c for c in checks if c.status == CheckStatus.WARN]
        assert len(warns) >= 1
        # BashOperator and EmailOperator are unused
        warn_messages = " ".join(c.message for c in warns)
        assert "EmailOperator" in warn_messages or "BashOperator" in warn_messages


class TestAFW005TaskIdUniqueness:
    def test_unique_passes(self):
        results = run_all_static_checks("/test.py", VALID_DAG)
        check = _get_check(results, "AFW005")
        assert check.status == CheckStatus.PASS

    def test_duplicate_fails(self):
        results = run_all_static_checks("/test.py", DUPLICATE_TASK_ID_DAG)
        check = _get_check(results, "AFW005")
        assert check.status == CheckStatus.FAIL
        assert "extract" in check.message


class TestAFW009ScheduleDeprecation:
    def test_schedule_passes(self):
        results = run_all_static_checks("/test.py", VALID_DAG)
        check = _get_check(results, "AFW009")
        assert check.status == CheckStatus.PASS

    def test_schedule_interval_warns(self):
        results = run_all_static_checks("/test.py", DEPRECATED_SCHEDULE_DAG)
        check = _get_check(results, "AFW009")
        assert check.status == CheckStatus.WARN


class TestAFW010CircularDependencies:
    def test_acyclic_passes(self):
        results = run_all_static_checks("/test.py", VALID_DAG)
        check = _get_check(results, "AFW010")
        assert check.status == CheckStatus.PASS

    def test_circular_fails(self):
        results = run_all_static_checks("/test.py", CIRCULAR_DEP_DAG)
        check = _get_check(results, "AFW010")
        assert check.status == CheckStatus.FAIL
        assert "Circular" in check.message


class TestAFW011MissingCatchup:
    def test_catchup_set_passes(self):
        results = run_all_static_checks("/test.py", VALID_DAG)
        check = _get_check(results, "AFW011")
        assert check.status == CheckStatus.PASS

    def test_missing_catchup_warns(self):
        results = run_all_static_checks("/test.py", MISSING_CATCHUP_DAG)
        check = _get_check(results, "AFW011")
        assert check.status == CheckStatus.WARN


class TestAFW012StartDateRequired:
    def test_start_date_set_passes(self):
        results = run_all_static_checks("/test.py", VALID_DAG)
        check = _get_check(results, "AFW012")
        assert check.status == CheckStatus.PASS

    def test_missing_start_date_fails(self):
        results = run_all_static_checks("/test.py", MISSING_START_DATE_DAG)
        check = _get_check(results, "AFW012")
        assert check.status == CheckStatus.FAIL


class TestAFW007SqlColumnDuplicates:
    def test_no_duplicates_passes(self):
        results = run_all_static_checks("/test.py", VALID_DAG)
        check = _get_check(results, "AFW007")
        assert check.status == CheckStatus.PASS

    def test_duplicates_warn(self):
        results = run_all_static_checks("/test.py", SQL_DUPLICATE_COLUMNS_DAG)
        checks = _get_checks(results, "AFW007")
        warns = [c for c in checks if c.status == CheckStatus.WARN]
        assert len(warns) >= 1
        assert "name" in warns[0].message.lower()


class TestAFW013TopLevelCode:
    def test_clean_passes(self):
        results = run_all_static_checks("/test.py", VALID_DAG)
        check = _get_check(results, "AFW013")
        assert check.status == CheckStatus.PASS

    def test_top_level_warns(self):
        results = run_all_static_checks("/test.py", TOP_LEVEL_CODE_DAG)
        checks = _get_checks(results, "AFW013")
        warns = [c for c in checks if c.status == CheckStatus.WARN]
        assert len(warns) >= 1
        assert "print" in warns[0].message.lower() or "top-level" in warns[0].message.lower()
