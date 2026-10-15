FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 RISK_DATA_DIR=/data
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY docker-entrypoint.sh .
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=180s CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/health')"
ENTRYPOINT ["./docker-entrypoint.sh"]
