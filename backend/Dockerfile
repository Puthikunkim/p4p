# V-CORE backend — Python 3.11 + liblsl (pylsl's native dependency).
FROM python:3.11-slim-bookworm

# liblsl: the native library pylsl binds to (no Linux pip wheel bundles it).
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && curl -fsSL -o /tmp/liblsl.deb \
      https://github.com/sccn/liblsl/releases/download/v1.17.7/liblsl-1.17.7-jammy_amd64.deb \
 && apt-get install -y --no-install-recommends /tmp/liblsl.deb \
 && rm -f /tmp/liblsl.deb \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the package + dependencies into the system environment. At runtime the
# source is bind-mounted over /app and PYTHONPATH=/app makes the live code win, so
# `uvicorn --reload` (set in docker-compose) picks up edits.
COPY . .
RUN pip install --no-cache-dir .

ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "vcore.app:app", "--host", "0.0.0.0", "--port", "8000"]
