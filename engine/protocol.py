"""
JSON-RPC protocol definitions — the single source of truth.

Defines method names and request/response shapes for the stdio JSON-RPC
interface between the TypeScript extension host and the Python engine.

The TypeScript types.ts mirrors these definitions.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Method names
# ---------------------------------------------------------------------------

class Methods:
    """JSON-RPC method names."""

    # Core validation
    VALIDATE = "validate"
    GET_PACKS = "getPacks"

    # AI remediation (streaming)
    AI_REMEDIATE = "aiRemediate"

    # Streaming notifications (engine → extension)
    AI_REMEDIATE_STREAM = "aiRemediate/stream"
    AI_REMEDIATE_DONE = "aiRemediate/done"
    AI_REMEDIATE_ERROR = "aiRemediate/error"

    # Connection management
    CHECK_CONNECTION = "checkConnection"
    CREATE_AIRFLOW_CONNECTION = "createAirflowConnection"

    # Lifecycle
    SHUTDOWN = "shutdown"
    INITIALIZED = "initialized"


# ---------------------------------------------------------------------------
# Request / Response schemas (as dicts for documentation; actual validation
# happens via the dataclass models)
# ---------------------------------------------------------------------------

VALIDATE_REQUEST_SCHEMA = {
    "type": "object",
    "properties": {
        "file_path": {"type": "string"},
        "content": {"type": "string"},
        "connections": {
            "type": "object",
            "additionalProperties": True,
        },
        "enabled_packs": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["file_path", "content"],
}

VALIDATE_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "file_path": {"type": "string"},
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "status": {"type": "string", "enum": ["pass", "warn", "fail"]},
                    "category": {"type": "string"},
                    "message": {"type": "string"},
                    "detail": {"type": "string"},
                    "line": {"type": "integer"},
                    "column": {"type": "integer"},
                    "end_line": {"type": "integer"},
                    "end_column": {"type": "integer"},
                    "source_rule": {"type": "string"},
                },
            },
        },
        "fixes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "check_id": {"type": "string"},
                    "description": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"},
                    "diff": {"type": "string"},
                    "confidence": {"type": "number"},
                    "line": {"type": "integer"},
                    "column": {"type": "integer"},
                },
            },
        },
        "connection_fixes": {"type": "array"},
        "summary": {
            "type": "object",
            "properties": {
                "total": {"type": "integer"},
                "passed": {"type": "integer"},
                "warnings": {"type": "integer"},
                "failures": {"type": "integer"},
            },
        },
    },
}

AI_REMEDIATE_REQUEST_SCHEMA = {
    "type": "object",
    "properties": {
        "file_path": {"type": "string"},
        "content": {"type": "string"},
        "checks": {"type": "array"},
        "fixes": {"type": "array"},
        "api_key": {"type": "string"},
        "provider": {"type": "string"},
        "model": {"type": "string"},
        "connections": {"type": "object"},
    },
    "required": ["file_path", "content", "checks", "api_key"],
}

AI_REMEDIATE_STREAM_SCHEMA = {
    "type": "object",
    "properties": {
        "impact": {"type": "string", "enum": ["low", "medium", "high"]},
        "title": {"type": "string"},
        "root_cause": {"type": "string"},
        "fix_explanation": {"type": "string"},
        "dag_code": {"type": "string"},
        "diff": {"type": "string"},
        "failed": {"type": "boolean"},
        "failure_reason": {"type": "string"},
        "status": {"type": "string", "enum": ["streaming", "complete", "error"]},
    },
}

GET_PACKS_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "packs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                },
            },
        },
    },
}

CHECK_CONNECTION_REQUEST_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "type": {"type": "string"},
        "host": {"type": "string"},
        "port": {"type": "integer"},
        "database": {"type": "string"},
        "username": {"type": "string"},
        "password": {"type": "string"},
    },
    "required": ["name", "type", "host"],
}
