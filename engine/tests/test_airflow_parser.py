"""Tests for engine/packs/airflow/parser.py — AST extraction from sample DAGs."""

from engine.packs.airflow.parser import (
    parse_dag_file,
    parse_dag_ast,
    extract_source_tables,
    extract_columns_from_sql,
)
from engine.tests.conftest import (
    VALID_DAG,
    SYNTAX_ERROR_DAG,
    CIRCULAR_DEP_DAG,
)


class TestParseDagAst:
    def test_valid_code_parses(self):
        tree, err = parse_dag_ast(VALID_DAG)
        assert tree is not None
        assert err is None

    def test_syntax_error_returns_error(self):
        tree, err = parse_dag_ast(SYNTAX_ERROR_DAG)
        assert tree is None
        assert err is not None
        assert isinstance(err, SyntaxError)


class TestParseDagFile:
    def test_valid_dag_extracts_dag_id(self):
        info = parse_dag_file(VALID_DAG)
        assert info.dag_id == "valid_test_dag"
        assert info.syntax_error is None

    def test_valid_dag_extracts_tasks(self):
        info = parse_dag_file(VALID_DAG)
        task_ids = [t.task_id for t in info.tasks]
        assert "extract_data" in task_ids
        assert "transform_data" in task_ids
        assert "load_data" in task_ids
        assert len(info.tasks) == 3

    def test_valid_dag_extracts_dependencies(self):
        info = parse_dag_file(VALID_DAG)
        assert len(info.dependencies) >= 2

    def test_valid_dag_has_start_date(self):
        info = parse_dag_file(VALID_DAG)
        assert info.has_start_date is True

    def test_valid_dag_has_catchup(self):
        info = parse_dag_file(VALID_DAG)
        assert info.has_catchup is True

    def test_valid_dag_has_schedule(self):
        info = parse_dag_file(VALID_DAG)
        assert info.schedule_param == "schedule"

    def test_syntax_error_dag(self):
        info = parse_dag_file(SYNTAX_ERROR_DAG)
        assert info.syntax_error is not None

    def test_circular_dag_extracts_deps(self):
        info = parse_dag_file(CIRCULAR_DEP_DAG)
        assert len(info.dependencies) >= 3

    def test_extracts_imports(self):
        info = parse_dag_file(VALID_DAG)
        modules = [i.module for i in info.imports]
        assert "airflow" in modules or any("airflow" in m for m in modules)


class TestExtractSourceTables:
    def test_simple_from(self):
        tables = extract_source_tables("SELECT * FROM users")
        assert "users" in tables

    def test_join(self):
        tables = extract_source_tables(
            "SELECT * FROM users JOIN orders ON users.id = orders.user_id"
        )
        assert "users" in tables
        assert "orders" in tables

    def test_schema_prefixed(self):
        tables = extract_source_tables("SELECT * FROM public.users")
        assert "public.users" in tables

    def test_deduplication(self):
        tables = extract_source_tables(
            "SELECT * FROM users JOIN users ON 1=1"
        )
        assert len(tables) == 1


class TestExtractColumnsFromSql:
    def test_simple_select(self):
        cols = extract_columns_from_sql("SELECT id, name, email FROM users")
        col_names = [c[0] for c in cols]
        assert "id" in col_names
        assert "name" in col_names
        assert "email" in col_names

    def test_with_alias(self):
        cols = extract_columns_from_sql(
            "SELECT id, user_name AS name FROM users"
        )
        col_names = [c[0] for c in cols]
        assert "id" in col_names
        # Should extract the original column name, not the alias
        assert "user_name" in col_names

    def test_with_table_prefix(self):
        cols = extract_columns_from_sql(
            "SELECT u.id, u.name FROM users u"
        )
        col_names = [c[0] for c in cols]
        assert "id" in col_names
        assert "name" in col_names
