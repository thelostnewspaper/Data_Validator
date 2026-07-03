"""
Airflow REST API connector — tests if connections exist and can create them.

Uses Python's built-in urllib to avoid external request package dependencies.
Supports Basic Authentication for the Airflow API.
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
import base64
from typing import Any

logger = logging.getLogger(__name__)


class AirflowApiConnector:
    """
    Airflow REST API connector.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        # Configuration matches VS Code connection profile
        self.url = config.get("host", "").rstrip("/")
        self.username = config.get("username", "")
        self.password = config.get("password", "")

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.username and self.password:
            auth_str = f"{self.username}:{self.password}"
            encoded = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
            headers["Authorization"] = f"Basic {encoded}"
        return headers

    def test_connection(self) -> dict[str, Any]:
        """Test if the Airflow API endpoint is reachable."""
        if not self.url:
            return {"status": "error", "message": "Airflow host URL not configured."}

        # Query Airflow health endpoint
        endpoint = f"{self.url}/api/v1/health"
        req = urllib.request.Request(
            endpoint,
            headers=self.get_headers_no_auth(), # Health is often unauthenticated
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    return {
                        "status": "success",
                        "message": f"Successfully connected to Airflow API. Status: {data.get('metadatabase', {}).get('status', 'OK')}",
                    }
            return {"status": "error", "message": f"Unexpected response status: {response.status}"}
        except Exception as e:
            # Try with auth headers just in case
            try:
                req_auth = urllib.request.Request(
                    endpoint,
                    headers=self._get_headers(),
                )
                with urllib.request.urlopen(req_auth, timeout=5) as response:
                    if response.status == 200:
                        return {"status": "success", "message": "Successfully connected to Airflow API (Authenticated)."}
            except Exception:
                pass
            return {"status": "error", "message": f"Airflow API connection failed: {e}"}

    def connection_exists(self, conn_id: str) -> bool:
        """Check if a specific connection ID exists in Airflow."""
        if not self.url:
            return False

        endpoint = f"{self.url}/api/v1/connections/{conn_id}"
        req = urllib.request.Request(
            endpoint,
            headers=self._get_headers(),
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    return True
            return False
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            logger.error(f"HTTP error checking connection {conn_id}: {e.code} - {e.reason}")
            return False
        except Exception as e:
            logger.error(f"Error checking connection {conn_id} in Airflow: {e}")
            return False

    def create_connection(self, conn_data: dict[str, Any]) -> dict[str, Any]:
        """Create a connection in Airflow via REST API."""
        if not self.url:
            return {"status": "error", "message": "Airflow host URL not configured."}

        endpoint = f"{self.url}/api/v1/connections"
        payload = json.dumps(conn_data).encode("utf-8")
        
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers=self._get_headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status in (200, 201):
                    res_data = json.loads(response.read().decode("utf-8"))
                    return {
                        "status": "success",
                        "message": f"Connection '{res_data.get('connection_id')}' created successfully in Airflow.",
                    }
                return {"status": "error", "message": f"Airflow API returned status {response.status}"}
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8")
                err_json = json.loads(err_body)
                err_detail = err_json.get("detail", err_json.get("title", e.reason))
                return {"status": "error", "message": f"Airflow REST API Error: {err_detail}"}
            except Exception:
                return {"status": "error", "message": f"Airflow REST API returned HTTP {e.code}: {e.reason}"}
        except Exception as e:
            return {"status": "error", "message": f"Failed to create Airflow connection: {e}"}

    @staticmethod
    def get_headers_no_auth() -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
