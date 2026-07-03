"""
Airflow universal static checks — Layer 1, no network required.

All 13 checks from the design doc, derivable from the DAG file alone.
Each function returns a list of CheckResult.

Check IDs:
    AFW001 — Python syntax validity
    AFW002 — DAG variable integrity (default_args defined before use)
    AFW003 — Required structure (with DAG or DAG context)
    AFW004 — Operator imports match usage
    AFW005 — Task ID uniqueness
    AFW006 — Dependency integrity (references defined tasks)
    AFW007 — SQL column duplicate detection
    AFW008 — SELECT-alias integrity
    AFW009 — schedule_interval deprecation
    AFW010 — Circular task dependencies
    AFW011 — Missing catchup=False
    AFW012 — start_date required
    AFW013 — Top-level code outside DAG context
"""

from __future__ import annotations

import ast
import re
from collections import Counter

from engine.core.models import CheckResult, CheckStatus, CheckCategory
from engine.core.graph import build_dependency_graph, has_circular_dependencies
from engine.packs.airflow.parser import (
    parse_dag_file,
    parse_dag_ast,
    DAGInfo,
    extract_columns_from_sql,
)


def run_all_static_checks(file_path: str, content: str) -> list[CheckResult]:
    """
    Run all Layer 1 static checks on a DAG file.

    Returns aggregated list of CheckResult from all individual checks.
    """
    results: list[CheckResult] = []

    # Parse the DAG
    dag_info = parse_dag_file(content)

    # AFW001 — Syntax check (must run first — if it fails, most others can't run)
    results.extend(check_syntax(content, dag_info))

    if dag_info.syntax_error:
        # Can't run further checks if the file doesn't parse
        return results

    # All remaining checks
    results.extend(check_dag_variable_integrity(content, dag_info))
    results.extend(check_required_structure(content, dag_info))
    results.extend(check_operator_imports(content, dag_info))
    results.extend(check_task_id_uniqueness(content, dag_info))
    results.extend(check_dependency_integrity(content, dag_info))
    results.extend(check_sql_column_duplicates(content, dag_info))
    results.extend(check_select_alias_integrity(content, dag_info))
    results.extend(check_schedule_interval_deprecation(content, dag_info))
    results.extend(check_circular_dependencies(content, dag_info))
    results.extend(check_missing_catchup(content, dag_info))
    results.extend(check_start_date_required(content, dag_info))
    results.extend(check_top_level_code(content, dag_info))

    return results


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_syntax(content: str, dag_info: DAGInfo) -> list[CheckResult]:
    """AFW001 — Python syntax validity."""
    if dag_info.syntax_error:
        err = dag_info.syntax_error
        return [CheckResult(
            id="AFW001",
            status=CheckStatus.FAIL,
            category=CheckCategory.SYNTAX,
            message=f"Syntax error: {err.msg}",
            detail=(
                f"Python cannot parse this file. Fix the syntax error before "
                f"other checks can run.\n\n"
                f"Error: {err.msg}\n"
                f"Line {err.lineno}, Column {err.offset}"
            ),
            line=err.lineno or 0,
            column=(err.offset or 1) - 1,
            source_rule="Python syntax validity",
        )]

    return [CheckResult(
        id="AFW001",
        status=CheckStatus.PASS,
        category=CheckCategory.SYNTAX,
        message="Python syntax is valid",
        source_rule="Python syntax validity",
    )]


def check_dag_variable_integrity(content: str, dag_info: DAGInfo) -> list[CheckResult]:
    """
    AFW002 — DAG variable integrity.

    Checks for:
    - default_args referenced but not defined
    - Typos like 'defdefault_args' (common copy-paste error)
    - Variable used before assignment in DAG context
    """
    results: list[CheckResult] = []
    lines = content.splitlines()

    # Check for common typos in variable names
    typo_patterns = [
        (r'\bdefdefault_args\b', "defdefault_args", "default_args"),
        (r'\bdefault_argss\b', "default_argss", "default_args"),
        (r'\bdag_idd\b', "dag_idd", "dag_id"),
        (r'\btask_idd\b', "task_idd", "task_id"),
        (r'\bschedule_intervall\b', "schedule_intervall", "schedule_interval"),
    ]

    for pattern, typo, correct in typo_patterns:
        for i, line in enumerate(lines, 1):
            if re.search(pattern, line):
                results.append(CheckResult(
                    id="AFW002",
                    status=CheckStatus.FAIL,
                    category=CheckCategory.VARIABLES,
                    message=f"Likely typo: '{typo}' — did you mean '{correct}'?",
                    detail=(
                        f"Found '{typo}' on line {i}. This is likely a typo for "
                        f"'{correct}'. This will cause a NameError at runtime."
                    ),
                    line=i,
                    source_rule="DAG variable integrity",
                ))

    # Check if default_args is referenced in DAG() but not defined
    tree, _ = parse_dag_ast(content)
    if tree:
        default_args_defined = dag_info.default_args_name is not None

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _get_call_name(node.func)
                if name and "DAG" in name:
                    for kw in node.keywords:
                        if kw.arg == "default_args":
                            if isinstance(kw.value, ast.Name):
                                if not default_args_defined:
                                    results.append(CheckResult(
                                        id="AFW002",
                                        status=CheckStatus.FAIL,
                                        category=CheckCategory.VARIABLES,
                                        message=f"'{kw.value.id}' is used in DAG() but not defined",
                                        detail=(
                                            f"The variable '{kw.value.id}' is passed to DAG() as "
                                            f"default_args but no assignment for it was found. "
                                            f"This will cause a NameError."
                                        ),
                                        line=node.lineno,
                                        source_rule="DAG variable integrity",
                                    ))

    if not results:
        results.append(CheckResult(
            id="AFW002",
            status=CheckStatus.PASS,
            category=CheckCategory.VARIABLES,
            message="DAG variable integrity OK",
            source_rule="DAG variable integrity",
        ))

    return results


def check_required_structure(content: str, dag_info: DAGInfo) -> list[CheckResult]:
    """
    AFW003 — Required structure.

    Must have `with DAG(` or `DAG(` context.
    """
    if dag_info.dag_line > 0:
        return [CheckResult(
            id="AFW003",
            status=CheckStatus.PASS,
            category=CheckCategory.STRUCTURE,
            message="DAG definition found",
            line=dag_info.dag_line,
            source_rule="Required DAG structure",
        )]

    return [CheckResult(
        id="AFW003",
        status=CheckStatus.WARN,
        category=CheckCategory.STRUCTURE,
        message="No DAG definition found — expected `with DAG(...)` or `DAG(...)`",
        detail=(
            "This file imports Airflow but doesn't define a DAG. "
            "A DAG file must contain a `DAG(...)` or `with DAG(...)` "
            "call for the Airflow scheduler to discover it."
        ),
        source_rule="Required DAG structure",
    )]


def check_operator_imports(content: str, dag_info: DAGInfo) -> list[CheckResult]:
    """
    AFW004 — Operator imports match usage.

    Imported operator classes should be actually instantiated in the DAG.
    """
    results: list[CheckResult] = []

    # Collect imported operator class names
    operator_modules = {
        "airflow.operators",
        "airflow.providers",
        "airflow.sensors",
        "airflow.utils",
    }

    imported_operators: dict[str, int] = {}  # name -> line
    for imp in dag_info.imports:
        if imp.is_from and any(imp.module.startswith(m) for m in operator_modules):
            for name in imp.names:
                imported_operators[name] = imp.line

    # Collect used operator class names (from task definitions)
    used_operators: set[str] = set()
    for task in dag_info.tasks:
        used_operators.add(task.operator_class)

    # Also check for usage in the content (might be used in non-task contexts)
    for name in list(imported_operators.keys()):
        # Check if the name appears in the code (beyond the import line)
        lines = content.splitlines()
        import_line = imported_operators[name]
        for i, line in enumerate(lines, 1):
            if i == import_line:
                continue
            if re.search(r'\b' + re.escape(name) + r'\b', line):
                used_operators.add(name)
                break

    # Find unused imports
    unused = set(imported_operators.keys()) - used_operators
    for name in unused:
        results.append(CheckResult(
            id="AFW004",
            status=CheckStatus.WARN,
            category=CheckCategory.STRUCTURE,
            message=f"Imported operator '{name}' is never used",
            detail=(
                f"'{name}' is imported on line {imported_operators[name]} but "
                f"never instantiated in this DAG. Consider removing the unused import."
            ),
            line=imported_operators[name],
            source_rule="Operator import usage",
        ))

    if not unused:
        results.append(CheckResult(
            id="AFW004",
            status=CheckStatus.PASS,
            category=CheckCategory.STRUCTURE,
            message="All imported operators are used",
            source_rule="Operator import usage",
        ))

    return results


def check_task_id_uniqueness(content: str, dag_info: DAGInfo) -> list[CheckResult]:
    """AFW005 — Task ID uniqueness."""
    results: list[CheckResult] = []

    task_ids = [t.task_id for t in dag_info.tasks]
    counts = Counter(task_ids)
    duplicates = {tid: count for tid, count in counts.items() if count > 1}

    for tid, count in duplicates.items():
        # Find all lines where this task_id appears
        dup_tasks = [t for t in dag_info.tasks if t.task_id == tid]
        lines = [str(t.line) for t in dup_tasks]
        results.append(CheckResult(
            id="AFW005",
            status=CheckStatus.FAIL,
            category=CheckCategory.STRUCTURE,
            message=f"Duplicate task_id '{tid}' found {count} times",
            detail=(
                f"task_id='{tid}' is used {count} times (lines {', '.join(lines)}). "
                f"Each task in a DAG must have a unique task_id. "
                f"Duplicate task_ids will cause unpredictable behavior."
            ),
            line=dup_tasks[0].line if dup_tasks else 0,
            source_rule="Task ID uniqueness",
        ))

    if not duplicates:
        results.append(CheckResult(
            id="AFW005",
            status=CheckStatus.PASS,
            category=CheckCategory.STRUCTURE,
            message=f"All {len(task_ids)} task IDs are unique",
            source_rule="Task ID uniqueness",
        ))

    return results


def check_dependency_integrity(content: str, dag_info: DAGInfo) -> list[CheckResult]:
    """AFW006 — Dependency integrity (>> / << reference defined tasks)."""
    results: list[CheckResult] = []

    # Build set of defined task variable names
    # We need to map from variable names to task_ids
    # The parser gives us task_ids, but dependencies use variable names
    # We'll check both

    # Also extract variable names assigned to tasks from the AST
    tree, _ = parse_dag_ast(content)
    defined_vars: set[str] = set()
    if tree:
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        defined_vars.add(target.id)

    for dep in dag_info.dependencies:
        for name, role in [(dep.upstream, "upstream"), (dep.downstream, "downstream")]:
            # Strip any dotted prefix (e.g., "task1" from "task1.output")
            base_name = name.split(".")[0] if name else name
            if base_name and base_name not in defined_vars:
                results.append(CheckResult(
                    id="AFW006",
                    status=CheckStatus.FAIL,
                    category=CheckCategory.DEPENDENCIES,
                    message=f"Undefined {role} task variable: '{base_name}'",
                    detail=(
                        f"'{base_name}' is used as {role} in a dependency chain "
                        f"on line {dep.line} but is not defined in this file. "
                        f"This will cause a NameError at parse time."
                    ),
                    line=dep.line,
                    source_rule="Dependency integrity",
                ))

    if not results:
        results.append(CheckResult(
            id="AFW006",
            status=CheckStatus.PASS,
            category=CheckCategory.DEPENDENCIES,
            message="All dependency references are valid",
            source_rule="Dependency integrity",
        ))

    return results


def check_sql_column_duplicates(content: str, dag_info: DAGInfo) -> list[CheckResult]:
    """AFW007 — SQL column duplicate detection in SELECT statements."""
    results: list[CheckResult] = []

    for frag in dag_info.sql_fragments:
        columns = extract_columns_from_sql(frag.sql)
        col_names = [c[0].lower() for c in columns]
        counts = Counter(col_names)
        duplicates = {name: count for name, count in counts.items() if count > 1}

        for col, count in duplicates.items():
            results.append(CheckResult(
                id="AFW007",
                status=CheckStatus.WARN,
                category=CheckCategory.COLUMNS,
                message=f"Duplicate column '{col}' in SELECT ({count} times) in task '{frag.task_id}'",
                detail=(
                    f"Column '{col}' appears {count} times in the SELECT statement "
                    f"of task '{frag.task_id}'. Duplicate columns may cause "
                    f"unexpected behavior in downstream processing."
                ),
                line=frag.line,
                source_rule="SQL column duplicate detection",
            ))

    if not results:
        results.append(CheckResult(
            id="AFW007",
            status=CheckStatus.PASS,
            category=CheckCategory.COLUMNS,
            message="No duplicate columns in SQL",
            source_rule="SQL column duplicate detection",
        ))

    return results


def check_select_alias_integrity(content: str, dag_info: DAGInfo) -> list[CheckResult]:
    """AFW008 — SELECT-alias integrity (aliases don't shadow column names)."""
    results: list[CheckResult] = []

    for frag in dag_info.sql_fragments:
        # Find aliases in SELECT statements
        alias_pattern = re.compile(
            r"""(\w+)\s+AS\s+(\w+)""",
            re.IGNORECASE,
        )

        columns = [c[0].lower() for c in extract_columns_from_sql(frag.sql)]

        for match in alias_pattern.finditer(frag.sql):
            original = match.group(1).lower()
            alias = match.group(2).lower()

            # Check if the alias shadows another real column name
            if alias in columns and alias != original:
                results.append(CheckResult(
                    id="AFW008",
                    status=CheckStatus.WARN,
                    category=CheckCategory.COLUMNS,
                    message=(
                        f"Alias '{match.group(2)}' shadows column '{match.group(2)}' "
                        f"in task '{frag.task_id}'"
                    ),
                    detail=(
                        f"In the SELECT statement of task '{frag.task_id}', "
                        f"'{match.group(1)}' is aliased as '{match.group(2)}', "
                        f"which shadows another column with the same name. "
                        f"This can cause confusion in downstream processing."
                    ),
                    line=frag.line,
                    source_rule="SELECT-alias integrity",
                ))

    if not results:
        results.append(CheckResult(
            id="AFW008",
            status=CheckStatus.PASS,
            category=CheckCategory.COLUMNS,
            message="SELECT aliases are clean",
            source_rule="SELECT-alias integrity",
        ))

    return results


def check_schedule_interval_deprecation(content: str, dag_info: DAGInfo) -> list[CheckResult]:
    """AFW009 — schedule_interval deprecation warning."""
    if dag_info.schedule_param == "schedule_interval":
        return [CheckResult(
            id="AFW009",
            status=CheckStatus.WARN,
            category=CheckCategory.BEST_PRACTICES,
            message="'schedule_interval' is deprecated — use 'schedule' instead",
            detail=(
                "The 'schedule_interval' parameter has been deprecated since "
                "Airflow 2.4. Use the 'schedule' parameter instead for forward "
                "compatibility:\n\n"
                "  Before: DAG(..., schedule_interval='@daily')\n"
                "  After:  DAG(..., schedule='@daily')"
            ),
            line=dag_info.schedule_line,
            source_rule="schedule_interval deprecation",
        )]

    return [CheckResult(
        id="AFW009",
        status=CheckStatus.PASS,
        category=CheckCategory.BEST_PRACTICES,
        message="Schedule parameter is current",
        source_rule="schedule_interval deprecation",
    )]


def check_circular_dependencies(content: str, dag_info: DAGInfo) -> list[CheckResult]:
    """AFW010 — Circular task dependencies."""
    if not dag_info.dependencies:
        return [CheckResult(
            id="AFW010",
            status=CheckStatus.PASS,
            category=CheckCategory.DEPENDENCIES,
            message="No task dependencies to check for cycles",
            source_rule="Circular task dependencies",
        )]

    # Build the graph from dependency edges
    nodes = list({d.upstream for d in dag_info.dependencies} |
                 {d.downstream for d in dag_info.dependencies})
    edges = [(d.upstream, d.downstream) for d in dag_info.dependencies]

    graph = build_dependency_graph(nodes, edges)
    cycles = has_circular_dependencies(graph)

    if cycles:
        results: list[CheckResult] = []
        for cycle in cycles:
            cycle_str = " → ".join(cycle)
            results.append(CheckResult(
                id="AFW010",
                status=CheckStatus.FAIL,
                category=CheckCategory.DEPENDENCIES,
                message=f"Circular dependency detected: {cycle_str}",
                detail=(
                    f"The following tasks form a circular dependency chain:\n"
                    f"  {cycle_str}\n\n"
                    f"Airflow cannot execute tasks with circular dependencies. "
                    f"Remove or restructure one of the edges to break the cycle."
                ),
                source_rule="Circular task dependencies",
            ))
        return results

    return [CheckResult(
        id="AFW010",
        status=CheckStatus.PASS,
        category=CheckCategory.DEPENDENCIES,
        message="No circular dependencies found",
        source_rule="Circular task dependencies",
    )]


def check_missing_catchup(content: str, dag_info: DAGInfo) -> list[CheckResult]:
    """AFW011 — Missing catchup=False (common gotcha)."""
    if not dag_info.has_catchup:
        return [CheckResult(
            id="AFW011",
            status=CheckStatus.WARN,
            category=CheckCategory.BEST_PRACTICES,
            message="Missing 'catchup=False' in DAG definition",
            detail=(
                "The DAG definition does not explicitly set 'catchup'. "
                "Airflow defaults catchup to True, which means when the DAG "
                "is first enabled, it will try to backfill all missed runs "
                "since start_date. This is usually not desired.\n\n"
                "Add catchup=False to your DAG:\n"
                "  with DAG(..., catchup=False):"
            ),
            line=dag_info.dag_line,
            source_rule="Missing catchup=False",
        )]

    return [CheckResult(
        id="AFW011",
        status=CheckStatus.PASS,
        category=CheckCategory.BEST_PRACTICES,
        message="catchup is explicitly set",
        source_rule="Missing catchup=False",
    )]


def check_start_date_required(content: str, dag_info: DAGInfo) -> list[CheckResult]:
    """AFW012 — start_date in default_args or DAG."""
    if dag_info.has_start_date:
        return [CheckResult(
            id="AFW012",
            status=CheckStatus.PASS,
            category=CheckCategory.STRUCTURE,
            message="start_date is defined",
            source_rule="start_date required",
        )]

    return [CheckResult(
        id="AFW012",
        status=CheckStatus.FAIL,
        category=CheckCategory.STRUCTURE,
        message="Missing required 'start_date' in DAG or default_args",
        detail=(
            "Every DAG must have a 'start_date' — either in default_args or "
            "as a DAG parameter. Without it, the scheduler cannot determine "
            "when to start scheduling runs.\n\n"
            "Add start_date:\n"
            "  default_args = {'start_date': datetime(2024, 1, 1)}\n"
            "  or\n"
            "  with DAG(..., start_date=datetime(2024, 1, 1)):"
        ),
        line=dag_info.dag_line or 1,
        source_rule="start_date required",
    )]


def check_top_level_code(content: str, dag_info: DAGInfo) -> list[CheckResult]:
    """AFW013 — Top-level code outside DAG context (accidental execution)."""
    results: list[CheckResult] = []

    for line_num, code_line in dag_info.top_level_statements:
        results.append(CheckResult(
            id="AFW013",
            status=CheckStatus.WARN,
            category=CheckCategory.BEST_PRACTICES,
            message=f"Top-level code outside DAG context: '{code_line[:60]}...'",
            detail=(
                f"Line {line_num} contains executable code outside a DAG context "
                f"manager or function definition. This code runs every time the "
                f"scheduler parses the DAG file (which can be very frequent), "
                f"not just when the DAG runs.\n\n"
                f"Move this code inside a task or function, or wrap it in "
                f"'if __name__ == \"__main__\":'."
            ),
            line=line_num,
            source_rule="Top-level code outside DAG context",
        ))

    if not results:
        results.append(CheckResult(
            id="AFW013",
            status=CheckStatus.PASS,
            category=CheckCategory.BEST_PRACTICES,
            message="No suspicious top-level code found",
            source_rule="Top-level code outside DAG context",
        ))

    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_call_name(node: ast.expr) -> str | None:
    """Get the name of a function being called."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None
