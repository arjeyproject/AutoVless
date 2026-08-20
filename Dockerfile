FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/app/data

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates tzdata \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot
COPY worker ./worker

RUN useradd --create-home --uid 10001 autovless \
 && mkdir -p /app/data \
 && chown -R autovless:autovless /app

USER autovless

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import sqlite3,os,sys; sys.exit(0 if os.path.exists(os.environ['DATA_DIR'] + '/autovless.db') else 1)"

CMD ["python", "-m", "bot.main"]
