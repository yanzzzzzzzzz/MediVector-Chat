"""API credentials, per-principal database namespaces, and bounded request limits."""
import hashlib
import hmac
import ipaddress
import json
import os
import threading
import time
from collections import defaultdict, deque
from contextvars import ContextVar
from dataclasses import dataclass

from starlette.responses import JSONResponse


@dataclass(frozen=True)
class Principal:
    name: str
    role: str

    @property
    def schema(self):
        return "tenant_" + hashlib.sha256(self.name.encode()).hexdigest()[:24]


current_principal: ContextVar[Principal | None] = ContextVar("principal", default=None)


def configured_users() -> dict:
    users = json.loads(os.getenv("API_USERS", "{}"))
    if not isinstance(users, dict):
        raise ValueError("API_USERS must be an object")
    tokens = set()
    for name, user in users.items():
        if not name or not isinstance(user, dict) or user.get("role") not in {"user", "admin"}:
            raise ValueError("Invalid API_USERS principal or role")
        token = user.get("token")
        if not isinstance(token, str) or len(token) < 32 or not token.isascii() or token in tokens:
            raise ValueError("API_USERS requires unique tokens of at least 32 characters")
        tokens.add(token)
    return users


def is_loopback(host):
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class APIProtection:
    def __init__(self, app):
        self.app = app
        self.requests = defaultdict(deque)
        self.lock = threading.Lock()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        users = configured_users()
        headers = dict(scope["headers"])
        principal = None
        if users:
            supplied = headers.get(b"authorization", b"")
            for name, user in users.items():
                if hmac.compare_digest(supplied, ("Bearer " + user["token"]).encode("ascii")):
                    principal = Principal(name, user["role"])
            if principal is None:
                return await JSONResponse({"error": "API authorization required"}, status_code=401)(scope, receive, send)
            if (scope["path"].startswith("/api/documents") and scope["method"] in {"POST", "PUT", "DELETE"}
                    and principal.role != "admin"):
                return await JSONResponse({"error": "Document administration requires admin role"}, status_code=403)(scope, receive, send)
        elif not is_loopback((scope.get("client") or ("",))[0]) and not (
            scope["path"] == "/api/retrieval/search" and os.getenv("RETRIEVAL_API_TOKEN")
        ):
            return await JSONResponse({"error": "Local demo requires loopback access; configure API_USERS"}, status_code=403)(scope, receive, send)
        key = principal.name if principal else "local-demo"
        now = time.monotonic()
        limit = max(1, int(os.getenv("API_RATE_LIMIT_PER_MINUTE", "120")))
        with self.lock:
            bucket = self.requests[key]
            while bucket and bucket[0] <= now - 60:
                bucket.popleft()
            limited = len(bucket) >= limit
            if not limited:
                bucket.append(now)
        if limited:
            return await JSONResponse({"error": "Rate limit exceeded"}, status_code=429,
                                      headers={"Retry-After": "60"})(scope, receive, send)
        max_bytes = max(1, int(os.getenv("MAX_REQUEST_BYTES", "10485760")))
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > max_bytes:
                return await JSONResponse({"error": "Request too large"}, status_code=413)(scope, receive, send)
            if not message.get("more_body", False):
                break
        delivered = False
        async def replay():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}
        context_token = current_principal.set(principal)
        try:
            await self.app(scope, replay, send)
        finally:
            current_principal.reset(context_token)
