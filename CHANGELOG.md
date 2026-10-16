# Changelog

All notable changes to this project are documented in this file. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Releases up to 1.7.7 are the original
[Boerderij/Varken](https://github.com/Boerderij/Varken) releases, kept below as they were written.

## [Unreleased]

### Added
- [docs/security-review.md](docs/security-review.md): a dated security review of 3.2.0 (scope, method, findings,
  accepted risks); the next is due by October 2027.
- Policies for the project's own secrets (docs/security.md), static-analysis findings and a code-scanning merge
  gate, and an OpenVEX document for vulnerabilities that don't affect Varken, which the weekly image scan reads
  (docs/dependencies.md); code-review standards and good first issues (CONTRIBUTING.md); two-factor
  authentication and how access is granted (GOVERNANCE.md).
- Every source file starts with SPDX copyright and license lines; a test checks.

### Fixed
- The Device Types and Stream Types pies showed only the sessions playing at that moment, so they were empty whenever
  nobody was watching; they now cover the dashboard's time range (average concurrent sessions), like the original.
- The classic dashboard's Server Popularity strip asked for a point a minute (721 over 12 hours), more than Grafana's
  status history draws; it now asks for about 120, each the busiest moment of its slot.

## [3.2.0] - 2026-10-16

### Added
- **Lidarr item metrics:** `varken_lidarr_queue_item_info` (what's downloading, with the artist and album: the queue
  request now asks Lidarr for them) and `varken_lidarr_album_info` (missing and upcoming albums, with their release
  date and track count). Lidarr had only the job metrics before.
- `dashboard/make_dashboard.py --argus` also writes a classic copy for Argus (`varken-classic.json`) in the original
  dashboard's look: solid-coloured tiles on the original grid, rows coloured by status, a heat strip for Server
  Popularity, a dark map of the US and week-long pies.
- Both Argus copies of the dashboard have Lidarr tables: Music in Queue, Missing Albums and Albums Coming Out.

## [3.1.0] - 2026-10-16

### Changed
- A GeoLite2 download is installed only if it matches the SHA-256 MaxMind publishes beside it
  (`suffix=tar.gz.sha256`, with the same Basic auth). A mismatch, or a checksum that can't be read, fails the
  attempt (retried up to three times), and the archive is deleted without being extracted. Each download now makes
  two requests to MaxMind.

## [3.0.0] - 2026-10-16

**3.0.0 is a major release**: see the breaking changes below and [upgrading](docs/upgrading.md).

### Added
- **A Seerr module** (`[seerr-N]`, `seerr_server_ids`, off by default). Seerr is the successor of Overseerr and
  Jellyseerr. It reads Seerr's request and issue counts (`varken_seerr_requests`, `_requests_by_type`, `_issues`,
  `_issues_by_type`) and each request still waiting, from the 100 newest (`varken_seerr_request_info`, with
  `Title (Year)` and whether it's 4K). The requester's display name is included only with `stream_details = true`,
  and their email address is never read. Seerr's API key acts as its admin; Varken only reads.

### Changed (breaking)
- **New configs check TLS certificates.** `varken.example.ini` sets `verify_ssl = true` for every service, and a
  server on HTTPS with `verify_ssl = false` logs a warning at start-up. An existing `varken.ini` keeps its value.
- **GeoIP needs `maxmind_account_id`.** The legacy MaxMind download, with the license key in the URL, is gone.
  With only a license key, GeoIP is off and an error says what's missing.
- **Masked secrets keep nothing:** `********`, without the last five characters.

### Changed
- The Argus copy of the dashboard has an Instance column (HD or 4K) in its Sonarr and Radarr tables.
- The Argus copy of the dashboard shows Seerr's requests and issues where the original had Ombi's.

## [2.3.0] - 2026-10-16

### Changed
- **Varken logs at INFO by default.** Set `DEBUG=true` (or pass `-D`) for debug logs, which record every request
  URL. `-ND` still works and does nothing more. The image no longer sets `DEBUG=True`.
- The coverage floor is 80 % (was 65 %).
- The default branch is `main` (it was `master`); GitHub redirects old links. A local clone needs
  `git branch -m master main && git fetch && git branch -u origin/main main && git remote set-head origin -a`.

### Fixed
- Requests to the services had no timeout, so one that accepted a connection and never answered held its job's
  thread for good, and the scheduler started another every run. Every request now has a 10-second connect and
  30-second read timeout; a run that times out is marked down (`varken_job_up` 0) and the log names the host.

## [2.2.1] - 2026-10-15

### Fixed
- A key that `varken.ini` doesn't have yet (one a newer Varken added, such as 2.2.0's `maxmind_account_id`) is
  filled in from the example with an INFO line, not an ERROR.
- Filling in missing keys no longer overwrites keys left empty on purpose (an empty `maxmind_license_key`
  came back as the example's placeholder).
- A key missing from `varken.example.ini` as well stops Varken with an error instead of recursing forever.

### Changed
- A successful GeoLite2 download logs `Installed a new GeoLite2 DB (… MB)`; before, only failures were logged.

## [2.2.0] - 2026-10-15

### Added
- `maxmind_account_id` (`VRKN_GLOBAL_MAXMIND_ACCOUNT_ID`): with it, the GeoLite2 database is downloaded the way
  MaxMind documents, with HTTP Basic auth (account ID and license key) instead of the license key in the URL.
  Without it, Varken uses the old URL and logs a warning. Existing `varken.ini` files get the key, empty, on
  their next start.

### Changed
- A GeoLite2 download that fails no longer stops Varken: it logs the error and runs without locations, and the
  next check (every 12 to 24 hours, and not within an hour of a failure, which MaxMind rate-limits) tries
  again. The download has a 60-second timeout, is retried up to three times, and never logs its URL. A new database is swapped in with a rename, so lookups keep working during an
  update.
- The Argus copy of the dashboard leaves out the Ombi and SickChill panels (`dashboard/make_dashboard.py
  --argus`); `dashboard/varken.json` is unchanged.

### Added
- `.gitlab-ci.yml` for the copy of the repository on the maintainer's self-hosted GitLab. GitHub stays the
  project's home and its Actions the required checks; on GitLab a scheduled job mirrors `master` and the tags
  from GitHub (fast-forward only, with a project access token in a masked, protected CI/CD variable), and every
  commit that arrives gets the checks that need no Docker daemon: ruff, yamllint, the unit tests with the
  coverage floor, `promtool check metrics` on a sample scrape, gitleaks over the whole history, actionlint,
  hadolint and `docker compose config`.

## [2.1.0] - 2026-10-15

### Added
- Metrics for what the \*arr apps and Ombi hold, one series per item: `varken_sonarr_queue_item_info`,
  `varken_sonarr_episode_info` (missing and upcoming episodes), `varken_radarr_queue_item_info`,
  `varken_radarr_missing_info`, `varken_sickchill_episode_info` and `varken_ombi_request_info`, and the counts
  `varken_ombi_requests` and `varken_ombi_issues` by status. The requester of an Ombi request is filled in only
  with `stream_details = true`. See [interfaces](docs/interfaces.md#output-prometheus-metrics).
- `varken_tautulli_session_info` (with `stream_details = true`) adds `friendly_name`, `product_version`,
  `quality_profile`, `video_decision`, `state`, `full_location`, and the viewer's city as `latitude` and
  `longitude`, for a map panel.
- A Grafana dashboard, [`dashboard/varken.json`](dashboard/README.md): the original "Varken [Official]" dashboard
  ported to these metrics, with its 35 panels on Grafana's built-in panels. It is generated by
  `dashboard/make_dashboard.py`; CI checks that it is up to date and uses only metrics and labels Varken serves.

### Changed
- **Sonarr and Radarr need version 4 or later.** Both modules now read `/api/v3` (Sonarr's calendar and queue,
  Radarr's movies and queue); the unversioned `/api/...` paths they used before aren't served by current
  releases, so these modules didn't work with them. A reply in an unexpected shape logs an error and marks the
  job down.
- `varken_tautulli_session_info`'s `location` is empty for a viewer who can't be placed (it was `👽`).
- The example `docker-compose.yml` keeps Varken's data in `CONFIG_ROOT/varken/config` (`CONFIG_ROOT` in `.env`,
  required; `/srv/config` in `.env.example`), replacing `VARKEN_CONFIG_DIR`. The docs recommend a host directory
  over a named Docker volume, which `docker volume prune` deletes while its container is stopped.
- A first start without `varken.ini` logs at INFO ("creating it from varken.example.ini") instead of an ERROR.

### Fixed
- The error for a data folder Varken can't write to named the folder and the error the wrong way round.
- Lidarr's calendar jobs crashed on the first album missing tracks, and both Lidarr jobs failed whenever Lidarr
  returned a field Varken didn't know. They now read the reply as it comes and ask for the artist with
  `includeArtist`; the `future` job lists every upcoming album, complete or not, as Sonarr's does.

## [2.0.0] - 2026-10-15

The first HoneyBearTech release: Varken is now a standalone project maintained at
[HoneyBearTech/Varken](https://github.com/HoneyBearTech/Varken), and serves its data as Prometheus metrics
instead of writing it to InfluxDB. See [upgrading](docs/upgrading.md).

### Added
- Prometheus metrics, now Varken's output: a `/metrics` endpoint that is always on (`[prometheus]` `bind`,
  default `0.0.0.0`; `port`, default 9180; `VRKN_PROMETHEUS_*`). It serves `varken_build_info`, and
  `varken_job_up`, `varken_job_last_success_timestamp_seconds` and `varken_job_points` for every job, and for
  Tautulli streams, streams by decision, bandwidth, sessions and library items. Per-viewer metrics (user,
  title, city, progress) need `stream_details = true`; viewer IP addresses are never exported. Scrapes read
  the last run of each job and never call a service. The endpoint has no authentication or TLS: keep it on a
  private network. An existing `varken.ini` gets the `[prometheus]` section, with its defaults, on its first
  start (the file must be writable). The image exposes port 9180, and CI checks a sample scrape with
  `promtool check metrics`. See [interfaces](docs/interfaces.md#output-prometheus-metrics).
- Secrets from files: `VRKN_<SECTION>_<KEY>_FILE` names a file whose contents become the value of
  `VRKN_<SECTION>_<KEY>`, for Docker and compose secrets. Setting both, or a file that can't be read, stops
  Varken. Values read this way are masked in the logs like any other.
- `LOG_TO_FILE=false` logs to stdout only, without a `logs/` folder in the data folder.

### Changed
- GeoIP is optional. Without a MaxMind license key (empty, or the example's placeholder), Varken logs that
  GeoIP is off, gives Tautulli streams the unknown-location values, and never contacts MaxMind or
  `api.ipify.org`. Before, Tautulli without a downloadable GeoLite2 database stopped Varken at start-up.
  `.env.example` now leaves the key empty.
- The image creates `/config` owned by 1000:1000, so a new Docker named volume mounted there is writable
  from the start. Bind-mounted folders still need `chown 1000:1000`.
- **Breaking:** the image is now `ghcr.io/honeybeartech/varken`, built for linux/amd64 and linux/arm64
  (linux/arm/v7 is no longer built).
- **Breaking:** the container runs as an unprivileged user (uid/gid 1000), so the config folder must belong to
  that user (`chown -R 1000:1000`), or run the container with `user:`. The Unraid template uses `--user 99:100`
  and publishes port 9180.
- **Breaking:** Python 3.14 (the image's base is `python:3.14.8-slim`, pinned by digest). Every dependency is
  updated to its current release (requests 2.34, urllib3 2.8, geoip2 5.3, schedule 1.2, distro 1.9) and
  pinned with hashes.
- **Breaking:** the example `docker-compose.yml` runs Varken alone, with no InfluxDB and no Grafana: bring
  your own Prometheus and Grafana (in the maintainer's setup, Argus provides both). It publishes `/metrics` on
  `127.0.0.1:9180` (`VARKEN_METRICS_BIND`), reads settings from `.env` (template `.env.example`) and runs
  Varken with a read-only root filesystem, no capabilities and `no-new-privileges`.
- Releases are signed: the image with cosign (keyless), with an SBOM and SLSA provenance, and the release files
  with a signed `SHA256SUMS`. See [verifying releases](docs/verifying-releases.md).

### Fixed
- **Security:** when neither a stream's IP nor `fallback_ip` was in the GeoLite2 database, Varken looked up
  its public IP with the Tautulli session, which sent the Tautulli API key in plain HTTP to a third-party site
  (ip.42.pl). The lookup now uses a separate HTTPS request to api.ipify.org that carries no credentials. If
  your logs ever showed "Looked the public IP", rotate your Tautulli API key.
- **Security:** API keys, usernames, passwords and URLs set through `VRKN_*` environment variables weren't
  redacted from the logs (only values from `varken.ini` were), and with debug logging on by default they could
  appear in request lines. They're redacted now, as is the MaxMind license key and any secret inside an
  exception message.
- **Security:** the GeoLite2 archive is extracted with Python's `data` filter, so a tampered archive can't
  create links or write outside the data folder.
- A wrong MaxMind license key (HTTP 401) is now reported as such; it used to be reported as a generic download
  problem.
- The startup log works on current `distro` releases, which removed `linux_distribution()`.

### Removed
- **Breaking:** the InfluxDB output. Varken no longer writes to InfluxDB, and no longer reads the `[influxdb]`
  section or the `VRKN_INFLUXDB_*` variables (a `varken.ini` that still has `[influxdb]` works: the section is
  ignored). Data already in InfluxDB stays there, but dashboards built on it, such as upstream's, stop
  updating. Scrape Varken with Prometheus and build Grafana dashboards on the metrics instead
  ([upgrading](docs/upgrading.md#from-upstream-varken-17x-boerderijvarken-to-200)).
- **Breaking:** the `influxdb` Python package, which was archived upstream, and with it msgpack, pytz, six and
  python-dateutil.
- **Breaking:** the Tautulli history import, and `utilities/` (`grafana_build.py`, which imported upstream's
  InfluxDB dashboard into Grafana, and `historical_tautulli_import.py`). The image no longer contains them.
- Links to the original project's Discord, wiki, Docker Hub image and donation page.

## [v1.7.7](https://github.com/Boerderij/Varken/tree/v1.7.7) (2020-12-21)
[Full Changelog](https://github.com/Boerderij/Varken/compare/1.7.6...v1.7.7)

**Implemented enhancements:**
- \[Enhancement\] Ombi 4.0 compatibility [\#186](https://github.com/Boerderij/Varken/issues/186)
  ([samwiseg0](https://github.com/samwiseg0))

**Merged pull requests:**

- v1.7.7 Merge [\#191](https://github.com/Boerderij/Varken/pull/191) 
  ([DirtyCajunRice](https://github.com/DirtyCajunRice))
- Type Error fix [\#177](https://github.com/Boerderij/Varken/pull/177)
  ([derek-miller](https://github.com/derek-miller))

**Fixed bugs:**

- \[BUG\] Influxdb exit code [\#174](https://github.com/Boerderij/Varken/issues/174) 
  ([samwiseg0](https://github.com/samwiseg0))

**Notes:**
- Now built via github actions
- Available on ghcr, quay.io, and dockerhub
- Nightly builds done to accommodate dependabot MRs

## [v1.7.6](https://github.com/Boerderij/Varken/tree/v1.7.6) (2020-01-01)
[Full Changelog](https://github.com/Boerderij/Varken/compare/1.7.5...v1.7.6)

**Merged pull requests:**

- v1.7.6 Merge [\#165](https://github.com/Boerderij/Varken/pull/165) ([samwiseg0](https://github.com/samwiseg0))

**Fixed bugs:**

- \[BUG\] Geolite database download failing [\#164](https://github.com/Boerderij/Varken/issues/164)

**Notes:**
- A MaxMind license key will be required in order to download the GeoLite2 DB. Please see the [wiki](https://wiki.cajun.pro/link/5#bkmrk-maxmind) for more details.

## [v1.7.5](https://github.com/Boerderij/Varken/tree/v1.7.5) (2019-12-11)
[Full Changelog](https://github.com/Boerderij/Varken/compare/1.7.4...v1.7.5)

**Merged pull requests:**

- v1.7.5 Merge [\#162](https://github.com/Boerderij/Varken/pull/162) ([DirtyCajunRice](https://github.com/DirtyCajunRice))
- Add helper itemgetter function for TautulliStream fields [\#157](https://github.com/Boerderij/Varken/pull/157) ([JonnyWong16](https://github.com/JonnyWong16))
- Fix to only use NamedTuple fields from TautulliStream [\#156](https://github.com/Boerderij/Varken/pull/156) ([JonnyWong16](https://github.com/JonnyWong16))

## [1.7.4](https://github.com/Boerderij/Varken/tree/1.7.4) (2019-10-07)
[Full Changelog](https://github.com/Boerderij/Varken/compare/1.7.3...1.7.4)

**Implemented enhancements:**

- \[Enhancement\] Update Tautulli structures to include grandparent\_guid and parent\_guid [\#154](https://github.com/Boerderij/Varken/issues/154)
- \[Enhancement\] Update Tautulli structures to reflect recent changes [\#153](https://github.com/Boerderij/Varken/issues/153)

**Merged pull requests:**

- v1.7.4 Merge [\#155](https://github.com/Boerderij/Varken/pull/155) ([DirtyCajunRice](https://github.com/DirtyCajunRice))

## [1.7.3](https://github.com/Boerderij/Varken/tree/1.7.3) (2019-08-09)
[Full Changelog](https://github.com/Boerderij/Varken/compare/1.7.2...1.7.3)

**Implemented enhancements:**

- \#141 Take monitored status into account for Missing Available Movies check [\#145](https://github.com/Boerderij/Varken/pull/145) ([mikeporterdev](https://github.com/mikeporterdev))

**Fixed bugs:**

- \[BUG\] Varken Crashes when ini is read only [\#146](https://github.com/Boerderij/Varken/issues/146)
- \[BUG\] Missing Available Movies/TV Shows does not take Monitored status into account [\#141](https://github.com/Boerderij/Varken/issues/141)

**Closed issues:**

- \[Feature Request\] Medusa Support [\#148](https://github.com/Boerderij/Varken/issues/148)

**Merged pull requests:**

- v1.7.3 Merge [\#149](https://github.com/Boerderij/Varken/pull/149) ([DirtyCajunRice](https://github.com/DirtyCajunRice))

## [1.7.2](https://github.com/Boerderij/Varken/tree/1.7.2) (2019-06-24)
[Full Changelog](https://github.com/Boerderij/Varken/compare/1.7.1...1.7.2)

**Implemented enhancements:**

- Allow configuration via environment variables [\#137](https://github.com/Boerderij/Varken/issues/137)

**Fixed bugs:**

- \[BUG\] logger invoked before initialization in dbmanager [\#138](https://github.com/Boerderij/Varken/issues/138)

**Merged pull requests:**

- v1.7.2 Merge [\#144](https://github.com/Boerderij/Varken/pull/144) ([DirtyCajunRice](https://github.com/DirtyCajunRice))

## [1.7.1](https://github.com/Boerderij/Varken/tree/1.7.1) (2019-06-04)
[Full Changelog](https://github.com/Boerderij/Varken/compare/1.7.0...1.7.1)

**Fixed bugs:**

- \[BUG\] Sonarr Missing episodes column ordering is incorrect [\#133](https://github.com/Boerderij/Varken/pull/133) ([nicolerenee](https://github.com/nicolerenee))

**Merged pull requests:**

- v1.7.1 Merge [\#134](https://github.com/Boerderij/Varken/pull/134) ([DirtyCajunRice](https://github.com/DirtyCajunRice))

## [1.7.0](https://github.com/Boerderij/Varken/tree/1.7.0) (2019-05-06)
[Full Changelog](https://github.com/Boerderij/Varken/compare/1.6.8...1.7.0)

**Implemented enhancements:**

- \[ENHANCEMENT\] Add album and track totals to artist library from Tautulli [\#127](https://github.com/Boerderij/Varken/issues/127)
- \[Feature Request\] No way to show music album / track count [\#125](https://github.com/Boerderij/Varken/issues/125)

**Fixed bugs:**

- \[BUG\] Invalid retention policy name causing retention policy creation failure [\#129](https://github.com/Boerderij/Varken/issues/129)
- \[BUG\] Unifi errors on unnamed devices [\#126](https://github.com/Boerderij/Varken/issues/126)

**Merged pull requests:**

- v1.7.0 Merge [\#131](https://github.com/Boerderij/Varken/pull/131) ([DirtyCajunRice](https://github.com/DirtyCajunRice))

## [1.6.8](https://github.com/Boerderij/Varken/tree/1.6.8) (2019-04-19)
[Full Changelog](https://github.com/Boerderij/Varken/compare/1.6.7...1.6.8)

**Implemented enhancements:**

- \[Enhancement\] Only drop the invalid episodes from sonarr [\#121](https://github.com/Boerderij/Varken/issues/121)

**Merged pull requests:**

- v1.6.8 Merge [\#122](https://github.com/Boerderij/Varken/pull/122) ([DirtyCajunRice](https://github.com/DirtyCajunRice))

## [1.6.7](https://github.com/Boerderij/Varken/tree/1.6.7) (2019-04-18)
[Full Changelog](https://github.com/Boerderij/Varken/compare/1.6.6...1.6.7)

**Implemented enhancements:**

- \[BUG\] Ombi null childRequest output [\#119](https://github.com/Boerderij/Varken/issues/119)
- \[ENHANCEMENT\] Invalid entries in Sonarr's queue leaves varken unable to process the rest of the queue [\#117](https://github.com/Boerderij/Varken/issues/117)

**Merged pull requests:**

- v1.6.7 Merge [\#120](https://github.com/Boerderij/Varken/pull/120) ([DirtyCajunRice](https://github.com/DirtyCajunRice))

## [1.6.6](https://github.com/Boerderij/Varken/tree/1.6.6) (2019-03-12)
[Full Changelog](https://github.com/Boerderij/Varken/compare/1.6.5...1.6.6)

**Fixed bugs:**

- \[BUG\] TZDATA issue in docker images [\#112](https://github.com/Boerderij/Varken/issues/112)
- \[BUG\] Unifi job does not try again after failure [\#107](https://github.com/Boerderij/Varken/issues/107)
- \[BUG\] Catch ChunkError [\#106](https://github.com/Boerderij/Varken/issues/106)

**Merged pull requests:**

- v1.6.6 Merge [\#116](https://github.com/Boerderij/Varken/pull/116) ([samwiseg0](https://github.com/samwiseg0))

## [1.6.5](https://github.com/Boerderij/Varken/tree/1.6.5) (2019-03-11)
[Full Changelog](https://github.com/Boerderij/Varken/compare/v1.6.4...1.6.5)

**Implemented enhancements:**

- \[Feature Request\] Add new "relayed" and "secure" to Tautulli data pushed to influx [\#114](https://github.com/Boerderij/Varken/issues/114)
- \[BUG\] Changes to Tautulli breaks Varken `TypeError` `Secure` `relayed` [\#111](https://github.com/Boerderij/Varken/issues/111)

**Fixed bugs:**

- \[BUG\] Handle GeoIP Downloads better [\#113](https://github.com/Boerderij/Varken/issues/113)
- \[BUG\] - "None" outputted to stdout many times with no benefit? [\#105](https://github.com/Boerderij/Varken/issues/105)
- \[BUG\] windows file open error [\#104](https://github.com/Boerderij/Varken/issues/104)
- \[BUG\] Not catching DB url resolve [\#103](https://github.com/Boerderij/Varken/issues/103)

**Merged pull requests:**

- v1.6.5 Merge [\#115](https://github.com/Boerderij/Varken/pull/115) ([samwiseg0](https://github.com/samwiseg0))

## [v1.6.4](https://github.com/Boerderij/Varken/tree/v1.6.4) (2019-02-04)
[Full Changelog](https://github.com/Boerderij/Varken/compare/1.6.3...v1.6.4)

**Fixed bugs:**

- \[BUG\] fstring in Varken.py Doesnt allow py version check [\#102](https://github.com/Boerderij/Varken/issues/102)
- \[BUG\] Unifi loadavg is str instead of float [\#101](https://github.com/Boerderij/Varken/issues/101)
- \[BUG\] requestedByAlias to added to Ombi structures  [\#97](https://github.com/Boerderij/Varken/issues/97)

**Merged pull requests:**

- v1.6.4 Merge [\#100](https://github.com/Boerderij/Varken/pull/100) ([DirtyCajunRice](https://github.com/DirtyCajunRice))

## [1.6.3](https://github.com/Boerderij/Varken/tree/1.6.3) (2019-01-16)
[Full Changelog](https://github.com/Boerderij/Varken/compare/v1.6.2...1.6.3)

**Implemented enhancements:**

- \[Feature Request\] ARM, ARMHF and ARM64 Docker Images [\#71](https://github.com/Boerderij/Varken/issues/71)

**Fixed bugs:**

- \[BUG\] Newer influxdb has timeouts and connection errors [\#93](https://github.com/Boerderij/Varken/issues/93)

**Merged pull requests:**

- double typo [\#96](https://github.com/Boerderij/Varken/pull/96) ([DirtyCajunRice](https://github.com/DirtyCajunRice))
- tweaks [\#95](https://github.com/Boerderij/Varken/pull/95) ([DirtyCajunRice](https://github.com/DirtyCajunRice))
- v1.6.3 Merge [\#94](https://github.com/Boerderij/Varken/pull/94) ([DirtyCajunRice](https://github.com/DirtyCajunRice))

## [v1.6.2](https://github.com/Boerderij/Varken/tree/v1.6.2) (2019-01-12)
[Full Changelog](https://github.com/Boerderij/Varken/compare/v1.6.1...v1.6.2)

**Fixed bugs:**

- Rectify influxdb ini [\#91](https://github.com/Boerderij/Varken/issues/91)

**Merged pull requests:**

- v1.6.2 Merge [\#92](https://github.com/Boerderij/Varken/pull/92) ([DirtyCajunRice](https://github.com/DirtyCajunRice))

## [v1.6.1](https://github.com/Boerderij/Varken/tree/v1.6.1) (2019-01-12)
[Full Changelog](https://github.com/Boerderij/Varken/compare/v1.6...v1.6.1)

**Implemented enhancements:**

- \[Feature Request\] Unifi Integration [\#79](https://github.com/Boerderij/Varken/issues/79)

**Fixed bugs:**

- \[BUG\] Unexpected keyword argument 'langCode' while creating OmbiMovieRequest structure [\#88](https://github.com/Boerderij/Varken/issues/88)

**Closed issues:**

- Remove Cisco ASA since Telegraf + SNMP can do the same [\#86](https://github.com/Boerderij/Varken/issues/86)

**Merged pull requests:**

- v1.6.1 Merge [\#90](https://github.com/Boerderij/Varken/pull/90) ([DirtyCajunRice](https://github.com/DirtyCajunRice))

## [v1.6](https://github.com/Boerderij/Varken/tree/v1.6) (2019-01-04)
[Full Changelog](https://github.com/Boerderij/Varken/compare/v1.5...v1.6)

**Implemented enhancements:**

- \[Feature Request\] docker-compose stack install option [\#84](https://github.com/Boerderij/Varken/issues/84)
- Fix missing variables in varken.ini automatically [\#81](https://github.com/Boerderij/Varken/issues/81)
- Create Wiki for FAQ and help docs [\#80](https://github.com/Boerderij/Varken/issues/80)

**Fixed bugs:**

- \[BUG\] url:port does not filter [\#82](https://github.com/Boerderij/Varken/issues/82)

**Merged pull requests:**

- v1.6 Merge [\#85](https://github.com/Boerderij/Varken/pull/85) ([DirtyCajunRice](https://github.com/DirtyCajunRice))

## [v1.5](https://github.com/Boerderij/Varken/tree/v1.5) (2018-12-30)
[Full Changelog](https://github.com/Boerderij/Varken/compare/v1.4...v1.5)

**Implemented enhancements:**

- \[Feature Request\] Add issues from Ombi [\#70](https://github.com/Boerderij/Varken/issues/70)
- Replace static grafana configs with a Public Example [\#32](https://github.com/Boerderij/Varken/issues/32)

**Fixed bugs:**

- \[BUG\] unexpected keyword argument 'channel\_icon' [\#73](https://github.com/Boerderij/Varken/issues/73)
- \[BUG\] Unexpected keyword argument 'addOptions'  [\#68](https://github.com/Boerderij/Varken/issues/68)

**Merged pull requests:**

- v1.5 Merge [\#75](https://github.com/Boerderij/Varken/pull/75) ([DirtyCajunRice](https://github.com/DirtyCajunRice))
- Add Ombi Issues [\#74](https://github.com/Boerderij/Varken/pull/74) ([anderssonoscar0](https://github.com/anderssonoscar0))

## [v1.4](https://github.com/Boerderij/Varken/tree/v1.4) (2018-12-19)
[Full Changelog](https://github.com/Boerderij/Varken/compare/v1.1...v1.4)

**Implemented enhancements:**

- \[Feature Request\] Add tautulli request for library stats [\#64](https://github.com/Boerderij/Varken/issues/64)
- Create randomized 12-24 hour checks to update GeoLite DB after the first wednesday of the month [\#60](https://github.com/Boerderij/Varken/issues/60)
- \[Feature Request\]: Pull list of requests \(instead of just counts\) [\#58](https://github.com/Boerderij/Varken/issues/58)
- Feature Request  , Add Sickchill [\#48](https://github.com/Boerderij/Varken/issues/48)

**Fixed bugs:**

- \[BUG\] Ombi all requests missing half of "pending" option [\#63](https://github.com/Boerderij/Varken/issues/63)
- \[BUG\] asa bug with checking for apikey [\#62](https://github.com/Boerderij/Varken/issues/62)
- \[BUG\] Add Catchall to ombi requests [\#59](https://github.com/Boerderij/Varken/issues/59)

**Closed issues:**

- Unify naming and cleanup duplication in iniparser [\#61](https://github.com/Boerderij/Varken/issues/61)

**Merged pull requests:**

- v1.4 Merge [\#65](https://github.com/Boerderij/Varken/pull/65) ([DirtyCajunRice](https://github.com/DirtyCajunRice))

## [v1.1](https://github.com/Boerderij/Varken/tree/v1.1) (2018-12-11)
[Full Changelog](https://github.com/Boerderij/Varken/compare/v1.0...v1.1)

**Implemented enhancements:**

- Convert missing available to True False  [\#54](https://github.com/Boerderij/Varken/issues/54)
- Handle invalid config better and log it [\#51](https://github.com/Boerderij/Varken/issues/51)
- Feature Request - Include value from Radarr [\#50](https://github.com/Boerderij/Varken/issues/50)
- Change true/false to 0/1 for missing movies [\#47](https://github.com/Boerderij/Varken/issues/47)

**Fixed bugs:**

- \[BUG\] Time does not update from "today" [\#56](https://github.com/Boerderij/Varken/issues/56)
- geoip\_download does not account for moving data folder [\#46](https://github.com/Boerderij/Varken/issues/46)

**Closed issues:**

- Initial startup requires admin access to InfluxDB [\#53](https://github.com/Boerderij/Varken/issues/53)

**Merged pull requests:**

- v1.1 Merge [\#57](https://github.com/Boerderij/Varken/pull/57) ([DirtyCajunRice](https://github.com/DirtyCajunRice))
- Update issue templates [\#55](https://github.com/Boerderij/Varken/pull/55) ([DirtyCajunRice](https://github.com/DirtyCajunRice))

## [v1.0](https://github.com/Boerderij/Varken/tree/v1.0) (2018-12-10)
[Full Changelog](https://github.com/Boerderij/Varken/compare/v0.1...v1.0)

**Implemented enhancements:**

- Add cisco asa from legacy [\#44](https://github.com/Boerderij/Varken/issues/44)
- Add server ID to ombi to differenciate [\#43](https://github.com/Boerderij/Varken/issues/43)
- Create Changelog for nightly release [\#39](https://github.com/Boerderij/Varken/issues/39)
- Create proper logging [\#34](https://github.com/Boerderij/Varken/issues/34)

**Closed issues:**

- Remove "dashboard" folder and subfolders [\#42](https://github.com/Boerderij/Varken/issues/42)
- Remove "Legacy" folder [\#41](https://github.com/Boerderij/Varken/issues/41)
- Create the DB if it does not exist. [\#38](https://github.com/Boerderij/Varken/issues/38)
- create systemd examples [\#37](https://github.com/Boerderij/Varken/issues/37)
- Create a GeoIP db downloader and refresher [\#36](https://github.com/Boerderij/Varken/issues/36)
- Create unique IDs for all scripts to prevent duplicate data [\#35](https://github.com/Boerderij/Varken/issues/35)
- use a config.ini instead of command-line flags [\#33](https://github.com/Boerderij/Varken/issues/33)
- Migrate crontab to python schedule package [\#31](https://github.com/Boerderij/Varken/issues/31)
- Consolidate missing and missing\_days in sonarr.py [\#30](https://github.com/Boerderij/Varken/issues/30)
- Ombi something new \[Request\] [\#26](https://github.com/Boerderij/Varken/issues/26)
- Support for Linux without ASA [\#21](https://github.com/Boerderij/Varken/issues/21)

**Merged pull requests:**

- v1.0 Merge [\#45](https://github.com/Boerderij/Varken/pull/45) ([DirtyCajunRice](https://github.com/DirtyCajunRice))
- varken to nightly [\#40](https://github.com/Boerderij/Varken/pull/40) ([DirtyCajunRice](https://github.com/DirtyCajunRice))

## [v0.1](https://github.com/Boerderij/Varken/tree/v0.1) (2018-10-20)
**Implemented enhancements:**

- The address 172.17.0.1 is not in the database. [\#17](https://github.com/Boerderij/Varken/issues/17)
- Local streams aren't showing with Tautulli [\#16](https://github.com/Boerderij/Varken/issues/16)
- Worldmap panel [\#15](https://github.com/Boerderij/Varken/issues/15)

**Closed issues:**

- Issues with scripts [\#12](https://github.com/Boerderij/Varken/issues/12)
- issue with new tautulli.py [\#10](https://github.com/Boerderij/Varken/issues/10)
- ombi.py fails when attempting to update influxdb [\#9](https://github.com/Boerderij/Varken/issues/9)
- GeoIP Going to Break July 1st [\#8](https://github.com/Boerderij/Varken/issues/8)
- \[Request\] Documentation / How-to Guide [\#1](https://github.com/Boerderij/Varken/issues/1)

**Merged pull requests:**

- v0.1 [\#20](https://github.com/Boerderij/Varken/pull/20) ([samwiseg0](https://github.com/samwiseg0))
- Added selfplug [\#19](https://github.com/Boerderij/Varken/pull/19) ([Roxedus](https://github.com/Roxedus))
- Major rework of the scripts [\#14](https://github.com/Boerderij/Varken/pull/14) ([samwiseg0](https://github.com/samwiseg0))
- fix worldmap after change to maxmind local db [\#11](https://github.com/Boerderij/Varken/pull/11) ([madbuda](https://github.com/madbuda))
- Update sonarr.py [\#7](https://github.com/Boerderij/Varken/pull/7) ([ghost](https://github.com/ghost))
- Create crontabs [\#6](https://github.com/Boerderij/Varken/pull/6) ([ghost](https://github.com/ghost))
- update plex\_dashboard.json [\#5](https://github.com/Boerderij/Varken/pull/5) ([ghost](https://github.com/ghost))
- Update README.md [\#4](https://github.com/Boerderij/Varken/pull/4) ([ghost](https://github.com/ghost))
- added sickrage portion [\#3](https://github.com/Boerderij/Varken/pull/3) ([ghost](https://github.com/ghost))
