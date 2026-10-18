from mcp.server.transport_security import TransportSecuritySettings
import hashlib
from contextvars import ContextVar

from mcp.server.fastmcp import FastMCP

EMAIL = "23f3001817@ds.study.iitm.ac.in"

challenge_header = ContextVar("challenge_header", default="")

mcp = FastMCP("Exam Challenge")


class HeaderMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        challenge = headers.get(
            b"x-exam-challenge", b""
        ).decode("utf-8")

        token = challenge_header.set(challenge)
        try:
            await self.app(scope, receive, send)
        finally:
            challenge_header.reset(token)


@mcp.tool()
def solve_challenge() -> str:
    """Solve the current exam challenge using its HTTP header."""
    challenge = challenge_header.get()
    value = f"{challenge}:{EMAIL}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


app = HeaderMiddleware(
    mcp.streamable_http_app(
        transport_security=TransportSecuritySettings(
            allowed_hosts=[
                "mcp-challenge-1-ac40.onrender.com",
                "mcp-challenge-1-ac40.onrender.com:*",
            ]
        )
    )
)
