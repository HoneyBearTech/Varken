# Varken — Project Context for Claude Code

Collects data from the Plex ecosystem (Tautulli, Sonarr, Radarr, Lidarr, Ombi, SickChill) and UniFi and serves it
as Prometheus metrics at `/metrics` (port 9180). A standalone continuation of Boerderij/Varken (detached from the
fork network), to be integrated into **Argus** (the owner's Prometheus/Grafana stack). It no longer writes to
InfluxDB.

## Before Making Structural Changes
Read the project's notes first. They live outside this repo, in the owner's Obsidian vault **Chronos** at `~/Chronos/Projects/Varken/` (every file is prefixed `varken-`):
- `varken-roadmap.md`: phases (bootstrap, runtime modernization, Prometheus exporter, Argus integration, OpenSSF), the manual GitHub steps, and the Icebox for new ideas
- `varken-Pass-Map.md`: pass-by-pass delivery log; add a row when a pass ships
- `varken-Architecture.md`: components, data flow, config resolution, the proposed metric design, how Varken fits Argus
- `varken-Security-Considerations.md`: assets (an API key for every service, viewer data), trust boundaries, known weaknesses, checklist. Treat it as load-bearing
- `varken-Decisions-Log.md`: ADR-style log of why decisions were made (entries marked **Proposed** still need the owner's call)

The Argus side of the integration is tracked in `~/Chronos/Projects/Argus/` (and built in `~/GitHub/Argus`, which has its own CLAUDE.md and public-repo rules).

Update these files as the project evolves: tick roadmap checkboxes, add a Pass-Map row per pass, add dated Decisions-Log entries. **The notes never go into this repo**, and `.obsidian-docs/` stays gitignored. Chronos is its own private git repo: only commit or push it when the owner asks.

## Owner decisions (2026-10-15)
- **Varken is Prometheus-only.** It always serves `/metrics`; the InfluxDB output (`dbmanager.py`), the outputs
  layer, `[influxdb]`, the `influxdb` package, Tautulli's history import and `utilities/` were removed. Users bring
  their own Prometheus and Grafana (Argus provides both in the owner's setup). Argus stays Prometheus-only.
- **Keep every module working**, but build the Argus integration around **Tautulli first**. Argus already covers the *arrs (exportarr), Plex (Plex exporter) and UniFi (unpoller).

## Stack
- Python 3.14. Entry point `Varken.py`; package `varken/`, with one module per service, `iniparser.py` (config),
  `metrics.py` (the output: runs each job, keeps the points the job hands to `Metrics.write_points`, builds gauges on
  each scrape), `helpers.py` (GeoIP, HTTP), `structures.py` (NamedTuples) and `varkenlogger.py` (logging plus the
  `BlacklistFilter` that redacts secrets). Points are internal: only the metrics in `docs/interfaces.md` are a
  public interface.
- Config: `varken.ini` in the data folder (template `data/varken.example.ini`); every key can be overridden by `VRKN_<SECTION>_<KEY>`. Env values only override: every key must still exist in the ini, which is created from the example on first start.
- Runtime deps in `requirements.in` → `requirements.txt` (hash-pinned): distro, geoip2, prometheus-client, requests,
  schedule. Dev tools in `requirements-dev.in` → `requirements-dev.txt`.
- Image: `Dockerfile` (`python:3.14.x-slim` pinned by version and digest; Dependabot bumps it, uid 1000, read-only-rootfs friendly), published to `ghcr.io/honeybeartech/varken` by `.github/workflows/release.yml` on a signed `vX.Y.Z` tag (SBOM, provenance, cosign, signed SHA256SUMS). Release = a `## [x.y.z]` section in CHANGELOG.md, then `git tag -s`.
- Default branch is `master`.
- GitLab copy: the owner's self-hosted GitLab (CE, LAN only; host facts in Chronos) holds a mirror. GitHub stays
  the home (OpenSSF badges, Scorecard, Dependabot, releases); every change goes to GitHub as a PR, never to
  GitLab. `.gitlab-ci.yml` mirrors GitHub's `master` on a schedule (fast-forward only, `MIRROR_TOKEN` CI/CD
  variable) and re-runs the daemon-free checks; the image build and pip-audit stay GitHub-only. Its images are
  pinned by tag and digest and bumped by hand (Dependabot doesn't read it).

## Conventions
- No secrets, keys, hostnames or IPs in anything committed; `.env` and `config/` are gitignored, so extend `.gitignore` rather than working around it. Examples use `*.example.com` placeholders.
- Any value that can hold a secret must be redacted from logs (`BlacklistFilter.blacklisted_strings`, `INIParser.config_blacklist`). Never send credentials anywhere but the service they belong to (the Tautulli session adds `apikey` to every request it makes).
- Tests are offline (fixtures and mocks, no network). New behaviour gets tests; a bug fix gets a regression test; coverage never drops below the floor in `pyproject.toml` (`fail_under = 65`).
- User-visible changes go under "Unreleased" in `CHANGELOG.md`; docs in `docs/` stay true (mark unbuilt things **Planned**).
- Metric names and labels (`docs/interfaces.md`) are a public interface: renaming or removing one is a breaking change.
- Commits are signed off (`git commit -s`, DCO). Workflows: `permissions: contents: read` at the top, actions pinned to full SHAs, untrusted input only through `env:`. CI's job name "Checks + tests" is the required check, so keep it.
- Ruff rules are `E, F, W, B, S` at line length 120; exceptions are per line with a reason. `ruff format` isn't adopted yet (it's on the roadmap).

## Commands
```sh
python3 -m venv .venv && .venv/bin/pip install --require-hashes --no-deps -r requirements.txt -r requirements-dev.txt
.venv/bin/ruff check . && .venv/bin/yamllint --strict .
.venv/bin/coverage run -m pytest && .venv/bin/coverage report
uv pip compile --generate-hashes --python-version 3.14 requirements.in -o requirements.txt   # same for requirements-dev.in
docker build -t varken:dev .
cp .env.example .env && docker compose up -d      # Varken alone, /metrics on 127.0.0.1:9180 (BYO Prometheus/Grafana)
curl -s 127.0.0.1:9180/metrics | grep varken_job_up
python3 Varken.py -d ./data                       # run from a checkout (needs data/varken.ini)
```
CI also runs actionlint, hadolint, gitleaks (whole history), pip-audit (OSV), an image build that must run as non-root and start read-only, and `docker compose config`; see `.github/workflows/ci.yml`.
