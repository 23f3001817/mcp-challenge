
import hashlib
from contextvars import ContextVar

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

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
        challenge = headers.get(b"x-exam-challenge", b"").decode("utf-8")
        token = challenge_header.set(challenge)
        try:
            await self.app(scope, receive, send)
        finally:
            challenge_header.reset(token)


@mcp.tool()
def solve_challenge() -> str:
    challenge = challenge_header.get()
    value = f"{challenge}:{EMAIL.strip().lower()}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


security = TransportSecuritySettings(
    allowed_hosts=[
        "mcp-challenge-1-ac40.onrender.com",
        "mcp-challenge-1-ac40.onrender.com:*",
    ],
    enable_dns_rebinding_protection=True,
)

app = HeaderMiddleware(
    mcp.streamable_http_app(transport_security=security)
)
