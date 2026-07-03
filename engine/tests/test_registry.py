"""Tests for engine/core/registry.py — pack detection and orchestration."""

from engine.core.registry import PackRegistry
from engine.core.models import CheckStatus
from engine.packs.airflow.pack import AirflowUniversalPack
from engine.tests.conftest import VALID_DAG, NON_AIRFLOW_FILE, SYNTAX_ERROR_DAG


class TestPackRegistry:
    def setup_method(self):
        self.registry = PackRegistry()
        self.registry.register(AirflowUniversalPack())

    def test_detects_airflow_dag(self):
        pack = self.registry.detect_pack("/test.py", VALID_DAG)
        assert pack is not None
        assert pack.id == "airflow-universal"

    def test_does_not_detect_non_airflow(self):
        pack = self.registry.detect_pack("/test.py", NON_AIRFLOW_FILE)
        assert pack is None

    def test_validate_valid_dag(self):
        result = self.registry.validate("/test.py", VALID_DAG)
        assert result.file_path == "/test.py"
        assert len(result.checks) > 0
        # Valid DAG should have all passes
        fails = [c for c in result.checks if c.status == CheckStatus.FAIL]
        assert len(fails) == 0

    def test_validate_syntax_error(self):
        result = self.registry.validate("/test.py", SYNTAX_ERROR_DAG)
        fails = [c for c in result.checks if c.status == CheckStatus.FAIL]
        assert len(fails) >= 1
        assert any(c.id == "AFW001" for c in fails)

    def test_validate_non_airflow_returns_empty(self):
        result = self.registry.validate("/test.py", NON_AIRFLOW_FILE)
        assert len(result.checks) == 0

    def test_get_packs(self):
        packs = self.registry.get_packs()
        assert len(packs) == 1
        assert packs[0]["id"] == "airflow-universal"

    def test_enabled_packs_filter(self):
        result = self.registry.validate(
            "/test.py",
            VALID_DAG,
            enabled_packs=["dbt"],  # Airflow pack not in the list
        )
        assert len(result.checks) == 0

    def test_summary_counts(self):
        result = self.registry.validate("/test.py", VALID_DAG)
        assert result.summary.total > 0
        assert result.summary.failures == 0
