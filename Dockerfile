FROM python:3.12-slim

# Install the real WarpEP package (needs git). It is what proves an endpoint
# carries traffic rather than merely answering a handshake, and it is where the
# enrolled probing identity comes from when api.cloudflareclient.com is blocked.
# Build with --build-arg WARPEP=0 to skip it.
ARG WARPEP=1

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/app/data

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates tzdata git \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-optional.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
 && if [ "$WARPEP" = "1" ]; then \
      pip install --no-cache-dir -r requirements-optional.txt \
      || echo "WARNING: warpep could not be installed; the vendored copy will be used"; \
    fi

COPY bot ./bot
COPY worker ./worker
# CLEAN_IP_FILES defaults to endpoints/clean-ips.txt, so that directory has to
# exist inside the image or the seed list silently comes back empty.
COPY endpoints ./endpoints

RUN useradd --create-home --uid 10001 autovless \
 && mkdir -p /app/data \
 && chown -R autovless:autovless /app

USER autovless

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import sqlite3,os,sys; sys.exit(0 if os.path.exists(os.environ['DATA_DIR'] + '/autovless.db') else 1)"

CMD ["python", "-m", "bot.main"]
