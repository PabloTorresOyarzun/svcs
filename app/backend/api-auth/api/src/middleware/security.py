from litestar.middleware import DefineMiddleware
from litestar.middleware.base import MiddlewareProtocol
from litestar.types import ASGIApp, Receive, Scope, Send
from litestar.connection import Request
from collections import defaultdict
import time
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class SecurityHeadersMiddleware(MiddlewareProtocol):
    """
    OWASP: Headers de seguridad HTTP.
    Referencia: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))

                # OWASP Headers
                security_headers = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"x-xss-protection", b"1; mode=block"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"permissions-policy", b"geolocation=(), microphone=(), camera=()"),
                    (b"cache-control", b"no-store, no-cache, must-revalidate"),
                    (b"pragma", b"no-cache"),
                ]

                existing_headers = list(message.get("headers", []))
                existing_headers.extend(security_headers)
                message["headers"] = existing_headers

            await send(message)

        await self.app(scope, receive, send_with_headers)


class RateLimitMiddleware(MiddlewareProtocol):
    """
    OWASP: Proteccion contra ataques de fuerza bruta y DoS.
    Implementa rate limiting por IP.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.requests: dict[str, list[float]] = defaultdict(list)
        settings = get_settings()
        self.max_requests = settings.rate_limit_requests
        self.window_seconds = settings.rate_limit_period

    def _get_client_ip(self, scope: Scope) -> str:
        # Obtener IP real considerando proxies
        headers = dict(scope.get("headers", []))
        forwarded = headers.get(b"x-forwarded-for", b"").decode()
        if forwarded:
            return forwarded.split(",")[0].strip()

        client = scope.get("client")
        return client[0] if client else "unknown"

    def _is_rate_limited(self, client_ip: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds

        # Limpiar requests antiguos
        self.requests[client_ip] = [
            ts for ts in self.requests[client_ip] if ts > window_start
        ]

        if len(self.requests[client_ip]) >= self.max_requests:
            return True

        self.requests[client_ip].append(now)
        return False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        client_ip = self._get_client_ip(scope)

        if self._is_rate_limited(client_ip):
            logger.warning("rate_limit_exceeded", client_ip=client_ip)

            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"retry-after", str(self.window_seconds).encode()),
                ],
            })
            await send({
                "type": "http.response.body",
                "body": b'{"detail": "Too many requests"}',
            })
            return

        await self.app(scope, receive, send)


class AuditLogMiddleware(MiddlewareProtocol):
    """
    OWASP: Logging de auditoria para trazabilidad.
    Registra todas las operaciones sensibles.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    def _get_client_ip(self, scope: Scope) -> str:
        headers = dict(scope.get("headers", []))
        forwarded = headers.get(b"x-forwarded-for", b"").decode()
        if forwarded:
            return forwarded.split(",")[0].strip()
        client = scope.get("client")
        return client[0] if client else "unknown"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.time()
        status_code = 0

        async def capture_status(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        finally:
            duration = time.time() - start_time
            logger.info(
                "http_request",
                method=scope.get("method"),
                path=scope.get("path"),
                status=status_code,
                duration_ms=round(duration * 1000, 2),
                client_ip=self._get_client_ip(scope),
            )


# Middleware configurados para uso en la aplicacion
security_headers_middleware = DefineMiddleware(SecurityHeadersMiddleware)
rate_limit_middleware = DefineMiddleware(RateLimitMiddleware)
audit_log_middleware = DefineMiddleware(AuditLogMiddleware)