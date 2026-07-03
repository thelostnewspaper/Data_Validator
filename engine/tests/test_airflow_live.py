"""Tests for Airflow Layer 2 live checks."""

import pytest
from unittest.mock import MagicMock, patch
from engine.core.models import CheckStatus
from engine.packs.airflow.live_checks import run_all_live_checks


@pytest.fixture
def mock_connections():
    return {
        "my_doris": {
            "type": "doris",
            "host": "localhost",
            "port": 9030,
            "database": "db"
        },
        "my_airflow": {
            "type": "airflow",
            "host": "http://localhost:8080"
        }
    }


class TestAirflowLiveChecks:
    @patch("engine.packs.airflow.live_checks.get_connector")
    def test_run_all_live_checks_success(self, mock_get_connector, mock_connections):
        # Setup mocks
        mock_db_connector = MagicMock()
        mock_db_connector.test_connection.return_value = {"status": "success"}
        mock_db_connector.get_columns.return_value = ["id", "name", "email", "status"]

        mock_airflow_connector = MagicMock()
        mock_airflow_connector.test_connection.return_value = {"status": "success"}
        mock_airflow_connector.connection_exists.return_value = True

        def get_connector_side_effect(profile):
            if profile["type"] == "doris":
                return mock_db_connector
            elif profile["type"] == "airflow":
                return mock_airflow_connector
            return MagicMock()

        mock_get_connector.side_effect = get_connector_side_effect

        # Sample SQL with column matching the mocked DB columns
        dag_content = """
from datetime import datetime
from airflow import DAG
from airflow.providers.mysql.operators.mysql import MySqlOperator

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 1, 1),
}

with DAG('test_live_dag', default_args=default_args, catchup=False) as dag:
    task = MySqlOperator(
        task_id='query',
        sql="SELECT id, name FROM users",
        mysql_conn_id='my_doris',
    )
"""

        results = run_all_live_checks("/test.py", dag_content, mock_connections)
        
        # Verify database reachable (AFW_LIVE_001)
        reachable = [c for c in results if c.id == "AFW_LIVE_001"]
        assert len(reachable) == 2
        assert all(c.status == CheckStatus.PASS for c in reachable)

        # Verify table exists (AFW_LIVE_002)
        table_exists = [c for c in results if c.id == "AFW_LIVE_002"]
        assert len(table_exists) == 1
        assert table_exists[0].status == CheckStatus.PASS
        assert "users" in table_exists[0].message

        # Verify columns exist (AFW_LIVE_003)
        cols_exist = [c for c in results if c.id == "AFW_LIVE_003"]
        assert len(cols_exist) == 2
        assert all(c.status == CheckStatus.PASS for c in cols_exist)

        # Verify Airflow connection exists (AFW_LIVE_004)
        conn_exists = [c for c in results if c.id == "AFW_LIVE_004"]
        assert len(conn_exists) == 1
        assert conn_exists[0].status == CheckStatus.PASS
        assert "my_doris" in conn_exists[0].message


    @patch("engine.packs.airflow.live_checks.get_connector")
    def test_run_all_live_checks_column_missing_with_fuzzy(self, mock_get_connector, mock_connections):
        # Setup mocks
        mock_db_connector = MagicMock()
        mock_db_connector.test_connection.return_value = {"status": "success"}
        mock_db_connector.get_columns.return_value = ["id", "item_name", "price"]

        mock_airflow_connector = MagicMock()
        mock_airflow_connector.test_connection.return_value = {"status": "success"}

        mock_get_connector.side_effect = lambda profile: mock_db_connector if profile["type"] == "doris" else mock_airflow_connector

        # Query uses 'item_nam' which is a typo for 'item_name'
        dag_content = """
from datetime import datetime
from airflow import DAG
from airflow.providers.mysql.operators.mysql import MySqlOperator

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 1, 1),
}

with DAG('test_live_dag', default_args=default_args, catchup=False) as dag:
    task = MySqlOperator(
        task_id='query',
        sql="SELECT id, item_nam FROM products",
        mysql_conn_id='my_doris',
    )
"""

        results = run_all_live_checks("/test.py", dag_content, mock_connections)
        
        # Verify table exists is PASS
        table_exists = [c for c in results if c.id == "AFW_LIVE_002"]
        assert table_exists[0].status == CheckStatus.PASS

        # Verify column checks: id is PASS, item_nam is FAIL with suggestion
        col_checks = [c for c in results if c.id == "AFW_LIVE_003"]
        assert len(col_checks) == 2
        
        failed_col = [c for c in col_checks if c.status == CheckStatus.FAIL][0]
        assert "item_nam" in failed_col.message
        assert "item_name" in failed_col.message  # Suggestion
