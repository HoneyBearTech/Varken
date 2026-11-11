# Varken — Project Context for Claude Code

Collects data from the Plex ecosystem (Tautulli, Sonarr, Radarr, Lidarr, Ombi, Seerr, SickChill) and UniFi and
serves it as Prometheus metrics at `/metrics` (port 9180). A standalone continuation of Boerderij/Varken (detached
from the fork network), which **Argus** (the owner's Prometheus/Grafana stack) runs as an optional service since
Argus 0.8.0. It no longer writes to InfluxDB.

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
- Python 3.15. Entry point `Varken.py`; package `varken/`, with one module per service, `iniparser.py` (config),
  `metrics.py` (the output: runs each job, keeps the points the job hands to `Metrics.write_points`, builds gauges on
  each scrape), `helpers.py` (GeoIP, HTTP), `structures.py` (NamedTuples) and `varkenlogger.py` (logging plus the
  `BlacklistFilter` that redacts secrets). Points are internal: only the metrics in `docs/interfaces.md` are a
  public interface.
- Config: `varken.ini` in the data folder (template `data/varken.example.ini`); every key can be overridden by `VRKN_<SECTION>_<KEY>`. The ini is created from the example on first start and never written again: a key it lacks takes the example's value in memory (`ConfigFile` in `iniparser.py`), so every key must be in one of the two files, even when its env variable is set.
- Runtime deps in `requirements.in` → `requirements.txt` (hash-pinned): distro, maxminddb, prometheus-client, requests,
  schedule. Dev tools in `requirements-dev.in` → `requirements-dev.txt`.
- Image: `Dockerfile` (`python:3.15.x-slim` pinned by version and digest; Dependabot bumps it, uid 1000, read-only-rootfs friendly), published to `ghcr.io/honeybeartech/varken` by `.github/workflows/release.yml` on a signed `vX.Y.Z` tag (SBOM, provenance, cosign, signed SHA256SUMS). Release = a `## [x.y.z]` section in CHANGELOG.md, then `git tag -s`.
- Default branch is `main` (renamed from `master` on 2026-10-16).
- GitLab copy: the owner's self-hosted GitLab (CE, LAN only; host facts in Chronos) holds a mirror. GitHub stays
  the home (OpenSSF badges, Scorecard, Dependabot, releases); every change goes to GitHub as a PR, never to
  GitLab. `.gitlab-ci.yml` mirrors GitHub's default branch on a schedule (fast-forward only, `MIRROR_TOKEN` CI/CD
  variable) and re-runs the daemon-free checks; the image build and pip-audit stay GitHub-only. Its images are
  pinned by tag and digest and bumped by hand (Dependabot doesn't read it).

## Conventions
- No secrets, keys, hostnames or IPs in anything committed; `.env` and `config/` are gitignored, so extend `.gitignore` rather than working around it. Examples use `*.example.com` placeholders.
- Any value that can hold a secret must be redacted from logs (`BlacklistFilter.blacklisted_strings`, `INIParser.config_blacklist`). Never send credentials anywhere but the service they belong to (the Tautulli session adds `apikey` to every request it makes).
- Tests are offline (fixtures and mocks, no network). New behaviour gets tests; a bug fix gets a regression test; coverage never drops below the floor in `pyproject.toml` (`fail_under = 80`).
- User-visible changes go under "Unreleased" in `CHANGELOG.md`; docs in `docs/` stay true (mark unbuilt things **Planned**).
- Metric names and labels (`docs/interfaces.md`) are a public interface: renaming or removing one is a breaking change.
- Commits are signed off (`git commit -s`, DCO) and signed: the default-branch ruleset requires verified signatures, and the maintainer's build host signs its commits and tags with its own key (`docs/security.md`). Workflows: `permissions: contents: read` at the top, actions pinned to full SHAs, untrusted input only through `env:`. CI's job name "Checks + tests" is a required check, so keep it. How a change is merged: "Pull requests and merging" below. New source files start with the SPDX lines (`# SPDX-FileCopyrightText: 2026 HoneyBearTech` / `# SPDX-License-Identifier: MIT`); `tests/test_licensing.py` checks.
- Ruff runs every rule family (`select = ["ALL"]`) at line length 120, minus the few ignores listed with their reasons in `pyproject.toml`; exceptions are per line with a reason (`# noqa: CODE - reason`). So every function is annotated and, outside `tests/`, has a docstring. An import that only annotations use goes in an `if TYPE_CHECKING:` block, never behind `lazy` (ruff's suggested fix): the Fuzz workflow runs on Python 3.14, and `tests/test_fuzz_python.py` checks. Code is formatted with `ruff format` (single quotes); CI fails on unformatted files.

## Pull requests and merging
Every change reaches `main` as a squash-merged pull request, never by a push. The default-branch ruleset requires the checks "Checks + tests", "DCO sign-off", "Dependency review", "Analyze (python)" and "Analyze (actions)", a branch that is up to date with `main`, signed commits, a clean CodeQL gate (no alert at error level, no security alert rated high or above), and an approval from a code owner given after the last push. The owner (@HoneyBearTech) is the only code owner.

- **From the maintainer's build host**, `gh` and git act as the machine account `honeybeartech-ops`. It has write access and no admin rights, so it can't bypass the ruleset or approve a PR. Push a branch, open the PR, wait for its checks, report, and stop. The owner reviews and approves the PR under their own account.
- **Merge only when the owner asks for that PR by number** ("merge 51"). An approval alone, or a request for the end result, is not that. First check that every check on the PR is green, that code scanning shows no open alert on it (`gh api "repos/HoneyBearTech/Varken/code-scanning/alerts?ref=refs/pull/<n>/merge&state=open" -q length` prints `0`), that the owner's approval is on the PR's current head (`gh api repos/HoneyBearTech/Varken/pulls/<n>/reviews`) and that the branch is up to date. Then `gh pr merge <n> --squash --delete-branch`, and watch the runs on `main` to the end.
- **A push dismisses the approval**, so finish the PR before the owner reviews it. Change a pushed branch with a new commit, never by amending and force-pushing; the squash merge folds the commits into one.
- **A PR opened under the owner's own account** can't get that approval (GitHub doesn't let an author approve their own PR), so the owner merges it through the ruleset's admin pull-request bypass (`gh pr merge --squash --admin`, owner's decision 2026-10-16, `GOVERNANCE.md`), after the same checks: the bypass also skips the ruleset's CodeQL gate. The machine account can't use the bypass.
- **Release tags** (`vX.Y.Z`, signed) are pushed only when the owner asks. The "release tags" ruleset lets a tag be created but never moved or deleted, so check the commit and its changelog section first.

## Commands
```sh
python3 -m venv .venv && .venv/bin/pip install --require-hashes --no-deps -r requirements.txt -r requirements-dev.txt
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/yamllint --strict .
.venv/bin/coverage run -m pytest && .venv/bin/coverage report
uv pip compile --generate-hashes --python-version 3.15 requirements.in -o requirements.txt   # same for requirements-dev.in
docker build -t varken:dev .
cp .env.example .env && docker compose up -d      # Varken alone, /metrics on 127.0.0.1:9180 (BYO Prometheus/Grafana)
curl -s 127.0.0.1:9180/metrics | grep varken_job_up
python3 Varken.py -d ./data                       # run from a checkout (needs data/varken.ini)
```
CI also runs actionlint, hadolint, gitleaks (whole history), pip-audit (OSV), an image build that must run as non-root and start read-only, and `docker compose config`; see `.github/workflows/ci.yml`.
