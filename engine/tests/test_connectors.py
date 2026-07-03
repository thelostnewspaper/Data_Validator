"""Tests for database and API connectors using direct module mocks."""

import sys
from unittest.mock import MagicMock

# 1. Mock out PyMySQL
mock_pymysql = MagicMock()
sys.modules["pymysql"] = mock_pymysql

# 2. Mock out BigQuery (requires nested package mock)
mock_bigquery = MagicMock()
sys.modules["google.cloud.bigquery"] = mock_bigquery

mock_google_cloud = MagicMock()
mock_google_cloud.bigquery = mock_bigquery
sys.modules["google.cloud"] = mock_google_cloud

mock_google = MagicMock()
mock_google.cloud = mock_google_cloud
sys.modules["google"] = mock_google

# 3. Mock out Snowflake
mock_snowflake = MagicMock()
mock_snowflake_pkg = MagicMock()
mock_snowflake_pkg.connector = mock_snowflake
sys.modules["snowflake"] = mock_snowflake_pkg
sys.modules["snowflake.connector"] = mock_snowflake

import pytest
from unittest.mock import patch
from engine.connectors.base import verify_connection, get_connector
from engine.connectors.doris import DorisConnector
from engine.connectors.bigquery import BigQueryConnector
from engine.connectors.snowflake import SnowflakeConnector
from engine.connectors.airflow_api import AirflowApiConnector


class TestDorisConnector:
    def test_test_connection_success(self):
        mock_conn = MagicMock()
        mock_pymysql.connect.return_value = mock_conn
        
        connector = DorisConnector({
            "host": "localhost",
            "port": 9030,
            "username": "root",
            "password": "pwd",
            "database": "db"
        })
        res = connector.test_connection()
        assert res["status"] == "success"
        mock_pymysql.connect.assert_called_with(
            host="localhost",
            port=9030,
            user="root",
            password="pwd",
            database="db",
            connect_timeout=5
        )

    def test_get_columns(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [("id",), ("name",)]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_pymysql.connect.return_value = mock_conn

        connector = DorisConnector({"database": "db"})
        cols = connector.get_columns("users")
        assert cols == ["id", "name"]
        mock_cursor.execute.assert_called_with("SHOW COLUMNS FROM users")


class TestBigQueryConnector:
    def test_test_connection(self):
        mock_client = MagicMock()
        mock_bigquery.Client.return_value = mock_client

        connector = BigQueryConnector({"project_id": "proj"})
        res = connector.test_connection()
        assert res["status"] == "success"
        mock_client.list_datasets.assert_called_once()

    def test_get_columns(self):
        mock_client = MagicMock()
        mock_table = MagicMock()
        field_id = MagicMock()
        field_id.name = "id"
        field_name = MagicMock()
        field_name.name = "name"
        mock_table.schema = [field_id, field_name]
        mock_client.get_table.return_value = mock_table
        mock_bigquery.Client.return_value = mock_client

        connector = BigQueryConnector({"project_id": "proj", "dataset_id": "ds"})
        cols = connector.get_columns("users")
        assert cols == ["id", "name"]
        mock_client.get_table.assert_called_once_with("proj.ds.users")


class TestSnowflakeConnector:
    def test_test_connection(self):
        mock_conn = MagicMock()
        mock_snowflake.connect.return_value = mock_conn

        connector = SnowflakeConnector({
            "host": "acct",
            "username": "user",
            "password": "pwd",
            "database": "db"
        })
        res = connector.test_connection()
        assert res["status"] == "success"

    def test_get_columns(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [("ID",), ("NAME",)]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_snowflake.connect.return_value = mock_conn

        connector = SnowflakeConnector({
            "host": "acct",
            "username": "user",
            "database": "db",
            "schema": "public"
        })
        cols = connector.get_columns("users")
        assert cols == ["ID", "NAME"]


class TestAirflowApiConnector:
    @patch("urllib.request.urlopen")
    def test_connection_exists(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response

        connector = AirflowApiConnector({
            "host": "http://localhost:8080",
            "username": "admin",
            "password": "admin_password"
        })
        exists = connector.connection_exists("my_conn")
        assert exists is True
        
        args, kwargs = mock_urlopen.call_args
        req = args[0]
        assert req.get_header("Authorization").startswith("Basic ")


class TestBaseConnectorVerification:
    def test_verify_connection_doris(self):
        mock_conn = MagicMock()
        mock_pymysql.connect.return_value = mock_conn

        params = {
            "type": "doris",
            "host": "localhost",
            "port": 9030,
            "username": "root",
            "password": "pwd",
            "database": "db"
        }
        res = verify_connection(params)
        assert res["status"] == "success"
