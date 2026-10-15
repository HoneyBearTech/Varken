# Base image pinned by version and multi-arch digest; Dependabot proposes updates to both.
FROM python:3.14.7-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d

# Set by the release workflow from the tag; a local build reports 0.0.0.
ARG VERSION=0.0.0
ARG BRANCH=local
ARG BUILD_DATE=1970-01-01T00:00:00Z

LABEL org.opencontainers.image.title="varken" \
      org.opencontainers.image.description="Collects Plex-ecosystem data for InfluxDB and Prometheus" \
      org.opencontainers.image.url="https://github.com/HoneyBearTech/Varken" \
      org.opencontainers.image.source="https://github.com/HoneyBearTech/Varken" \
      org.opencontainers.image.vendor="HoneyBearTech" \
      org.opencontainers.image.licenses="MIT"

# Debian's security updates for the base image's packages (the Python image can lag behind them). Package
# versions come from the base image's Debian release (pinned above); pinning them as well would break on every
# Debian point release.
# hadolint ignore=DL3005
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# An unprivileged user. 1000:1000 is the first user on most Linux hosts, so the config folder on the host
# belongs to them; compose can run the container as another uid/gid with `user:`.
# /config belongs to it too, so a new named volume starts out writable.
RUN groupadd --gid 1000 varken \
    && useradd --uid 1000 --gid 1000 --no-create-home --home-dir /tmp --shell /usr/sbin/nologin varken \
    && mkdir /config && chown 1000:1000 /config

WORKDIR /app
COPY requirements.txt .
# pip is only needed to install the requirements; removing it drops its vendored packages and their
# vulnerabilities from the image.
RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements.txt \
    && python -m pip uninstall -y pip

COPY Varken.py LICENSE ./
COPY varken ./varken
COPY data ./data
COPY utilities ./data/utilities
RUN sed -i "s/^VERSION = .*/VERSION = \"${VERSION}\"/;s/^BRANCH = .*/BRANCH = '${BRANCH}'/;s/^BUILD_DATE = .*/BUILD_DATE = '${BUILD_DATE}'/" \
        varken/__init__.py

# Config, the GeoLite2 database and logs live in /config (a volume). No .pyc files, so the root filesystem can
# be read-only.
ENV DATA_FOLDER=/config PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DEBUG=True
VOLUME ["/config"]
# The Prometheus /metrics endpoint, when [prometheus] enabled = true.
EXPOSE 9180
USER 1000:1000
# Copies the current example config next to the user's varken.ini, then runs Varken.
CMD ["sh", "-c", "cp /app/data/varken.example.ini /config/varken.example.ini && exec python /app/Varken.py"]
