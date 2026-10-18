
import hashlib
import json
import os
import re
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

app = FastAPI(
    title="Exam MCP Server",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

REGISTERED_EMAIL = "23f3001817@ds.study.iitm.ac.in"
TOOL_NAME = "solve_challenge"

SUPPORTED_PROTOCOL_VERSIONS = {
    "2024-11-05",
    "2025-03-26",
    "2025-06-18",
    "2025-11-25",
}

CHALLENGE_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def jsonrpc_result(request_id: Any, result: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result,
    }


def jsonrpc_error(
    request_id: Any,
    code: int,
    message: str,
) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }


def make_tool_result(text: str, is_error: bool = False) -> dict:
    return {
        "content": [
            {
                "type": "text",
                "text": text,
            }
        ],
        "isError": is_error,
    }


def handle_initialize(params: dict) -> dict:
    requested_version = params.get("protocolVersion", "2025-03-26")

    # Negotiate a version supported by both sides.
    if requested_version in SUPPORTED_PROTOCOL_VERSIONS:
        negotiated_version = requested_version
    else:
        negotiated_version = "2025-03-26"

    return {
        "protocolVersion": negotiated_version,
        "capabilities": {
            "tools": {
                "listChanged": False,
            }
        },
        "serverInfo": {
            "name": "exam-challenge-mcp",
            "version": "1.0.0",
        },
        "instructions": "Call solve_challenge to solve the current request.",
    }


def handle_tools_list() -> dict:
    # Exactly one tool, with no required input properties.
    return {
        "tools": [
            {
                "name": TOOL_NAME,
                "description": (
                    "Returns the first 16 lowercase hexadecimal "
                    "characters of SHA-256(challenge:registered_email). "
                    "The challenge is read from the current HTTP request "
                    "header X-Exam-Challenge."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": True,
                },
            }
        ]
    }


async def handle_tools_call(
    params: dict,
    request: Request,
) -> dict:
    name = params.get("name")

    if name != TOOL_NAME:
        return make_tool_result(
            f"Unknown tool: {name}",
            is_error=True,
        )

    # The challenge MUST come from this HTTP request's headers.
    # Never use a challenge supplied in params.arguments.
    challenge = request.headers.get("x-exam-challenge", "")

    if not CHALLENGE_PATTERN.fullmatch(challenge):
        return make_tool_result(
            "Missing or invalid X-Exam-Challenge header.",
            is_error=True,
        )

    normalized_email = REGISTERED_EMAIL.strip().lower()
    message = f"{challenge}:{normalized_email}"

    digest = hashlib.sha256(message.encode("utf-8")).hexdigest()
    answer = digest[:16]

    # A successful MCP tool call returns one text content block.
    return make_tool_result(answer)


async def dispatch(message: dict, request: Request):
    if not isinstance(message, dict):
        return JSONResponse(
            jsonrpc_error(None, -32600, "Invalid Request"),
            status_code=400,
        )

    if message.get("jsonrpc") != "2.0":
        return JSONResponse(
            jsonrpc_error(
                message.get("id"),
                -32600,
                "Invalid Request",
            ),
            status_code=400,
        )

    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    if not isinstance(params, dict):
        return JSONResponse(
            jsonrpc_error(request_id, -32602, "Invalid params"),
            status_code=200,
        )

    # Notifications must not receive JSON-RPC result/error bodies.
    is_notification = "id" not in message

    if method == "notifications/initialized":
        return Response(status_code=202)

    if method == "notifications/cancelled":
        return Response(status_code=202)

    if is_notification:
        # Other valid notifications are acknowledged without a body.
        return Response(status_code=202)

    if method == "initialize":
        return JSONResponse(
            jsonrpc_result(request_id, handle_initialize(params))
        )

    if method == "ping":
        return JSONResponse(jsonrpc_result(request_id, {}))

    if method == "tools/list":
        return JSONResponse(
            jsonrpc_result(request_id, handle_tools_list())
        )

    if method == "tools/call":
        result = await handle_tools_call(params, request)
        return JSONResponse(jsonrpc_result(request_id, result))

    return JSONResponse(
        jsonrpc_error(
            request_id,
            -32601,
            f"Method not found: {method}",
        ),
        status_code=200,
    )


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "exam-challenge-mcp",
        "mcp_endpoint": "/mcp",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/mcp")
async def mcp_endpoint(request: Request):
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return JSONResponse(
            jsonrpc_error(None, -32700, "Parse error"),
            status_code=400,
        )

    # Support individual JSON-RPC messages and batches.
    if isinstance(body, list):
        if not body:
            return JSONResponse(
                jsonrpc_error(None, -32600, "Invalid Request"),
                status_code=400,
            )

        responses = []

        for message in body:
            response = await dispatch(message, request)

            if response.status_code == 202:
                continue

            try:
                data = json.loads(response.body)
            except (ValueError, TypeError):
                continue

            responses.append(data)

        if not responses:
            return Response(status_code=202)

        return JSONResponse(responses)

    return await dispatch(body, request)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
    )
