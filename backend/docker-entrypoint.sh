#!/bin/sh
set -e
DATA="${RISK_DATA_DIR:-/data}"
if [ ! -f "$DATA/models/model.joblib" ]; then
  echo ">> No trained model found in $DATA: generating data, features and training (first start only)…"
  python -m app.data.generate_dataset
  python -m app.ml.features
  python -m app.ml.train
fi
exec uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --no-server-header
