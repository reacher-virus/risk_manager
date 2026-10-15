"""
SSRF defence for every outbound request the server makes on a user's behalf (currently: admin-configured webhooks).

  * https only, no credentials in the URL, allow-listed ports, optional host allow-list.
  * The hostname is resolved ONCE; if ANY answer is non-public (loopback, RFC1918, link-local incl. cloud metadata
    169.254.169.254, CGNAT, multicast, reserved, IPv4-mapped IPv6 ...) the request is refused.
  * The connection is then made to that validated IP (pinned) while TLS still verifies the original hostname, so a
    DNS-rebinding answer between "check" and "use" cannot redirect the request.
  * Redirects are never followed, timeouts are short and the response size is capped.
  * Obfuscated forms (decimal / hex / octal IPs, trailing dots, IDN tricks) end up as an IP that fails the public test.
"""
import hashlib
import hmac
import http.client
import ipaddress
import json
import re
import socket
import ssl
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core import config as cfg

BLOCKED_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback", "metadata", "metadata.google.internal", "instance-data"}
BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa", ".corp", ".intranet", ".private", ".cluster.local")
_LABEL = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


class UnsafeURL(ValueError):
    pass


@dataclass(frozen=True)
class Target:
    host: str
    port: int
    path: str
    ips: tuple[str, ...]


def _is_public(ip) -> bool:
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def _resolve(host: str, port: int) -> list[str]:                       # separate function so tests can substitute DNS
    return sorted({ai[4][0] for ai in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})


def validate_public_url(url: str) -> Target:
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) < 33 for c in url):
        raise UnsafeURL("URL is not valid")
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise UnsafeURL("Only https:// URLs are allowed")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise UnsafeURL("Credentials in the URL are not allowed")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeURL("URL has no host")
    try:
        port = parts.port or 443
    except ValueError:
        raise UnsafeURL("URL has an invalid port")
    if port not in cfg.WEBHOOK_ALLOWED_PORTS:
        raise UnsafeURL("Port is not allowed")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not _is_public(literal):
            raise UnsafeURL("Address is not a public internet address")
        resolved = [str(literal)]
    else:
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            raise UnsafeURL("Host name is not valid")
        if host in BLOCKED_NAMES or host.endswith(BLOCKED_SUFFIXES) or not all(_LABEL.match(l) for l in host.split(".")):
            raise UnsafeURL("Host name is not allowed")
        if cfg.WEBHOOK_ALLOWED_HOSTS and not any(host == h or host.endswith("." + h) for h in cfg.WEBHOOK_ALLOWED_HOSTS):
            raise UnsafeURL("Host is not on the allow-list")
        try:
            resolved = _resolve(host, port)
        except OSError:
            raise UnsafeURL("Host name could not be resolved")
    if not resolved:
        raise UnsafeURL("Host name could not be resolved")
    for addr in resolved:
        if not _is_public(ipaddress.ip_address(addr)):                  # ANY private answer poisons the whole name
            raise UnsafeURL("Host resolves to a non-public address")
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    return Target(host=host, port=port, path=path, ips=tuple(resolved))


class _PinnedHTTPS(http.client.HTTPSConnection):
    """Connects to a pre-validated IP but performs TLS (SNI + certificate check) for the real hostname."""

    def __init__(self, host, port, ip, **kw):
        super().__init__(host, port, **kw)
        self._pinned_ip = ip

    def connect(self):
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def post_json(url: str, payload: dict, signing_key: bytes, timeout: float = 5.0, max_response: int = 65536) -> int:
    """POST JSON to a validated public URL; returns the HTTP status. Redirects are NOT followed (a 3xx is just returned)."""
    target = validate_public_url(url)                                   # re-validated at send time, not only at save time
    body = json.dumps(payload, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "RiskManager-Webhook/1.0",
               "X-Risk-Signature": "sha256=" + hmac.new(signing_key, body, hashlib.sha256).hexdigest()}
    conn = _PinnedHTTPS(target.host, target.port, target.ips[0], timeout=timeout, context=ssl.create_default_context())
    try:
        conn.request("POST", target.path, body, headers)
        resp = conn.getresponse()
        resp.read(max_response)
        return resp.status
    finally:
        conn.close()
