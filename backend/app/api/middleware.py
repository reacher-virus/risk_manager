"""HTTPS enforcement and security headers for every response."""
from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth import netutil
from app.core import config as cfg

DOC_PATHS = ("/docs", "/redoc", "/openapi.json")          # Swagger UI needs scripts; docs are disabled in production
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        https = netutil.is_https(request)
        if cfg.FORCE_HTTPS and not https and request.url.path != "/health":
            return RedirectResponse(str(request.url.replace(scheme="https")), status_code=308)   # method-preserving redirect
        resp = await call_next(request)
        h = resp.headers
        if https or cfg.FORCE_HTTPS:
            h["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        h["X-Content-Type-Options"] = "nosniff"                                      # a JSON reply can never be sniffed into HTML
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "no-referrer"
        h["Permissions-Policy"] = "geolocation=(), camera=(), microphone=(), payment=()"
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        h["Cache-Control"] = "no-store"                                              # tokens, codes and personal data are never cached
        if not request.url.path.startswith(DOC_PATHS):
            h["Content-Security-Policy"] = API_CSP
        return resp
