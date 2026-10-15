#!/bin/sh
# Self-signed certificate for LOCAL https development only (browsers will warn; use `curl -k` or trust certs/dev.crt).
# Production: terminate TLS at Caddy (see Caddyfile) or your cloud load balancer: never ship a self-signed cert.
set -e
cd "$(dirname "$0")/.."
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 365 -keyout certs/dev.key -out certs/dev.crt \
  -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" 2>/dev/null
chmod 600 certs/dev.key
echo "Created certs/dev.crt and certs/dev.key (valid 365 days)"
