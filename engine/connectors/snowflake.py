"""
Snowflake connector — tests connections and fetches metadata using snowflake-connector-python.

Safe to import even if snowflake-connector-python is not installed.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SnowflakeConnector:
    """
    Snowflake connector using snowflake-connector-python.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.account = config.get("host", "")  # Or account name
        self.user = config.get("username", "")
        self.password = config.get("password", "")
        self.database = config.get("database", "")
        self.schema = config.get("schema", "PUBLIC")
        self.warehouse = config.get("warehouse", "")

    def _get_connection(self) -> Any:
        try:
            import snowflake.connector
        except ImportError:
            raise ImportError(
                "The 'snowflake-connector-python' package is required for Snowflake checks. "
                "Install it in your active environment."
            )

        return snowflake.connector.connect(
            account=self.account,
            user=self.user,
            password=self.password,
            database=self.database,
            schema=self.schema,
            warehouse=self.warehouse,
            login_timeout=10,
        )

    def test_connection(self) -> dict[str, Any]:
        """Test connection to Snowflake."""
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
            return {"status": "success", "message": "Successfully connected to Snowflake."}
        except Exception as e:
            return {"status": "error", "message": f"Snowflake connection failed: {e}"}
        finally:
            if conn:
                conn.close()

    def get_columns(self, table: str) -> list[str]:
        """Fetch columns from Snowflake database for the given table."""
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                # Basic protection for table name injection
                cleaned_table = table.upper().replace('"', '').replace("'", "")
                
                # Check if it has schema prefix
                parts = cleaned_table.split('.')
                if len(parts) == 1:
                    schema_name = self.schema.upper()
                    table_name = parts[0]
                elif len(parts) == 2:
                    schema_name = parts[0]
                    table_name = parts[1]
                else:
                    # Database.Schema.Table
                    schema_name = parts[1]
                    table_name = parts[2]

                query = """
                    SELECT COLUMN_NAME 
                    FROM INFORMATION_SCHEMA.COLUMNS 
                    WHERE TABLE_NAME = %s AND TABLE_SCHEMA = %s
                    ORDER BY ORDINAL_POSITION
                """
                cursor.execute(query, (table_name, schema_name))
                rows = cursor.fetchall()
                return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Error fetching Snowflake columns for {table}: {e}")
            return []
        finally:
            if conn:
                conn.close()
