"""Tests for engine/core/models.py — serialization round-trips."""

import json
from engine.core.models import (
    CheckResult, CheckStatus, CheckCategory,
    SuggestedFix, ValidationResult, RemediationOption,
    FixImpact, AirflowConnectionFix,
)


class TestCheckResult:
    def test_to_dict_serializes_enums(self):
        cr = CheckResult(
            id="AFW001",
            status=CheckStatus.FAIL,
            category=CheckCategory.SYNTAX,
            message="Syntax error",
            line=10,
        )
        d = cr.to_dict()
        assert d["status"] == "fail"
        assert d["category"] == "syntax"
        assert d["id"] == "AFW001"
        assert d["line"] == 10

    def test_to_dict_round_trips_through_json(self):
        cr = CheckResult(
            id="AFW002",
            status=CheckStatus.WARN,
            category=CheckCategory.VARIABLES,
            message="Typo detected",
            detail="Some detail",
            line=5,
            column=3,
        )
        json_str = json.dumps(cr.to_dict())
        parsed = json.loads(json_str)
        assert parsed["id"] == "AFW002"
        assert parsed["status"] == "warn"
        assert parsed["message"] == "Typo detected"


class TestSuggestedFix:
    def test_to_dict(self):
        fix = SuggestedFix(
            check_id="AFW002",
            description="Rename x to y",
            old_text="x",
            new_text="y",
            confidence=0.92,
            line=10,
        )
        d = fix.to_dict()
        assert d["check_id"] == "AFW002"
        assert d["confidence"] == 0.92


class TestValidationResult:
    def test_compute_summary(self):
        result = ValidationResult(
            file_path="/test.py",
            checks=[
                CheckResult(id="A", status=CheckStatus.PASS, category=CheckCategory.SYNTAX, message="ok"),
                CheckResult(id="B", status=CheckStatus.WARN, category=CheckCategory.COLUMNS, message="warn"),
                CheckResult(id="C", status=CheckStatus.FAIL, category=CheckCategory.STRUCTURE, message="fail"),
                CheckResult(id="D", status=CheckStatus.PASS, category=CheckCategory.SYNTAX, message="ok"),
            ],
        )
        result.compute_summary()
        assert result.summary.total == 4
        assert result.summary.passed == 2
        assert result.summary.warnings == 1
        assert result.summary.failures == 1

    def test_to_dict(self):
        result = ValidationResult(file_path="/test.py")
        d = result.to_dict()
        assert d["file_path"] == "/test.py"
        assert "checks" in d
        assert "fixes" in d
        assert "summary" in d


class TestRemediationOption:
    def test_to_dict_serializes_impact(self):
        option = RemediationOption(
            impact=FixImpact.HIGH,
            title="Major restructure",
            root_cause="Bad structure",
        )
        d = option.to_dict()
        assert d["impact"] == "high"
        assert d["title"] == "Major restructure"


class TestAirflowConnectionFix:
    def test_to_dict(self):
        fix = AirflowConnectionFix(
            conn_id="my_db",
            conn_type="mysql",
            host="localhost",
            port=3306,
        )
        d = fix.to_dict()
        assert d["conn_id"] == "my_db"
        assert d["port"] == 3306
