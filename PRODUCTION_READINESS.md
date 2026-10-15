# Production Readiness: Challenges, Fixes, and Future Scope

This document records the main issues encountered while preparing Risk Manager for deployment, the fixes applied, and improvements that remain possible. It is a development log, not a claim that the application has undergone a formal security audit or production-scale load test.

## Project and Deployment

- **Project:** Risk Manager — AI-assisted fraud, abusive-return, and chargeback risk analysis.
- **Repository:** https://github.com/reacher-virus/risk_manager
- **Frontend:** React, TypeScript, and Vite, deployed on Vercel.
- **Backend:** FastAPI, deployed on Render.
- **Data and model note:** Results shown by the project include synthetic-data results. They should not be interpreted as verified performance on real merchant transactions.

## Problems Encountered and Work Completed

### 1. Frontend/backend deployment and configuration

**Challenge:** The frontend and backend are deployed separately, so the frontend must use the correct backend URL and the backend must be configured for the deployed environment.

**Work completed:** The frontend was deployed to Vercel and the FastAPI backend to Render. Deployment URLs and application configuration were checked during troubleshooting.

**Future improvement:** Document required environment variables in an `.env.example` file, validate configuration at startup, and keep development, preview, and production settings separate. Never commit real credentials or secrets.

### 2. Authentication and email verification

**Challenge:** Verification emails were not being delivered during SMTP setup. Logs showed that the SMTP host setting was not loaded, and development-mode messages printed verification codes to the backend console instead of delivering email.

**Work completed:** SMTP configuration and environment-variable loading were investigated, and authentication-related code was developed and tested.

**Future improvement:** Verify delivery using the production email provider, add delivery/error monitoring and retry handling, and ensure production never falls back to logging verification codes or password-reset tokens. Keep SMTP credentials in the hosting provider's secret settings.

### 3. Model artifact and startup handling

**Challenge:** The backend initially reported a missing `model.joblib` artifact. Model artifacts and startup loading had to be checked before the API could start successfully.

**Work completed:** The model-loading path and startup logs were investigated; later startup logs confirmed that the configured Random Forest model loaded.

**Future improvement:** Add a documented model-artifact build/release process, validate artifact presence and compatibility during deployment, and expose a health/readiness check that reports whether required artifacts are available without revealing sensitive paths or data.

### 4. Memory limits and model retraining

**Challenge:** The Render service encountered out-of-memory failures on its 512 MB instance. Memory use was especially concerning around model retraining and concurrent activity.

**Work completed:** A backend change was committed to reduce model-retraining memory usage. The service later ran without new OOM errors during the observed period, but this does not prove the issue is eliminated under load.

**Future improvement:**
- Profile memory and CPU use under representative traffic.
- Prevent duplicate or overlapping training jobs.
- Move training to a separate worker/job service instead of running it inside the API process.
- Set job timeouts, status reporting, cancellation rules, and safe failure recovery.
- Consider a larger service instance if measured workload requires it.
- Add load tests for concurrent sign-ins, dashboard requests, and administrative training actions.

### 5. Security and authentication hardening

**Challenge:** A deployed application needs stronger controls than a local prototype, including safe session handling, access control, input validation, and auditability.

**Work completed:** Authentication and authorization functionality, security-focused tests, and related backend changes were developed. The project includes tests for authentication flows and static security checks.

**Future improvement:**
- Conduct a formal security review and threat model.
- Test authorization on every protected API route, including administrator-only actions.
- Add rate limits appropriate to each endpoint and monitor abuse.
- Review CSRF protection, cookie settings, CORS, session rotation/revocation, password reset, and account recovery.
- Add dependency scanning, secret scanning, and a regular patch process.
- Test SQL injection and other input-handling risks with a security test suite.
- Avoid exposing sensitive user data in logs, errors, and API responses.

Passing automated tests is useful evidence, but it does not guarantee the application is secure.

### 6. Frontend contact links and GitHub Actions

**Challenge:** Contact links were changed from `mailto:` to Gmail compose URLs, and the footer repository link still pointed to an older repository URL. Frontend CI tests expected the previous `mailto:` behavior and old GitHub URL. A date test also failed because a UTC timestamp crossed into the next calendar day in the local timezone.

**Work completed:** Contact links and the repository URL were corrected, and affected test expectations were updated. The date-test timestamp was adjusted to avoid crossing the local date boundary. The user confirmed that all frontend tests passed locally afterward.

**Future improvement:** Keep tests aligned with intended user-facing behavior, use timezone-independent date tests where appropriate, and confirm the latest GitHub Actions workflow passes after pushing changes.

### 7. Deployment verification

**Challenge:** A successful Vercel deployment did not mean all GitHub Actions checks had passed; the frontend CI workflow failed while the backend CI passed.

**Work completed:** Frontend test failures were identified and corrected locally.

**Future improvement:** Treat deployment status and CI status as separate checks. Require passing frontend tests, backend tests, build checks, and security checks before merging or releasing.

## Future Scope

### Reliability and operations
- Add structured logs, request IDs, error tracking, and operational alerts.
- Add API liveness/readiness checks and uptime monitoring.
- Track response latency, error rates, memory, CPU, and job duration.
- Define backup and recovery procedures for persistent application data.

### Model quality and explainability
- Evaluate on representative, properly governed real-world data before making real-world performance claims.
- Track precision, recall, F1, PR-AUC, ROC-AUC, calibration, and false-positive rates across meaningful data splits.
- Add model/version metadata, reproducible training, model approval, and rollback.
- Monitor data drift and model performance degradation.
- Validate explanations with domain experts and clearly communicate uncertainty.

### Product capabilities
- Add richer interactive dashboards and date/filter controls.
- Add alert triage, assignment, notes, and audit-history views.
- Support configurable risk thresholds and cost-sensitive decision analysis.
- Add carefully permissioned report exports and scheduled summaries.
- Improve accessibility, mobile usability, and clear empty/loading/error states.

### Scale and maintainability
- Move long-running model training to a separate worker.
- Add a task queue if background workload grows.
- Add integration and end-to-end tests for critical user journeys.
- Improve API documentation and maintain a versioned API contract.
- Add CI checks for linting, type checking, production builds, dependencies, and secrets.

## Production-readiness checklist

- [ ] Confirm all required production environment variables are set in hosting dashboards.
- [ ] Confirm no secrets, credentials, verification codes, or tokens are committed.
- [ ] Confirm frontend and backend CI workflows pass on the latest commit.
- [ ] Confirm production sign-up, email verification, sign-in, sign-out, and password recovery.
- [ ] Confirm role-based access control for all protected API routes.
- [ ] Confirm health checks and model artifact loading after a clean restart.
- [ ] Test memory use and concurrency on the actual hosting plan.
- [ ] Confirm logs do not contain passwords, tokens, or unnecessary personal data.
- [ ] Review CORS, cookies, CSRF controls, rate limits, and security headers.
- [ ] Document backup, recovery, incident response, and model rollback procedures.
- [ ] Clearly label synthetic-data results and avoid unsupported performance claims.

## Final note

Risk Manager has been deployed and tested, and several deployment, authentication, contact-link, model-loading, and CI issues were addressed during development. The project should still be treated as an evolving application: production readiness depends on continued monitoring, realistic load testing, security review, reliable email delivery, and validation on representative data.
