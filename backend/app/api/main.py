"""AI Risk Manager API.  Run: python -m uvicorn app.api.main:app --reload --port 8000   (docs at /docs in development)"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api import routes_admin, routes_alerts, routes_analytics, routes_auth, routes_core, routes_users
from app.api.middleware import SecurityMiddleware
from app.api.state import S
from app.auth.startup import run_startup_checks
from app.core import config as cfg


@asynccontextmanager
async def lifespan(app: FastAPI):
    S.load_all()                       # creates tables
    run_startup_checks()               # weak secrets / unsafe production config stop the server here
    print(f"Loaded model={S.manifest['best_model']} (calibration={S.manifest['calibration']}); auth_required={cfg.AUTH_REQUIRED}.")
    yield


app = FastAPI(title="AI Risk Manager", version="3.0.0", lifespan=lifespan,
              docs_url=None if cfg.IS_PROD else "/docs", redoc_url=None, openapi_url=None if cfg.IS_PROD else "/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=cfg.CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Content-Type", "X-CSRF-Token", "X-API-Key"])
if cfg.ALLOWED_HOSTS and "*" not in cfg.ALLOWED_HOSTS:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=cfg.ALLOWED_HOSTS)
app.add_middleware(SecurityMiddleware)  # outermost: headers + HTTPS redirect apply to everything, including CORS responses
for r in (routes_auth.router, routes_core.router, routes_alerts.router, routes_analytics.router, routes_admin.router, routes_users.router):
    app.include_router(r)
