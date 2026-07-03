"""
Connector base — interface, connection profiles, and caching.

Phase 3 stub. Will provide the shared connector interface for
Doris, BigQuery, Snowflake, and Airflow API connectors.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Connector(Protocol):
    """Protocol for database/API connectors."""

    def test_connection(self) -> dict[str, Any]:
        """Test if the connection is reachable. Returns status dict."""
        ...

    def get_schema(self, table: str) -> dict[str, Any]:
        """Get table schema. Returns column info dict."""
        ...

    def get_columns(self, table: str) -> list[str]:
        """Get column names for a table."""
        ...


def get_connector(params: dict[str, Any]) -> Any:
    """Factory function to return the correct connector instance."""
    conn_type = params.get("type", "").lower()
    if conn_type == "doris":
        from engine.connectors.doris import DorisConnector
        return DorisConnector(params)
    elif conn_type == "bigquery":
        from engine.connectors.bigquery import BigQueryConnector
        return BigQueryConnector(params)
    elif conn_type == "snowflake":
        from engine.connectors.snowflake import SnowflakeConnector
        return SnowflakeConnector(params)
    elif conn_type == "airflow":
        from engine.connectors.airflow_api import AirflowApiConnector
        return AirflowApiConnector(params)
    else:
        raise ValueError(f"Unknown connection type: {conn_type}")


def verify_connection(params: dict[str, Any]) -> dict[str, Any]:
    """
    Test a connection based on the profile parameters.
    """
    try:
        connector = get_connector(params)
        return connector.test_connection()
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
        }
