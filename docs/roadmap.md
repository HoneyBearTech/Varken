# Roadmap

What Varken intends to do over the next year (to October 2027), and what it deliberately won't do. Plans
change; this file is updated when they do, and larger items get a GitHub issue before work starts.
Suggestions are welcome in [Issues](https://github.com/HoneyBearTech/Varken/issues).

## Where it stands

Varken collects data from Tautulli, Sonarr, Radarr, Lidarr, Ombi, SickChill and UniFi and writes it to
InfluxDB 1.x for Grafana dashboards. The original Boerderij project stopped at 1.7.7 in December 2020; this
fork picked it up in October 2026. The first pass modernized the runtime and the project around it: Python
3.14, hash-pinned dependencies, a non-root image for amd64 and arm64 on GHCR, offline tests, CI with
linting, secret scanning and dependency auditing, and signed releases with an SBOM and provenance. It also
fixed two inherited security bugs ([security.md](security.md#fixed-in-200)). **2.0.0**, the first release,
ships that work.

## Over the following year

**Phase 1: finish modernizing the runtime**

- Replace the archived `influxdb` client with direct HTTP writes of InfluxDB line protocol to InfluxDB 1.x
  ([dependencies.md](dependencies.md#the-archived-influxdb-client)).
- Log at INFO by default instead of DEBUG.
- `verify_ssl` on by default. This is a breaking change and will be announced in the changelog.
- Download the GeoLite2 database with MaxMind's account ID + license key Basic authentication, instead of
  the license key in the URL.
- Timeouts on every request to the services, InfluxDB and MaxMind.
- Fix `utilities/historical_tautulli_import.py`, which fails at start-up.
- Check the Sonarr and Radarr modules against current releases, which serve their API under `/api/v3`.
- Raise test coverage to 80 %, and adopt `ruff format` and a wider ruff rule set.

**Phase 2: Prometheus output** ([design](architecture.md#planned-prometheus-output))

- An optional `/metrics` endpoint (`[prometheus]` `enabled`, `bind`, `port`, default 9180), with gauges
  updated by the existing jobs. Tautulli first: streams by state and transcode decision, bandwidth, library
  item counts, plus `varken_up` and last-success timestamps for every module.
- InfluxDB becomes optional (`[influxdb]` `enabled`, on by default), so either or both outputs can be used.
- Secrets from files (`VRKN_<SECTION>_<KEY>_FILE`), for Docker and compose secrets.
- Logging to stdout only, as an option, and a documented hardened profile (read-only root filesystem, no
  capabilities, non-root, only `/config` writable).
- Then metrics for the other modules.

**Phase 3: Argus integration** (in the [Argus](https://github.com/HoneyBearTech/Argus) repository)

- A `varken` service and Prometheus job in Argus, a Tautulli dashboard and alerts (for example "Varken
  silent" and "Tautulli unreachable"). Varken stays a standalone project; Argus is one user of it.

**Security and project health**

- Turn on GitHub Issues, private vulnerability reporting, secret scanning with push protection and
  Dependabot security updates.
- Protect the default branch with a ruleset: changes only through pull requests that pass "Checks + tests",
  no force-pushes or deletion.
- Sign every release tag (`git tag -s`, key in `.github/allowed_signers`) and every release, starting with
  2.0.0 ([verifying-releases.md](verifying-releases.md)).
- The [OpenSSF Best Practices badge](https://www.bestpractices.dev/projects/15525) at Passing, then Silver,
  and OSPS Baseline Levels 1 and 2.
- A healthy OpenSSF Scorecard: pinned dependencies, signed releases, branch protection, SAST.
- Close the remaining [known weaknesses](security.md#known-weaknesses) (the Phase 1 items above, and full
  masking of secrets in logs).

## Later, if there's interest (icebox)

- InfluxDB 2 and 3 support.
- An Overseerr/Jellyseerr module, as Ombi's successor.
- Refreshed Grafana dashboards for standalone InfluxDB users (current Grafana panels).
- Fuzzing the INI and environment parser.
- Jellyfin and Emby support.

## What Varken will not do

- **Become a general-purpose exporter for apps that already have good Prometheus exporters.** Use
  [exportarr](https://github.com/onedr0p/exportarr) for the \*arr apps, [unpoller](https://github.com/unpoller/unpoller)
  for UniFi, and a Plex exporter for Plex. Varken's Prometheus output focuses on what they don't cover,
  starting with Tautulli. The existing modules keep working.
- **Store data itself.** InfluxDB (or Prometheus) holds the data; Varken keeps only its config, the GeoIP
  database and logs.
- **Act on your media servers.** Varken only reads; it will never change, delete or request anything in
  the services it collects from.
- **Collect data about its users.** It contacts only the services you configure, MaxMind, and a
  public-address service in one fallback case.
