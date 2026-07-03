"""Tests for engine/core/fixes.py — fuzzy match, diff, column ops."""

from engine.core.fixes import (
    fuzzy_match_column,
    make_unified_diff,
    apply_column_rename,
    apply_column_removal,
)


class TestFuzzyMatchColumn:
    def test_exact_match(self):
        matches = fuzzy_match_column("item_name", ["item_name", "price", "qty"])
        assert len(matches) >= 1
        assert matches[0][0] == "item_name"
        assert matches[0][1] == 1.0

    def test_close_match(self):
        matches = fuzzy_match_column("item_nam", ["item_name", "price", "qty"])
        assert len(matches) >= 1
        assert matches[0][0] == "item_name"
        assert matches[0][1] >= 0.80

    def test_no_match_below_threshold(self):
        matches = fuzzy_match_column("xyz", ["item_name", "price", "qty"])
        assert len(matches) == 0

    def test_case_insensitive(self):
        matches = fuzzy_match_column("ITEM_NAME", ["item_name", "price"])
        assert len(matches) >= 1
        assert matches[0][0] == "item_name"

    def test_multiple_matches_sorted(self):
        matches = fuzzy_match_column(
            "item_name",
            ["item_names", "item_name", "item_nam", "price"],
            threshold=0.80,
        )
        # Exact match should be first
        assert matches[0][0] == "item_name"


class TestMakeUnifiedDiff:
    def test_produces_diff(self):
        old = "line1\nline2\nline3\n"
        new = "line1\nmodified\nline3\n"
        diff = make_unified_diff(old, new)
        assert "-line2" in diff
        assert "+modified" in diff

    def test_no_diff_for_identical(self):
        text = "line1\nline2\n"
        diff = make_unified_diff(text, text)
        assert diff == ""


class TestApplyColumnRename:
    def test_renames_bare_column(self):
        content = "SELECT item_nam, price FROM products"
        result = apply_column_rename(content, "item_nam", "item_name")
        assert "item_name" in result
        assert "item_nam," not in result

    def test_renames_backtick_column(self):
        content = "SELECT `item_nam`, price FROM products"
        result = apply_column_rename(content, "item_nam", "item_name")
        assert "`item_name`" in result


class TestApplyColumnRemoval:
    def test_removes_duplicate(self):
        content = "SELECT\n  id,\n  name,\n  email,\n  name,\n  status\nFROM users"
        result = apply_column_removal(content, "name")
        lines = result.strip().splitlines()
        name_count = sum(1 for l in lines if "name" in l.strip().lower())
        assert name_count == 1  # Only one occurrence should remain
