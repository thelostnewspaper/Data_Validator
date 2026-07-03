"""
Doris connector — tests connections and fetches metadata using PyMySQL.

Safe to import even if pymysql is not installed.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class DorisConnector:
    """
    Doris database connector using pymysql.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.host = config.get("host", "localhost")
        self.port = int(config.get("port", 9030))
        self.database = config.get("database", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")

    def _get_connection(self) -> Any:
        try:
            import pymysql
        except ImportError:
            raise ImportError(
                "The 'pymysql' package is required for Doris checks. "
                "Install it in your active environment."
            )

        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.username,
            password=self.password,
            database=self.database,
            connect_timeout=5,
        )

    def test_connection(self) -> dict[str, Any]:
        """Test if Doris is reachable."""
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
            return {"status": "success", "message": "Successfully connected to Doris."}
        except Exception as e:
            return {"status": "error", "message": f"Doris connection failed: {e}"}
        finally:
            if conn:
                conn.close()

    def get_columns(self, table: str) -> list[str]:
        """Fetch columns from Doris for the given table."""
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                # Basic protection for table name injection
                if not table.replace(".", "_").replace("_", "").isalnum():
                    raise ValueError(f"Invalid table name format: {table}")
                
                cursor.execute(f"SHOW COLUMNS FROM {table}")
                rows = cursor.fetchall()
                # SHOW COLUMNS returns: Field, Type, Null, Key, Default, Extra
                return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Error fetching columns for table {table}: {e}")
            return []
        finally:
            if conn:
                conn.close()
