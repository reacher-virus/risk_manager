.PHONY: setup data features train pipeline api api-auth api-https web test demo docker clean admin cert secret
PY ?= python3

setup:            ## install backend + frontend dependencies
	cd backend && $(PY) -m pip install -r requirements-dev.txt
	cd frontend && npm install

data:             ## generate the synthetic dataset
	cd backend && $(PY) -m app.data.generate_dataset
features:         ## leakage-safe feature engineering
	cd backend && $(PY) -m app.ml.features
train:            ## train, calibrate, pick threshold, evaluate once on held-out test
	cd backend && $(PY) -m app.ml.train
pipeline: data features train   ## whole ML pipeline

api:              ## run the API on :8000 (open dev mode: no login; see README)
	cd backend && RISK_AUTH_REQUIRED=false $(PY) -m uvicorn app.api.main:app --reload --port 8000 --no-server-header
api-auth:         ## run the API with authentication ON (create an admin first: make admin)
	cd backend && $(PY) -m uvicorn app.api.main:app --reload --port 8000 --no-server-header
cert:             ## self-signed certificate for local https (certs/dev.crt, certs/dev.key)
	./scripts/dev_cert.sh
api-https: cert   ## run the API over TLS on :8443 with secure cookies and HSTS
	cd backend && FORCE_HTTPS=true COOKIE_SECURE=true CORS_ORIGINS=http://localhost:5173 $(PY) -m uvicorn app.api.main:app --port 8443 --ssl-keyfile ../certs/dev.key --ssl-certfile ../certs/dev.crt --no-server-header
admin:            ## create an admin account (prompts for the password)
	cd backend && $(PY) -m app.auth.create_admin
secret:           ## print a strong random JWT secret
	cd backend && $(PY) -m app.auth.secrets
web:              ## run the dashboard on :5173
	cd frontend && npm run dev

test:             ## backend + frontend test suites
	cd backend && $(PY) -m pytest -q
	cd frontend && npm test

demo:             ## train if needed, then start API (auth ON) and dashboard. Run `make admin` once first
	@test -f backend/data/models/model.joblib || $(MAKE) pipeline
	@trap 'kill 0' INT TERM EXIT; \
	 (cd backend && $(PY) -m uvicorn app.api.main:app --port 8000 --no-server-header) & \
	 (cd frontend && npm run dev) & wait

docker:           ## everything in containers (Postgres + API + dashboard)
	docker compose up --build

clean:            ## remove generated data, models and the local database
	rm -rf backend/data/raw/*.csv backend/data/processed/*.csv backend/data/models/* backend/data/*.db
