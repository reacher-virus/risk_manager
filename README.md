# AI Risk Manager

Defense-only loss detection for fraud, abusive returns and chargebacks. It scores every transaction, explains
*why*, recommends an action (allow / monitor / review / hold), and picks its operating point from **what mistakes
cost**, not from accuracy. Built to the product spec's MVP: Fraud-Spike Detector + Risk Verifier.

> **Data honesty.** All data is **synthetic** (`backend/app/data/generate_dataset.py`) because public fraud datasets
> lack device/account/network fields. Every metric below describes simulated ground truth, not production performance.

## Quick start

```bash
make setup      # install backend + frontend dependencies
make pipeline   # generate data, engineer features, train (~1-2 min, first time only)
make admin      # create the first administrator (prompts for a password)
make demo       # API on :8000 (authentication ON) + dashboard on :5173
```

Open <http://localhost:5173>. Sign up as a normal user, or use **Administrator sign-in** (link at the bottom of the sign-in page).
With no SMTP configured, the emailed one-time codes are printed in the API terminal (development only: production refuses to start without SMTP).
Want to look around without logging in? `make api` runs the API in open dev mode (`RISK_AUTH_REQUIRED=false`).

By hand:

```bash
cd backend && pip install -r requirements-dev.txt
python -m app.data.generate_dataset && python -m app.ml.features && python -m app.ml.train
python -m app.auth.create_admin
python -m uvicorn app.api.main:app --reload --port 8000     # docs: http://localhost:8000/docs (disabled in production)
cd ../frontend && npm install && npm run dev                 # dashboard: http://localhost:5173
```

HTTPS locally: `make api-https` (self-signed cert, TLS on :8443). Production: `docker compose up --build` (Caddy terminates TLS with automatic certificates, Postgres, API and dashboard on one origin; copy `.env.example` to `.env` first).

## What it does

**Detection & ML**
- Two layers: a simple rule baseline vs. a learned model (logistic regression / random forest / XGBoost, best by validation PR-AUC).
- 27 leakage-safe features: velocity, device sharing, customer/payment history, amount deviation, return rate, and **network features** (size of the linked account/device/card cluster).
- **Calibrated probabilities** (isotonic, fitted on a separate validation slice) so a score of 0.3 really means about 30%.
- **Cost-based threshold**: chosen on a second validation slice from your FP/FN costs; ties go to the higher threshold (fewer customers bothered).
- **Anomaly layer** (Isolation Forest) that flags behaviour unlike normal traffic even when the supervised model is unsure.
- **SHAP explanations** for every alert, turned into plain-English reasons.
- **Ring detection**: connected components over customer-device-card links, visualised as a network.
- **Drift monitoring** (PSI) with a retrain recommendation, and **retraining that folds in analyst feedback**.

**Data fixes that make the numbers believable** (all covered by tests)
- Outcomes (fraud confirmation, chargeback, return) enter history only after `RISK_LABEL_DELAY_DAYS` (default 14), like real chargebacks. Earlier versions let labels leak into features instantly, which inflated PR-AUC to 0.998.
- Cumulative all-time counters were replaced by 30-day windows (they acted as a clock and drifted).
- A warm-up window with no history/labels is excluded from training and evaluation.
- Harder fraud: six patterns (point anomaly, coordinated ring, multi-device ring, slow ring, account takeover, card testing, return abuse), label noise, and legitimate households that share devices.

**Backend**: FastAPI + SQLAlchemy (SQLite by default, PostgreSQL via `DATABASE_URL`); multi-step authentication with role-based access (viewer / analyst / admin); rate limiting; audit log of every score, review, sign-in and config change; analyst review workflow; batch CSV scoring; scenario simulator; CSV export; SSRF-guarded alert webhook.

**Public site and dashboard** (React + TypeScript): Landing page with a draggable 3D hero · Sign up · Sign in (two-step) · Administrator sign-in · Forgot/reset password · Privacy and Terms · custom 404 · signed-in welcome page · Overview · Alert queue with filters/pagination/export · Alert detail drawer (reasons, SHAP bars, customer timeline, related accounts, approve/hold/escalate, confirm fraud/legit) · Scenario simulator + single-transaction form · Threshold & cost explorer (live sliders, cost curve) · Network graph · Analytics (risk over time, segment breakdown, PR curve, confusion matrix) · Monitoring (drift, retrain, audit log) · Batch CSV · User management (admin) · Settings (account, change password, costs, light/dark theme).

## Results (held-out test set, evaluated once)

| | Rules | ML (random forest, calibrated) |
|---|---|---|
| Precision | 44.1% | **73.9%** |
| Recall | 42.2% | **94.4%** |
| PR-AUC | 0.277 | **0.851** |
| Expected loss (FP ₹150, FN ₹2,500) | ₹3,24,600 | **₹40,650** (-87.5%) |

False-positive rate 0.79%. Calibration cut the Brier score from 0.0096 to 0.0049. Precision is below the spec's 80% target:
with a missed fraud costing 17x a false alarm, the cost-optimal operating point favours recall. The Threshold tab lets you trade that off live.
Numbers vary slightly if you regenerate data or change costs.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/predict` | Score one transaction (live): score, level, decision, reasons, SHAP contributions, anomaly score |
| POST | `/predict/batch` | Score a CSV in isolation; optional `is_fraud` column returns precision/recall/cost |
| POST | `/simulate` | Fire a realistic scenario through the live pipeline |
| GET | `/alerts`, `/alerts/{id}`, `/alerts/export.csv` | Queue (filters, paging), full case, export |
| POST | `/alerts/{id}/review` | Approve/hold/escalate and/or label fraud/legit (feeds retraining) |
| GET | `/dashboard/summary`, `/metrics`, `/model-comparison` | Headline numbers |
| GET | `/analysis/threshold` | Cost curve and metrics for any threshold/costs |
| GET | `/analytics/{timeseries,breakdown,pr-curve,confusion}` | Chart data |
| GET | `/graph/rings`, `/graph/rings/{id}` | Linked-account networks |
| GET | `/monitoring/summary` | Drift (PSI), feedback stats, lifecycle |
| POST | `/admin/retrain` · GET `/admin/retrain/status` | Retrain with analyst feedback (admin) |
| GET/PUT | `/config`, `/config/costs`, `/config/threshold` | Business costs and deployed threshold (PUT: admin) |
| GET | `/audit` | Audit log (admin) |
| GET/PATCH | `/admin/users`, `/admin/users/{id}` · POST `/admin/users/{id}/revoke-sessions` | List, change role (viewer/analyst), disable, end sessions (admin) |
| GET/PUT/POST | `/admin/webhook`, `/admin/webhook/test` | Critical-alert webhook (admin, SSRF-guarded) |
| GET | `/auth/captcha` | New single-use image CAPTCHA |
| POST | `/auth/signup` → `/auth/signup/verify` | Sign-up (CAPTCHA) then confirm the emailed code |
| POST | `/auth/login` → `/auth/login/verify` | Sign-in step 1 (password + CAPTCHA) then step 2 (emailed code) |
| POST | `/auth/admin/login` → `/auth/admin/login/verify` | Dedicated administrator door (same two steps) |
| POST | `/auth/otp/resend` | New code (cooldown + hourly cap) |
| GET | `/auth/me` | Current session |
| POST | `/auth/refresh`, `/auth/logout`, `/auth/logout-all` | Rotate / end this session / end all sessions |
| POST | `/auth/password/forgot` → `/auth/password/reset` | Reset by emailed single-use link |
| POST | `/auth/password/change` | Change password (signs out everywhere) |

Browsers authenticate with HttpOnly session cookies (+ CSRF header). Machine clients can use `API_KEYS="key:analyst,key2:admin"` and send `X-API-Key`. Interactive docs at `/docs` in development.

## Configuration

See `backend/.env.example` (every variable is documented there). Frontend: `VITE_API_BASE` (see `frontend/.env.example`). The browser never holds an API key or token.

## Tests

```bash
make test        # backend: 274 tests (ML pipeline, API, authentication & security) + frontend: 86 tests
```
CI runs both on every push (`.github/workflows/ci.yml`).

## Project layout

```
backend/app/
  core/   config, db (SQLAlchemy), security (principal, RBAC, CSRF), ssrf, webhook, schemas, risk_policy
  auth/   models, service, tokens (JWT/cookies/CSRF), secrets, passwords, identity, captcha, mailer, ratelimit, netutil, startup
  data/   synthetic dataset generator
  ml/     feature_store, features, rule_baseline, train, anomaly, explain, graph, drift
  api/    main, middleware (HTTPS + headers), state, routes_{auth,users,core,alerts,analytics,admin}
backend/tests/   pytest suite (runs the whole pipeline on a small dataset)
frontend/src/    pages/ (+ pages/auth/), auth/, components/, lib/, api.ts, types.ts, index.css (all styling lives here)
Caddyfile, docker-compose.yml, scripts/dev_cert.sh   HTTPS + deployment
scripts/generate_brand_assets.py    favicons, PWA icons, social-share image
tools/browser-audit/                real-browser overflow / behaviour / CSP checks (optional)
docs/UI-SETUP.md                    how the login component and landing page were integrated; adding Tailwind + shadcn
```

## Frontend design

- **Look:** monochrome zinc palette with an orange accent; light and dark themes on the landing page and dashboard; the sign-in screens are always dark (black card over an animated dot-matrix WebGL background, from the supplied login component).
- **Landing page:** hero with a draggable 3D network (the orange cluster is a fraud ring sharing a device), feature bento, how it works, security, results versus a rules baseline, FAQ, closing call to action. It deliberately has **no invented testimonials or pricing**. Its headline numbers (87.5%, 94%, 0.85 and the results table) are static copy from the last training run on synthetic data; if you retrain and the numbers move, update `pages/LandingPage.tsx`.
- **Mobile and accessibility:** no horizontal scrolling at any width from 320 px (verified in a real browser: 20 screens at 6 widths), a hamburger menu on the public site and the dashboard (focus handling, Escape, scroll lock, visible close button), tables become labelled cards on phones, fields are not auto-focused on touch devices, reduced-motion is respected, FAQ uses native `<details>`.
- **Polish:** descriptive page title per route, meta description, social-share tags and icons (favicon, Apple touch icon, PWA manifest), custom in-app 404 plus a static `404.html`, footer links that all work, current copyright year, clickable logo everywhere, and success / error / info toast messages for sign-in, sign-up, resets, reviews, saves, uploads and retraining.
- **Your details** (name, contact email, GitHub link) live in one file: `frontend/src/lib/site.ts`. See `docs/UI-SETUP.md` for the component integration notes and for adding Tailwind and shadcn.
- **Verified in a browser, not just unit tests:** `tools/browser-audit` (optional) re-checks overflow, behaviours and the Content-Security-Policy after any restyle.

## Authentication & security

**Flows**
- **Sign-up**: CAPTCHA → name, email, password → a 6-digit code is emailed → entering it creates the account (role `viewer`). Nothing is stored as a user until the mailbox is proven, so made-up or someone else's addresses never become accounts. Disposable-email domains are rejected, and in production the domain must be able to receive mail.
- **Sign-in (two steps)**: CAPTCHA + password → a fresh emailed code → session cookies. A correct password alone gives no access.
- **Administrator sign-in**: a separate page and endpoints. Admin accounts cannot sign in through the public form (and vice versa), cannot be created via sign-up or the API (only `make admin` / `python -m app.auth.create_admin`), get shorter sessions (10-min access token, 8-hour maximum), and can be limited to trusted networks with `ADMIN_ALLOWED_IPS`.
- **After sign-in** everyone lands on the hero page, then the dashboard (`#/app/...`).
- **Roles**: `viewer` reads dashboards; `analyst` can also score, simulate, upload and review; `admin` also manages users, config, retraining, webhook and the audit log. Enforced on the server for every request, re-read from the database each time (demotion or disabling takes effect immediately). The UI hiding a tab is only a convenience.

**Threats and controls** (each row is covered by tests in `backend/tests/test_auth_*.py` and `frontend/src/__tests__/`)

| Threat | Control |
|---|---|
| SQL injection | The ORM with bound parameters is the only database path. Inputs are validated (strict schemas, enums, length caps, `extra=forbid`). Search wildcards are escaped. A test fails the build if raw SQL appears anywhere in `app/`. |
| XSS | JSON-only API sent with `nosniff` and `Content-Security-Policy: default-src 'none'`; names/emails reject markup; React escapes output and a scan test bans `dangerouslySetInnerHTML`, `innerHTML`, `eval`, etc.; the dashboard's nginx CSP allows only same-origin scripts; session cookies are HttpOnly so injected script could not read them anyway. |
| CSRF | SameSite cookies + `Origin` check + a signed per-session CSRF token required on every state-changing request. |
| Brute force / credential stuffing | 5 failed passwords lock an account for 15 minutes (also for emails that don't exist, so there is nothing to probe); per-IP caps on sign-in, sign-up, code entry, CAPTCHA and reset; codes die after 5 wrong tries; all counters live in the database, so they survive restarts and work across workers. |
| Account enumeration | Identical responses and equal work (a full Argon2 check even for unknown emails) for sign-in, sign-up and reset. Signing up with an existing email emails its owner instead of revealing it. |
| Weak or stolen credentials | Argon2id hashing; 12+ character policy with a common-password check; one-time codes stored as HMACs and single-use; refresh tokens rotate, and replaying an old one revokes the whole session. |
| JWT abuse | Algorithm pinned to HS256 (`none`/other algorithms rejected before verification); `exp`, `nbf`, `iat`, `iss`, `aud`, `sub`, `sid`, `jti` all required; key id header; roles come from the database, never the token; instant revocation via session rows and a per-user token version. |
| Secret management | `JWT_SECRET` from the environment or a mounted file, never the code. Weak, short, placeholder or low-entropy values are refused in every environment; production never auto-generates one; signing, CSRF, code, CAPTCHA and webhook keys are derived with HKDF; zero-downtime rotation with `JWT_SECRET_PREVIOUS`; the dev secret file is created mode 0600 and git-ignored. Generate one: `make secret`. |
| Broken password reset | 256-bit random single-use token, stored only as a hash, expires in 30 minutes; a new request kills older links; the link is built from `FRONTEND_URL` (never the Host header) and the token sits in the URL fragment so it never reaches servers or Referer headers; resetting signs out every device and mails a notice; no account enumeration; rate-limited per address and IP; new password must pass the policy and differ from the old one. |
| SSRF | The only server-side outbound request is the admin webhook. https only, no embedded credentials, allowed ports, optional host allowlist; the name is resolved once and **every** answer must be a public address (loopback, private ranges, link-local/cloud metadata, CGNAT, IPv4-mapped IPv6 and obfuscated decimal/hex/octal forms are all refused); the connection is pinned to the validated IP while TLS still verifies the hostname (defeats DNS rebinding); redirects are never followed; short timeout and response cap; re-validated at send time. |
| HTTPS | In production the app redirects http→https (308), sends HSTS, marks cookies `Secure` (`__Secure-` prefix), and refuses to start otherwise. Forwarded headers are trusted only when `TRUSTED_PROXY_COUNT` says a proxy of yours is in front. Caddy provides automatic certificates; `make api-https` gives local TLS. |
| Cookies | Access and refresh tokens are HttpOnly, SameSite, path-scoped (refresh is `Strict` and only sent to `/auth`); the CSRF token is the single JavaScript-readable cookie; nothing secret is ever put in localStorage or the page. A cookie notice explains that only strictly necessary cookies are used. |
| Mail abuse | Plain-text email only (no markup injection), header-injection impossible, resend cooldown and hourly caps, per-address and per-IP limits so nobody can use the system to spam a third party. |
| Mass assignment / over-posting | Unknown fields are rejected, so `{"role":"admin"}` in a sign-up request is a 422. Admin role cannot be granted through the API. |

**Production checklist**: `APP_ENV=production`; set `JWT_SECRET`, `POSTGRES_PASSWORD`, SMTP settings, `FRONTEND_URL`/`CORS_ORIGINS`/`ALLOWED_HOSTS` to your https domain; terminate TLS (Caddy via `docker compose`, or your load balancer); create the admin with `python -m app.auth.create_admin`; consider `ADMIN_ALLOWED_IPS` and `ALLOWED_EMAIL_DOMAINS`. The server validates these at startup and refuses to run if they are missing or unsafe.

## Known limitations

- Synthetic data: results show the system works, not how it will perform on your traffic. Re-run `make pipeline` on real data with the same columns.
- Graph features accumulate forever (no time decay); long-lived legitimate shared devices will grow large components.
- The live feature store is in-memory (rebuilt from history at start-up); persist/replay it for multi-instance deployments.
- Rate limiting is per-process. Use a gateway or Redis-backed limiter when scaling out.
- `docker compose` and the Caddy config are provided but were not run in the authoring environment; please smoke-test them once. The in-process HTTPS behaviour and a real TLS 1.3 server were tested.
- The CAPTCHA is a self-hosted image CAPTCHA: it stops casual bots but is weaker than a hosted service (reCAPTCHA/Turnstile/hCaptcha). Swapping one in means changing `app/auth/captcha.py` and the `Captcha` component.
- Second factor is an emailed code only (no authenticator app/WebAuthn); anyone who controls the mailbox can complete step 2, so protect the mailbox. Email-code MFA is a deliberate trade-off for this MVP.
- Rate limits are stored in the database: SQLite serialises writes (use PostgreSQL for real traffic). The general per-user API limiter is still in-memory and per process.
- No self-service account deletion, email change, or "known devices" yet. Sign-in alerts by email are not sent.
- Earlier commits of this repository contain generated data and model files; untracking them did not rewrite history.
- The 3D hero and sign-in background need WebGL; without it (or with `prefers-reduced-motion`) they fall back to a still or plain background. `three` is bundled (not loaded from a CDN) and only fetched by the landing and auth pages.
- Fonts (Inter, IBM Plex Mono) load from Google Fonts. For stricter privacy, self-host them and drop the two Google hosts from the CSP in `frontend/nginx.conf`.
- Privacy Policy and Terms describe what the software does but are a template: have them reviewed before commercial use.
