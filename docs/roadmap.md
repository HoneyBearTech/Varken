# Roadmap

What Varken intends to do over the next year (to October 2027), and what it deliberately won't do. Plans
change; this file is updated when they do, and larger items get a GitHub issue before work starts.
Suggestions are welcome in [Issues](https://github.com/HoneyBearTech/Varken/issues).

## Where it stands

Varken collects data from Tautulli, Sonarr, Radarr, Lidarr, Ombi, Seerr, SickChill and UniFi and serves it as
Prometheus metrics, for Prometheus to scrape and Grafana to chart. The original Boerderij
project stopped at 1.7.7 in December 2020; this fork picked it up in October 2026. The first pass
modernized the runtime and the project around it: Python 3.14, hash-pinned dependencies, a non-root image
for amd64 and arm64 on GHCR, offline tests, CI with linting, secret scanning and dependency auditing, and
signed releases with an SBOM and provenance. It also
fixed two inherited security bugs ([security.md](security.md#fixed-in-200)). **2.0.0** (2026-10-15), the first
release, ships that work.

The second pass built most of Phase 2, which also ships in 2.0.0:

- A Prometheus `/metrics` endpoint (`[prometheus]` `bind`, `port`, default 9180), always on, built from the
  points the existing jobs collect: `varken_job_up`, last-success timestamps and item counts for every
  module, and Tautulli's streams by state and transcode decision, bandwidth and library item counts. Per-viewer
  metrics are behind `stream_details`, off by default ([interfaces.md](interfaces.md#output-prometheus-metrics)).
  CI checks the metrics with `promtool`.
- Varken is Prometheus-only (the maintainer's decision, October 2026): the InfluxDB output, the `[influxdb]`
  settings, the archived `influxdb` client, Tautulli's history import and `utilities/` are gone. Data already
  in InfluxDB stays there ([upgrading.md](upgrading.md)).
- Secrets from files (`VRKN_<SECTION>_<KEY>_FILE`), for Docker and compose secrets.
- Logging to stdout only (`LOG_TO_FILE=false`); the hardened container profile (read-only root filesystem,
  no capabilities, non-root, only `/config` writable) is documented in [security.md](security.md#the-container).
- GeoIP is optional: without a MaxMind license key, Varken runs without locations and contacts neither
  MaxMind nor `api.ipify.org`.

**2.1.0** (2026-10-15) adds item metrics for Sonarr, Radarr, SickChill and Ombi, moves Sonarr and Radarr to
their `/api/v3` (Sonarr 4 and Radarr 4 or later), fixes the Lidarr module, and ships a Grafana dashboard: the
original Varken dashboard ported to these metrics ([dashboard/](../dashboard/README.md)).

**2.2.0** (2026-10-15) downloads the GeoLite2 database with MaxMind's account ID and Basic auth instead of the
license key in the URL, and keeps running when that download fails. **2.2.1** makes upgrades quieter: a
setting new in a version is added to `varken.ini` with an INFO line, not an ERROR.
**2.3.0** (2026-10-16) adds a timeout to every request and logs at INFO by default.

**3.0.0** (2026-10-16) adds a Seerr module and makes three breaking
changes: new configs check TLS certificates, GeoIP needs the MaxMind account ID, and masked secrets keep
nothing ([upgrading](upgrading.md)).

**3.1.0** (2026-10-16) installs a GeoLite2 download only if it matches the SHA-256 MaxMind publishes beside it.
**3.2.0** (2026-10-16) adds Lidarr item metrics (the queue, and missing and upcoming albums) and a classic copy of
the Argus dashboard in the original Varken look.

## Over the following year

**Next, Phase 3: Argus integration** (**Planned**, in the [Argus](https://github.com/HoneyBearTech/Argus) repository)

- A `varken` service and Prometheus job in Argus, a Tautulli dashboard and alerts (for example "Varken
  silent" and "Tautulli unreachable"). Varken stays a standalone project; Argus is one user of it.

**Phase 1: finish modernizing the runtime**

- Sonarr 5's new API (Sonarr 5 is in beta as of October 2026), once Sonarr 5 is stable, alongside `/api/v3`
  for Sonarr 4.
- Raise test coverage to 80 %, and adopt `ruff format` and a wider ruff rule set.

**Phase 2: Prometheus output** (built, see above; [how it works](architecture.md#the-prometheus-output))

- Item metrics for Sonarr, Radarr, SickChill and Ombi, and coordinates for a viewer map: 2.1.0.
- Still to do: detailed metrics for UniFi, which today has only the job metrics.

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

- Done in 3.0.0: a Seerr module (Overseerr and Jellyseerr merged into Seerr in 2026), as Ombi's successor.
- Fuzzing the INI and environment parser.
- Jellyfin and Emby support.

## What Varken will not do

- **Become a general-purpose exporter for apps that already have good Prometheus exporters.** Use
  [exportarr](https://github.com/onedr0p/exportarr) for the \*arr apps, [unpoller](https://github.com/unpoller/unpoller)
  for UniFi, and a Plex exporter for Plex. Varken's Prometheus output focuses on what they don't cover,
  starting with Tautulli. The existing modules keep working.
- **Store data itself.** Prometheus holds the history; Varken keeps only its config, the GeoIP database,
  logs and, for the metrics endpoint, the last run of each job in memory.
- **Act on your media servers.** Varken only reads; it will never change, delete or request anything in
  the services it collects from.
- **Collect data about its users.** It contacts only the services you configure and, with GeoIP on,
  MaxMind and a public-address service in one fallback case.
