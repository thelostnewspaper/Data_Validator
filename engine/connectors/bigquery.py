"""
BigQuery connector — tests connections and fetches metadata using google-cloud-bigquery.

Safe to import even if google-cloud-bigquery is not installed.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class BigQueryConnector:
    """
    BigQuery connector using google-cloud-bigquery.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        # Config may include credentials, project_id, dataset, etc.
        self.project = config.get("database") or config.get("project_id", "")
        self.dataset = config.get("schema") or config.get("dataset_id", "")

    def _get_client(self) -> Any:
        try:
            from google.cloud import bigquery
        except ImportError:
            raise ImportError(
                "The 'google-cloud-bigquery' package is required for BigQuery checks. "
                "Install it in your active environment."
            )

        # Initialize BigQuery client. Will pick up credentials from the environment
        # or defaults.
        return bigquery.Client(project=self.project)

    def test_connection(self) -> dict[str, Any]:
        """Test if BigQuery is reachable."""
        try:
            client = self._get_client()
            # Simple metadata query to test client auth and connectivity
            client.list_datasets(max_results=1)
            return {"status": "success", "message": "Successfully authenticated to BigQuery."}
        except Exception as e:
            return {"status": "error", "message": f"BigQuery connection failed: {e}"}

    def get_columns(self, table: str) -> list[str]:
        """Fetch columns from BigQuery for the given table."""
        try:
            client = self._get_client()
            # If dataset is set and table is not schema-qualified, prefix it
            table_ref = table
            if self.dataset and "." not in table:
                table_ref = f"{self.dataset}.{table}"
            if self.project and table_ref.count(".") == 1:
                table_ref = f"{self.project}.{table_ref}"

            table_obj = client.get_table(table_ref)
            return [field.name for field in table_obj.schema]
        except Exception as e:
            logger.error(f"Error fetching columns for BigQuery table {table}: {e}")
            return []
