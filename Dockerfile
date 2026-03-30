FROM python:3.13-slim

ARG TARGETARCH=amd64
ARG SUPERCRONIC_VERSION=v0.2.32

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

RUN case "${TARGETARCH}" in \
      amd64) SUPERCRONIC_ARCH="amd64"; SUPERCRONIC_SHA1SUM="7da26ce6ab48d75e97f7204554afe7c80779d4e0" ;; \
      arm64) SUPERCRONIC_ARCH="arm64"; SUPERCRONIC_SHA1SUM="7f89438e7810669d3e0ea488a202aaf422cc2fdf" ;; \
      *) echo "Unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
 && curl -fsSLo /usr/local/bin/supercronic \
      "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${SUPERCRONIC_ARCH}" \
 && echo "${SUPERCRONIC_SHA1SUM}  /usr/local/bin/supercronic" | sha1sum -c - \
 && chmod +x /usr/local/bin/supercronic

COPY pyproject.toml /app/pyproject.toml
COPY docs /app/docs
COPY src /app/src
COPY .env.example /app/.env.example
COPY crontab /app/crontab

RUN pip install --no-cache-dir .

RUN mkdir -p /app/var

CMD ["/bin/sh", "-lc", "python -m europeya_matrix_redactor.cli render-crontab --output /app/var/crontab && exec supercronic /app/var/crontab"]
