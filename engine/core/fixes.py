"""
Shared deterministic fix utilities — no LLM, fast, free, trustworthy.

Provides fuzzy-match column rename suggestions (difflib SequenceMatcher >= 0.80)
and unified diff generation. Reused by all packs.
"""

from __future__ import annotations

import difflib
from typing import Sequence


def fuzzy_match_column(
    name: str,
    candidates: Sequence[str],
    threshold: float = 0.80,
) -> list[tuple[str, float]]:
    """
    Find close matches for a column name using SequenceMatcher.

    Args:
        name:       The column name to match.
        candidates: List of valid column names to match against.
        threshold:  Minimum similarity ratio (0.0–1.0). Default 0.80.

    Returns:
        List of (candidate, score) tuples sorted by score descending.
        Only matches >= threshold are returned.
    """
    matches: list[tuple[str, float]] = []
    name_lower = name.lower()

    for candidate in candidates:
        ratio = difflib.SequenceMatcher(
            None,
            name_lower,
            candidate.lower(),
        ).ratio()
        if ratio >= threshold:
            matches.append((candidate, ratio))

    matches.sort(key=lambda x: x[1], reverse=True)
    return matches


def make_unified_diff(
    old: str,
    new: str,
    old_label: str = "original",
    new_label: str = "fixed",
    context: int = 3,
) -> str:
    """
    Generate a unified diff string between two file contents.

    Args:
        old:       Original file content.
        new:       Modified file content.
        old_label: Label for the original version.
        new_label: Label for the fixed version.
        context:   Number of context lines around changes.

    Returns:
        Unified diff as a string. Empty string if no differences.
    """
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)

    diff_lines = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=old_label,
        tofile=new_label,
        n=context,
    )

    return "".join(diff_lines)


def apply_column_rename(
    content: str,
    old_name: str,
    new_name: str,
) -> str:
    """
    Rename all occurrences of a column name in file content.

    Uses word-boundary-aware replacement to avoid partial matches.
    Handles both quoted and unquoted column references.

    Args:
        content:  Full file content.
        old_name: Column name to replace.
        new_name: Replacement column name.

    Returns:
        Modified file content with the column renamed.
    """
    import re

    # Match the column name as a whole word (not part of another identifier)
    # Handles: bare name, `backtick`, "double-quoted", 'single-quoted'
    patterns = [
        # Bare identifier (word boundary)
        (
            re.compile(r'\b' + re.escape(old_name) + r'\b'),
            new_name,
        ),
        # Backtick-quoted
        (
            re.compile(r'`' + re.escape(old_name) + r'`'),
            f'`{new_name}`',
        ),
    ]

    result = content
    for pattern, replacement in patterns:
        result = pattern.sub(replacement, result)

    return result


def apply_column_removal(
    content: str,
    column_name: str,
) -> str:
    """
    Remove duplicate occurrences of a column from SELECT statements.

    Removes the second and subsequent occurrences of the column, including
    any trailing comma and whitespace.

    Args:
        content:     Full file content.
        column_name: Column name to deduplicate.

    Returns:
        Modified file content with duplicate column references removed.
    """
    import re

    lines = content.split('\n')
    result_lines: list[str] = []
    seen_column = False

    for line in lines:
        stripped = line.strip().rstrip(',').strip()

        # Check if this line is just the column name (possibly with alias/comma)
        is_column_line = bool(
            re.match(
                r'^[`"\']?' + re.escape(column_name) + r'[`"\']?\s*(,|$|\s+as\s+)',
                stripped,
                re.IGNORECASE,
            )
        )

        if is_column_line:
            if seen_column:
                # Skip this duplicate
                continue
            seen_column = True

        result_lines.append(line)

    return '\n'.join(result_lines)


def find_best_fix(
    check_message: str,
    content: str,
    candidates: Sequence[str],
    threshold: float = 0.80,
) -> tuple[str, str, float] | None:
    """
    Given a check message about a bad column name, find the best rename fix.

    Extracts the problematic name from the message, fuzzy-matches against
    candidates, and returns (old_name, new_name, confidence) or None.

    Args:
        check_message: The check result message containing the bad name.
        content:       Full file content.
        candidates:    Valid column names to match against.
        threshold:     Minimum similarity ratio.

    Returns:
        Tuple of (old_name, best_match, confidence) or None if no match.
    """
    import re

    # Try to extract a quoted name from the message
    match = re.search(r"['\"`]([^'\"`]+)['\"`]", check_message)
    if not match:
        return None

    bad_name = match.group(1)
    matches = fuzzy_match_column(bad_name, candidates, threshold)

    if matches:
        best_name, best_score = matches[0]
        return (bad_name, best_name, best_score)

    return None
