"""
Airflow live checks — Layer 2, requires network connections.

Queries Doris, BigQuery, Snowflake, and Airflow APIs using the configured
connection profiles to validate tables, columns, and connection IDs.
"""

from __future__ import annotations

import logging
from typing import Any

from engine.core.models import CheckResult, CheckStatus, CheckCategory
from engine.core.fixes import fuzzy_match_column
from engine.connectors.base import get_connector
from engine.packs.airflow.parser import parse_dag_file, extract_source_tables, extract_columns_from_sql

logger = logging.getLogger(__name__)


def run_all_live_checks(
    file_path: str,
    content: str,
    connections: dict[str, Any],
) -> list[CheckResult]:
    """
    Run all Layer 2 live checks on a DAG file.

    Args:
        file_path:   Absolute path to the file.
        content:     Full file content.
        connections: Dict of connection profiles keyed by name.

    Returns:
        List of check results from live validation.
    """
    results: list[CheckResult] = []

    dag_info = parse_dag_file(content)

    # 1. Check database reachability
    results.extend(check_database_reachable(connections))

    # 2. Check table and column existence against live databases
    results.extend(check_tables_and_columns(dag_info, connections))

    # 3. Check Airflow connections against Airflow REST API
    results.extend(check_airflow_connections(dag_info, connections))

    return results


def check_database_reachable(
    connections: dict[str, Any],
) -> list[CheckResult]:
    """AFW_LIVE_001 — Target database reachable."""
    results: list[CheckResult] = []

    for name, profile in connections.items():
        conn_type = profile.get("type", "unknown")
        try:
            connector = get_connector(profile)
            test_res = connector.test_connection()
            if test_res.get("status") == "success":
                results.append(CheckResult(
                    id="AFW_LIVE_001",
                    status=CheckStatus.PASS,
                    category=CheckCategory.CONNECTIONS,
                    message=f"Connection '{name}' ({conn_type}) is reachable.",
                    source_rule="Target database reachable",
                ))
            else:
                results.append(CheckResult(
                    id="AFW_LIVE_001",
                    status=CheckStatus.WARN,
                    category=CheckCategory.CONNECTIONS,
                    message=f"Connection '{name}' ({conn_type}) is offline/unreachable.",
                    detail=test_res.get("message", "No error details provided."),
                    source_rule="Target database reachable",
                ))
        except Exception as e:
            results.append(CheckResult(
                id="AFW_LIVE_001",
                status=CheckStatus.WARN,
                category=CheckCategory.CONNECTIONS,
                message=f"Could not check connection '{name}': {e}",
                source_rule="Target database reachable",
            ))

    return results


def check_tables_and_columns(
    dag_info: Any,
    connections: dict[str, Any],
) -> list[CheckResult]:
    """
    AFW_LIVE_002 — Target table exists.
    AFW_LIVE_003 — Columns exist in target (with fuzzy match).
    """
    results: list[CheckResult] = []

    for frag in dag_info.sql_fragments:
        # Determine connector type based on operator class
        op = frag.operator.lower()
        conn_type = None
        if "bigquery" in op:
            conn_type = "bigquery"
        elif "snowflake" in op:
            conn_type = "snowflake"
        elif "mysql" in op or "doris" in op:
            conn_type = "doris"

        # Find matching profile
        profile = None
        for p_name, p_profile in connections.items():
            p_type = p_profile.get("type", "").lower()
            if conn_type and p_type == conn_type:
                profile = p_profile
                break
            elif not conn_type and p_type in ("doris", "bigquery", "snowflake"):
                # If only one database profile is defined, default to it
                profile = p_profile

        if not profile:
            continue

        try:
            connector = get_connector(profile)
            tables = extract_source_tables(frag.sql)

            for table in tables:
                # Query columns
                db_cols = connector.get_columns(table)
                if not db_cols:
                    results.append(CheckResult(
                        id="AFW_LIVE_002",
                        status=CheckStatus.WARN,
                        category=CheckCategory.COLUMNS,
                        message=f"Table '{table}' not found or has no columns in target database",
                        detail=f"Could not retrieve columns for table '{table}' in task '{frag.task_id}'.",
                        line=frag.line,
                        source_rule="Target table exists",
                    ))
                    continue

                # Table exists!
                results.append(CheckResult(
                    id="AFW_LIVE_002",
                    status=CheckStatus.PASS,
                    category=CheckCategory.COLUMNS,
                    message=f"Table '{table}' exists in target database",
                    line=frag.line,
                    source_rule="Target table exists",
                ))

                # Verify columns
                select_cols = extract_columns_from_sql(frag.sql)
                db_cols_lower = [c.lower() for c in db_cols]

                for col, pos in select_cols:
                    if col.lower() not in db_cols_lower:
                        # Find fuzzy matches
                        matches = fuzzy_match_column(col, db_cols, threshold=0.80)
                        suggestion = ""
                        if matches:
                            suggestion = f" Did you mean '{matches[0][0]}'?"

                        results.append(CheckResult(
                            id="AFW_LIVE_003",
                            status=CheckStatus.FAIL,
                            category=CheckCategory.COLUMNS,
                            message=f"Column '{col}' does not exist in table '{table}'.{suggestion}",
                            detail=(
                                f"Task '{frag.task_id}' queries column '{col}' from table '{table}', "
                                f"but this column was not found in the target database schema.\n\n"
                                f"Available columns: {', '.join(db_cols[:15])}"
                                + ("..." if len(db_cols) > 15 else "")
                            ),
                            line=frag.line,
                            column=pos,
                            source_rule="Columns exist in target",
                        ))
                    else:
                        results.append(CheckResult(
                            id="AFW_LIVE_003",
                            status=CheckStatus.PASS,
                            category=CheckCategory.COLUMNS,
                            message=f"Column '{col}' exists in table '{table}'",
                            line=frag.line,
                            source_rule="Columns exist in target",
                        ))

        except Exception as e:
            logger.error(f"Failed live check for task {frag.task_id}: {e}")
            results.append(CheckResult(
                id="AFW_LIVE_002",
                status=CheckStatus.WARN,
                category=CheckCategory.COLUMNS,
                message=f"Failed to query database schema for live checks: {e}",
                line=frag.line,
                source_rule="Target table exists",
            ))

    return results


def check_airflow_connections(
    dag_info: Any,
    connections: dict[str, Any],
) -> list[CheckResult]:
    """AFW_LIVE_004 — Airflow connection conn_id exists."""
    results: list[CheckResult] = []

    # Find Airflow REST API profile in connections
    airflow_profile = None
    for p_name, p_profile in connections.items():
        if p_profile.get("type", "").lower() == "airflow":
            airflow_profile = p_profile
            break

    if not airflow_profile:
        return []

    try:
        connector = get_connector(airflow_profile)

        # Extract connection references from task kwargs
        referenced_conns: set[str] = set()
        conn_kwarg_names = {
            "mysql_conn_id", "postgres_conn_id", "gcp_conn_id", "snowflake_conn_id",
            "conn_id", "ssh_conn_id", "http_conn_id", "aws_conn_id", "slack_conn_id"
        }

        for task in dag_info.tasks:
            for kwarg, val_expr in task.kwargs.items():
                if kwarg in conn_kwarg_names:
                    # Parse constant string value if possible
                    # ast.dump of Constant is: "Constant(value='my_conn')"
                    import re
                    match = re.search(r"value='([^']+)'", val_expr)
                    if match:
                        referenced_conns.add(match.group(1))

        for conn_id in referenced_conns:
            exists = connector.connection_exists(conn_id)
            if exists:
                results.append(CheckResult(
                    id="AFW_LIVE_004",
                    status=CheckStatus.PASS,
                    category=CheckCategory.CONNECTIONS,
                    message=f"Airflow connection '{conn_id}' exists.",
                    source_rule="Airflow connection exists",
                ))
            else:
                results.append(CheckResult(
                    id="AFW_LIVE_004",
                    status=CheckStatus.WARN,
                    category=CheckCategory.CONNECTIONS,
                    message=f"Airflow connection '{conn_id}' does not exist in target environment",
                    detail=(
                        f"The Airflow DAG references connection ID '{conn_id}', "
                        f"but this connection is missing from the configured Airflow instance."
                    ),
                    source_rule="Airflow connection exists",
                ))

    except Exception as e:
        logger.error(f"Failed to check Airflow connections: {e}")

    return results
