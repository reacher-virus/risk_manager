"""Client IP, scheme and Origin handling. Forwarded headers are trusted ONLY when TRUSTED_PROXY_COUNT > 0."""
import ipaddress

from fastapi import HTTPException, Request

from app.core import config as cfg


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    n = cfg.TRUSTED_PROXY_COUNT
    if n > 0:
        parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(parts) >= n:
            try:
                return str(ipaddress.ip_address(parts[-n]))     # count from the right: the left side is attacker-controlled
            except ValueError:
                pass
    return peer


def is_https(request: Request) -> bool:
    if cfg.TRUSTED_PROXY_COUNT > 0:
        return request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower() == "https"
    return request.url.scheme == "https"


def check_origin(request: Request) -> None:
    """Browsers always send Origin on cross-site POSTs. If it is present it must be one of ours."""
    origin = request.headers.get("origin")
    if origin and origin not in cfg.CORS_ORIGINS:
        raise HTTPException(403, "Origin not allowed")


def ip_allowed(ip: str, cidrs: list[str]) -> bool:
    if not cidrs:
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in ipaddress.ip_network(c, strict=False) for c in cidrs)
