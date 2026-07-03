"""
JSON-RPC server — the entry point the extension spawns.

A thin JSON-RPC 2.0 loop over stdio with Content-Length header framing,
compatible with vscode-jsonrpc. Each method delegates to the registry
or AI remediator.

Usage:
    python -u engine/server.py

All logging goes to stderr (stdout is the RPC channel).
"""

from __future__ import annotations

import json
import sys
import logging
import traceback
from typing import Any

from engine.protocol import Methods
from engine.core.registry import get_registry, register_all_packs
from engine.core.models import CheckResult, CheckStatus, CheckCategory

# ---------------------------------------------------------------------------
# Logging — MUST go to stderr, stdout is the JSON-RPC channel
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="[ai-validator] %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("server")


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 over stdio with Content-Length framing
# ---------------------------------------------------------------------------

def _read_message() -> dict[str, Any] | None:
    """
    Read a single JSON-RPC message from stdin.

    Expects Content-Length header framing:
        Content-Length: <n>\r\n
        \r\n
        <json body of n bytes>
    """
    # Read headers
    content_length = -1
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None  # EOF

        line_str = line.decode("utf-8").strip()
        if not line_str:
            break  # End of headers

        if line_str.lower().startswith("content-length:"):
            content_length = int(line_str.split(":", 1)[1].strip())

    if content_length < 0:
        return None

    # Read the body
    body = sys.stdin.buffer.read(content_length)
    if not body:
        return None

    return json.loads(body.decode("utf-8"))


def _write_message(msg: dict[str, Any]) -> None:
    """
    Write a JSON-RPC message to stdout with Content-Length framing.
    """
    body = json.dumps(msg, ensure_ascii=False)
    body_bytes = body.encode("utf-8")
    header = f"Content-Length: {len(body_bytes)}\r\n\r\n"

    sys.stdout.buffer.write(header.encode("utf-8"))
    sys.stdout.buffer.write(body_bytes)
    sys.stdout.buffer.flush()


def _make_response(id: Any, result: Any) -> dict[str, Any]:
    """Create a JSON-RPC success response."""
    return {
        "jsonrpc": "2.0",
        "id": id,
        "result": result,
    }


def _make_error(id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    """Create a JSON-RPC error response."""
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {
        "jsonrpc": "2.0",
        "id": id,
        "error": error,
    }


def _send_notification(method: str, params: Any) -> None:
    """Send a JSON-RPC notification (no id, no response expected)."""
    _write_message({
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
    })


# ---------------------------------------------------------------------------
# Method handlers
# ---------------------------------------------------------------------------

def _handle_validate(params: dict[str, Any]) -> dict[str, Any]:
    """Handle the 'validate' method."""
    file_path = params.get("file_path", "")
    content = params.get("content", "")
    connections = params.get("connections")
    enabled_packs = params.get("enabled_packs")

    registry = get_registry()
    result = registry.validate(
        file_path=file_path,
        content=content,
        connections=connections,
        enabled_packs=enabled_packs,
    )

    return result.to_dict()


def _handle_get_packs(_params: dict[str, Any]) -> dict[str, Any]:
    """Handle the 'getPacks' method."""
    registry = get_registry()
    return {"packs": registry.get_packs()}


def _handle_ai_remediate(params: dict[str, Any], request_id: Any) -> dict[str, Any]:
    """
    Handle the 'aiRemediate' method.

    This is a streaming method — it sends notifications as variants are
    generated, then returns the final result.
    """
    try:
        from engine.ai.remediator import remediate

        file_path = params.get("file_path", "")
        content = params.get("content", "")
        checks_data = params.get("checks", [])
        fixes_data = params.get("fixes", [])
        api_key = params.get("api_key", "")
        provider = params.get("provider", "claude")
        model = params.get("model", "")

        # Reconstruct CheckResult objects from dicts
        checks = []
        for cd in checks_data:
            checks.append(CheckResult(
                id=cd.get("id", ""),
                status=CheckStatus(cd.get("status", "fail")),
                category=CheckCategory(cd.get("category", "syntax")),
                message=cd.get("message", ""),
                detail=cd.get("detail", ""),
                line=cd.get("line", 0),
                column=cd.get("column", 0),
            ))

        # Stream remediation options
        for option in remediate(
            file_path=file_path,
            content=content,
            checks=checks,
            fixes_data=fixes_data,
            api_key=api_key,
            provider=provider,
            model=model,
        ):
            _send_notification(
                Methods.AI_REMEDIATE_STREAM,
                {**option.to_dict(), "status": "complete" if not option.failed else "error"},
            )

        _send_notification(Methods.AI_REMEDIATE_DONE, {"status": "done"})
        return {"status": "done"}

    except ImportError:
        return {"status": "error", "message": "AI remediation module not available. Install the 'anthropic' package."}
    except Exception as e:
        logger.error(f"AI remediation error: {e}\n{traceback.format_exc()}")
        _send_notification(
            Methods.AI_REMEDIATE_ERROR,
            {"status": "error", "message": str(e)},
        )
        return {"status": "error", "message": str(e)}


def _handle_check_connection(params: dict[str, Any]) -> dict[str, Any]:
    """Handle the 'checkConnection' method."""
    try:
        from engine.connectors.base import verify_connection
        return verify_connection(params)
    except ImportError:
        return {"status": "error", "message": "Connector module not available."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _handle_shutdown(_params: dict[str, Any]) -> dict[str, Any]:
    """Handle the 'shutdown' method."""
    logger.info("Shutdown requested")
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Method dispatch table
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, Any] = {
    Methods.VALIDATE: _handle_validate,
    Methods.GET_PACKS: _handle_get_packs,
    Methods.CHECK_CONNECTION: _handle_check_connection,
    Methods.SHUTDOWN: _handle_shutdown,
    # AI remediate is special — needs the request_id for streaming
}


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the JSON-RPC server loop."""
    logger.info("AI Validator engine starting...")

    # Register all built-in packs
    register_all_packs()

    logger.info("Engine ready. Listening for JSON-RPC messages on stdin.")

    # Send initialized notification
    _send_notification(Methods.INITIALIZED, {"status": "ready"})

    while True:
        try:
            msg = _read_message()
            if msg is None:
                logger.info("EOF on stdin, shutting down.")
                break

            method = msg.get("method", "")
            params = msg.get("params", {})
            request_id = msg.get("id")

            logger.info(f"Received: method={method}, id={request_id}")

            # Notifications (no id) — just log
            if request_id is None:
                logger.info(f"Notification: {method}")
                continue

            # Special handling for AI remediate (streaming)
            if method == Methods.AI_REMEDIATE:
                result = _handle_ai_remediate(params, request_id)
                _write_message(_make_response(request_id, result))
                continue

            # Shutdown — respond and exit
            if method == Methods.SHUTDOWN:
                _write_message(_make_response(request_id, {"status": "ok"}))
                break

            # Normal dispatch
            handler = _HANDLERS.get(method)
            if handler is None:
                _write_message(
                    _make_error(request_id, -32601, f"Method not found: {method}")
                )
                continue

            result = handler(params)
            _write_message(_make_response(request_id, result))

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
        except Exception as e:
            logger.error(f"Unhandled error: {e}\n{traceback.format_exc()}")
            if "request_id" in dir() and request_id is not None:
                _write_message(
                    _make_error(request_id, -32603, f"Internal error: {e}")
                )


if __name__ == "__main__":
    main()
