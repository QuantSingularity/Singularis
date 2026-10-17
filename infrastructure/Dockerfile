FROM python:3.12-slim

# git is needed to apply test patches for repository (SWE-bench style) tasks
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 sing
WORKDIR /app

COPY pyproject.toml README.md pytest.ini ./
COPY code ./code
COPY infrastructure/smoke ./smoke
RUN pip install --no-cache-dir -e ".[anthropic]"

RUN mkdir -p /app/runs && chown -R sing:sing /app/runs
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp \
    SINGULARIS_LOG_DIR=/app/runs/logs

USER sing
ENTRYPOINT ["singularis"]
