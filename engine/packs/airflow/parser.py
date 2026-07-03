"""
AST + regex helpers to extract information from an Airflow DAG file
without executing it.

This is the parser layer that the static_checks and live_checks modules
use to understand the DAG's structure. All extraction is done via ast
and regex — NEVER by importing or executing the DAG.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data structures for parsed DAG information
# ---------------------------------------------------------------------------

@dataclass
class ImportInfo:
    """Information about a single import statement."""
    module: str
    names: list[str]
    line: int
    is_from: bool = False

    @property
    def full_names(self) -> list[str]:
        if self.is_from:
            return [f"{self.module}.{name}" for name in self.names]
        return [self.module]


@dataclass
class SQLFragment:
    """A SQL string extracted from operator kwargs."""
    sql: str
    task_id: str
    operator: str
    kwarg_name: str
    line: int


@dataclass
class TaskInfo:
    """Information about a single task/operator in the DAG."""
    task_id: str
    operator_class: str
    line: int
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class DependencyEdge:
    """A task dependency (upstream >> downstream)."""
    upstream: str
    downstream: str
    line: int


@dataclass
class DAGInfo:
    """Complete parsed information about a DAG file."""
    dag_id: str | None = None
    dag_line: int = 0
    tasks: list[TaskInfo] = field(default_factory=list)
    dependencies: list[DependencyEdge] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    sql_fragments: list[SQLFragment] = field(default_factory=list)
    default_args_name: str | None = None
    default_args_line: int = 0
    default_args: dict[str, Any] = field(default_factory=dict)
    has_start_date: bool = False
    has_catchup: bool = False
    catchup_value: bool | None = None
    schedule_param: str | None = None  # "schedule" or "schedule_interval"
    schedule_line: int = 0
    top_level_statements: list[tuple[int, str]] = field(default_factory=list)
    syntax_error: SyntaxError | None = None


# ---------------------------------------------------------------------------
# Core parse function
# ---------------------------------------------------------------------------

def parse_dag_ast(content: str) -> tuple[ast.Module | None, SyntaxError | None]:
    """
    Safely parse Python source into an AST.

    Args:
        content: Full file content.

    Returns:
        Tuple of (ast_tree, syntax_error). One will always be None.
    """
    try:
        tree = ast.parse(content)
        return tree, None
    except SyntaxError as e:
        return None, e


# ---------------------------------------------------------------------------
# Extraction functions
# ---------------------------------------------------------------------------

def extract_imports(tree: ast.Module) -> list[ImportInfo]:
    """Extract all import statements from the AST."""
    imports: list[ImportInfo] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(ImportInfo(
                    module=alias.name,
                    names=[alias.asname or alias.name],
                    line=node.lineno,
                    is_from=False,
                ))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = [alias.name for alias in node.names]
            imports.append(ImportInfo(
                module=module,
                names=names,
                line=node.lineno,
                is_from=True,
            ))

    return imports


def extract_dag_id(tree: ast.Module) -> tuple[str | None, int]:
    """
    Extract the DAG ID from a `DAG(...)` or `with DAG(...)` call.

    Returns:
        Tuple of (dag_id, line_number). (None, 0) if not found.
    """
    for node in ast.walk(tree):
        # Match: DAG('dag_id', ...) or DAG(dag_id='...', ...)
        if isinstance(node, ast.Call):
            func = node.func

            # Direct call: DAG(...)
            is_dag_call = (
                (isinstance(func, ast.Name) and func.id == "DAG")
                or (isinstance(func, ast.Attribute) and func.attr == "DAG")
            )

            if is_dag_call:
                # First positional arg
                if node.args:
                    first_arg = node.args[0]
                    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                        return first_arg.value, node.lineno

                # dag_id keyword
                for kw in node.keywords:
                    if kw.arg == "dag_id":
                        if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                            return kw.value.value, node.lineno

                # DAG exists but couldn't extract ID
                return None, node.lineno

    return None, 0


def extract_tasks(tree: ast.Module) -> list[TaskInfo]:
    """
    Extract task definitions from operator instantiations.

    Looks for patterns like:
        task = PythonOperator(task_id='my_task', ...)
        task = BashOperator(task_id='my_task', ...)
    """
    tasks: list[TaskInfo] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Get the operator class name
            operator_class = _get_call_name(node.func)
            if not operator_class:
                continue

            # Look for task_id in kwargs
            task_id = None
            kwargs: dict[str, Any] = {}

            for kw in node.keywords:
                if kw.arg == "task_id":
                    if isinstance(kw.value, ast.Constant):
                        task_id = str(kw.value.value)
                elif kw.arg:
                    # Store other kwargs as their string representation
                    kwargs[kw.arg] = ast.dump(kw.value)

            if task_id:
                tasks.append(TaskInfo(
                    task_id=task_id,
                    operator_class=operator_class,
                    line=node.lineno,
                    kwargs=kwargs,
                ))

    return tasks


def extract_dependencies(tree: ast.Module, content: str) -> list[DependencyEdge]:
    """
    Extract task dependency edges from >> / << operators and set_downstream/set_upstream calls.

    Handles patterns like:
        task1 >> task2 >> task3
        task1 << task2
        task1.set_downstream(task2)
    """
    edges: list[DependencyEdge] = []

    for node in ast.walk(tree):
        # >> operator (BinOp with RShift)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.RShift):
            _extract_shift_chain(node, edges, is_right_shift=True)

        # << operator (BinOp with LShift)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.LShift):
            _extract_shift_chain(node, edges, is_right_shift=False)

        # set_downstream / set_upstream calls
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == "set_downstream" and node.args:
                    upstream = _get_name(node.func.value)
                    downstream = _get_name(node.args[0])
                    if upstream and downstream:
                        edges.append(DependencyEdge(
                            upstream=upstream,
                            downstream=downstream,
                            line=node.lineno,
                        ))
                elif node.func.attr == "set_upstream" and node.args:
                    downstream = _get_name(node.func.value)
                    upstream = _get_name(node.args[0])
                    if upstream and downstream:
                        edges.append(DependencyEdge(
                            upstream=upstream,
                            downstream=downstream,
                            line=node.lineno,
                        ))

    return edges


def extract_sql_strings(tree: ast.Module) -> list[SQLFragment]:
    """
    Extract SQL strings from operator kwargs (sql=, query=, etc.).

    Looks inside operator instantiations for string arguments that
    look like SQL.
    """
    fragments: list[SQLFragment] = []
    sql_kwarg_names = {"sql", "query", "queries", "hql"}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        operator_class = _get_call_name(node.func) or ""
        task_id = ""

        for kw in node.keywords:
            if kw.arg == "task_id" and isinstance(kw.value, ast.Constant):
                task_id = str(kw.value.value)

        for kw in node.keywords:
            if kw.arg in sql_kwarg_names:
                sql_text = _extract_string_value(kw.value)
                if sql_text:
                    fragments.append(SQLFragment(
                        sql=sql_text,
                        task_id=task_id,
                        operator=operator_class,
                        kwarg_name=kw.arg or "",
                        line=kw.value.lineno if hasattr(kw.value, "lineno") else node.lineno,
                    ))

    return fragments


def extract_source_tables(sql: str) -> list[str]:
    """
    Extract source table names from SQL using regex.

    Handles:
        FROM table_name
        JOIN table_name
        FROM schema.table_name
    """
    pattern = re.compile(
        r"""(?:FROM|JOIN)\s+"""
        r"""[`"']?(\w+(?:\.\w+)?)[`"']?""",
        re.IGNORECASE,
    )
    tables = pattern.findall(sql)
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for t in tables:
        t_lower = t.lower()
        if t_lower not in seen:
            seen.add(t_lower)
            unique.append(t)
    return unique


def extract_columns_from_sql(sql: str) -> list[tuple[str, int]]:
    """
    Extract column names from SELECT statements.

    Returns list of (column_name, approximate_position) tuples.
    Handles:
        SELECT col1, col2, col3 FROM ...
        SELECT col1 AS alias, col2 FROM ...
        SELECT t.col1, t.col2 FROM ...
    """
    columns: list[tuple[str, int]] = []

    # Find SELECT ... FROM blocks
    select_pattern = re.compile(
        r"""SELECT\s+(.*?)\s+FROM""",
        re.IGNORECASE | re.DOTALL,
    )

    for match in select_pattern.finditer(sql):
        select_body = match.group(1)
        offset = match.start(1)

        # Split by comma, handling parentheses nesting
        parts = _split_select_columns(select_body)

        for i, part in enumerate(parts):
            col = part.strip()
            if not col or col == "*":
                continue

            # Remove table prefix (t.column -> column)
            if "." in col:
                col = col.split(".")[-1]

            # Handle aliases: "column AS alias" -> take the original column name
            alias_match = re.match(
                r"""[`"']?(\w+)[`"']?\s+(?:AS\s+)?[`"']?(\w+)[`"']?""",
                col,
                re.IGNORECASE,
            )
            if alias_match:
                col = alias_match.group(1)

            # Clean up any remaining quotes/backticks
            col = col.strip("`\"' \t\n")

            if col and re.match(r"^\w+$", col):
                columns.append((col, offset + sum(len(p) + 1 for p in parts[:i])))

    return columns


def extract_default_args(tree: ast.Module) -> tuple[str | None, dict[str, Any], int, bool]:
    """
    Extract default_args dict assignment.

    Returns:
        Tuple of (variable_name, args_dict, line, has_start_date).
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and "default_args" in target.id.lower():
                    if isinstance(node.value, ast.Dict):
                        args = _ast_dict_to_dict(node.value)
                        has_start_date = "start_date" in args
                        return target.id, args, node.lineno, has_start_date
                    return target.id, {}, node.lineno, False

    return None, {}, 0, False


def extract_dag_context(tree: ast.Module) -> list[tuple[int, int]]:
    """
    Find the line ranges of DAG context managers.

    Returns list of (start_line, end_line) for each `with DAG(...)` block.
    """
    contexts: list[tuple[int, int]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            for item in node.items:
                call = item.context_expr
                if isinstance(call, ast.Call):
                    name = _get_call_name(call.func)
                    if name and "DAG" in name:
                        end_line = max(
                            getattr(n, "lineno", node.lineno)
                            for n in ast.walk(node)
                        )
                        contexts.append((node.lineno, end_line))

    return contexts


def find_top_level_code(tree: ast.Module, content: str) -> list[tuple[int, str]]:
    """
    Find top-level statements that are NOT inside a DAG context or are not
    import/assignment/function/class definitions.

    These are potential accidental execution risks.
    """
    dag_contexts = extract_dag_context(tree)
    suspicious: list[tuple[int, str]] = []

    for node in ast.iter_child_nodes(tree):
        line = getattr(node, "lineno", 0)

        # Skip imports, function/class defs, assignments
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef,
                             ast.AsyncFunctionDef, ast.ClassDef, ast.Assign,
                             ast.AnnAssign, ast.If, ast.With)):
            continue

        # Skip if inside a DAG context
        in_dag = any(start <= line <= end for start, end in dag_contexts)
        if in_dag:
            continue

        # This is a top-level expression/call that could execute on import
        if isinstance(node, ast.Expr):
            code_line = content.splitlines()[line - 1].strip() if line > 0 else ""
            if code_line and not code_line.startswith("#"):
                suspicious.append((line, code_line))

    return suspicious


def parse_dag_file(content: str) -> DAGInfo:
    """
    Full DAG parse — extracts all information needed for validation.

    This is the main entry point for the parser module.
    """
    info = DAGInfo()

    tree, syntax_error = parse_dag_ast(content)
    if syntax_error:
        info.syntax_error = syntax_error
        return info

    assert tree is not None

    # Imports
    info.imports = extract_imports(tree)

    # DAG ID
    info.dag_id, info.dag_line = extract_dag_id(tree)

    # Tasks
    info.tasks = extract_tasks(tree)

    # Dependencies
    info.dependencies = extract_dependencies(tree, content)

    # SQL fragments
    info.sql_fragments = extract_sql_strings(tree)

    # Default args
    (
        info.default_args_name,
        info.default_args,
        info.default_args_line,
        info.has_start_date,
    ) = extract_default_args(tree)

    # Check for start_date in DAG() kwargs too
    if not info.has_start_date:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _get_call_name(node.func)
                if name and "DAG" in name:
                    for kw in node.keywords:
                        if kw.arg == "start_date":
                            info.has_start_date = True
                            break

    # Schedule parameter
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _get_call_name(node.func)
            if name and "DAG" in name:
                for kw in node.keywords:
                    if kw.arg in ("schedule_interval", "schedule"):
                        info.schedule_param = kw.arg
                        info.schedule_line = node.lineno
                    if kw.arg == "catchup":
                        info.has_catchup = True
                        if isinstance(kw.value, ast.Constant):
                            info.catchup_value = bool(kw.value.value)

    # Top-level code
    info.top_level_statements = find_top_level_code(tree, content)

    return info


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_call_name(node: ast.expr) -> str | None:
    """Get the name of a function/class being called."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _get_name(node: ast.expr) -> str | None:
    """Get a variable name from an AST node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_get_name(node.value)}.{node.attr}" if node.value else node.attr
    return None


def _extract_string_value(node: ast.expr) -> str | None:
    """Extract a string value from an AST node (handles f-strings, concatenation)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        # f-string — reconstruct approximately
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(str(value.value))
            else:
                parts.append("{...}")
        return "".join(parts)
    return None


def _extract_shift_chain(
    node: ast.BinOp,
    edges: list[DependencyEdge],
    is_right_shift: bool,
) -> None:
    """Recursively extract dependency edges from chained >> or << operators."""
    left_name = _get_name(node.left) if not isinstance(node.left, ast.BinOp) else None
    right_name = _get_name(node.right)

    # Recurse into left side if it's also a shift
    if isinstance(node.left, ast.BinOp) and isinstance(node.left.op, (ast.RShift, ast.LShift)):
        _extract_shift_chain(node.left, edges, is_right_shift)
        # The rightmost node of the left subtree is the upstream
        left_name = _get_name(node.left.right)

    if left_name and right_name:
        if is_right_shift:
            edges.append(DependencyEdge(
                upstream=left_name,
                downstream=right_name,
                line=node.lineno,
            ))
        else:
            edges.append(DependencyEdge(
                upstream=right_name,
                downstream=left_name,
                line=node.lineno,
            ))


def _split_select_columns(select_body: str) -> list[str]:
    """Split a SELECT column list by commas, respecting parentheses."""
    parts: list[str] = []
    depth = 0
    current = ""

    for char in select_body:
        if char == "(":
            depth += 1
            current += char
        elif char == ")":
            depth -= 1
            current += char
        elif char == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char

    if current.strip():
        parts.append(current)

    return parts


def _ast_dict_to_dict(node: ast.Dict) -> dict[str, Any]:
    """Convert an AST Dict node to a Python dict (keys as strings)."""
    result: dict[str, Any] = {}

    for key, value in zip(node.keys, node.values):
        if key is None:
            continue
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            if isinstance(value, ast.Constant):
                result[key.value] = value.value
            else:
                result[key.value] = ast.dump(value)

    return result
