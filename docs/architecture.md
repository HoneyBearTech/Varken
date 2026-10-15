# How it works

Varken is a long-running Python process with no user interface. On a schedule it asks the services you
configure for their current state, turns the answers into InfluxDB points, and writes them to InfluxDB,
where Grafana dashboards read them. It only reads from those services. Its security properties are in
[security.md](security.md) and the [assurance case](assurance-case.md); every input and output is listed in
[interfaces.md](interfaces.md).

```
Tautulli ─┐                                     ┌─▶ InfluxDB 1.x (database "varken") ◀── Grafana
Sonarr ───┤                                     │
Radarr ───┤  HTTP(S) GET,  ┌──────────────────┐ │
Lidarr ───┼─ API key ─────▶│      Varken      │─┤
Ombi ─────┤                │ scheduled jobs   │ │
SickChill ┤                └──────────────────┘ └─▶ logs (stdout, data/logs/varken.log)
UniFi ────┘                  │            ▲
                             │ lookup     │ download every ~30 days
                             ▼            │ (license key)
                    data/GeoLite2-City.mmdb ◀── MaxMind

Planned: Varken ──▶ /metrics (:9180) ◀── Prometheus scrape
```

## Actors and what they do

| Actor | Does |
| --- | --- |
| Operator | Installs Varken, writes `varken.ini` or the environment, supplies API keys and the MaxMind license key, runs InfluxDB and Grafana, and reads the dashboards. |
| Media services (Tautulli, Sonarr, Radarr, Lidarr, Ombi, SickChill) | Answer Varken's read-only API requests with their current activity, queues, calendars, requests and library counts. |
| UniFi controller | Answers a login and device-statistics requests for one gateway. |
| Viewers | Don't interact with Varken, but their streams (username, title, device, approximate location) are what Tautulli reports and Varken records. |
| MaxMind | Serves the GeoLite2-City database to the operator's license key. |
| InfluxDB | Stores what Varken writes, for 30 days by default. |
| Grafana (and its users) | Reads InfluxDB; Varken never talks to it, except through the optional `grafana_build.py` utility. |
| Prometheus (**Planned**) | Will scrape Varken's `/metrics` endpoint. |

## Components

| Component | File | Role |
| --- | --- | --- |
| Entry point | [`Varken.py`](../Varken.py) | Parses the command line, finds the data folder, sets up logging, loads the config, connects to InfluxDB, registers one job per enabled server and feature, then runs the scheduler loop. |
| Config | [`varken/iniparser.py`](../varken/iniparser.py) | Reads `varken.ini`, applies `VRKN_*` overrides, validates URLs and `fallback_ip`, fills missing keys from the example, and builds one server record per section ([configuration.md](configuration.md)). |
| Data shapes | [`varken/structures.py`](../varken/structures.py) | Named tuples for each server's settings and for the API responses Varken understands. |
| Modules | [`varken/tautulli.py`](../varken/tautulli.py), [`sonarr.py`](../varken/sonarr.py), [`radarr.py`](../varken/radarr.py), [`lidarr.py`](../varken/lidarr.py), [`ombi.py`](../varken/ombi.py), [`sickchill.py`](../varken/sickchill.py), [`unifi.py`](../varken/unifi.py) | One class per service. Each job makes its requests, maps the answer onto the data shapes, builds InfluxDB points and hands them to the writer. |
| InfluxDB writer | [`varken/dbmanager.py`](../varken/dbmanager.py) | Connects at start-up, creates the `varken` database and retention policy if needed, and writes points. |
| Helpers | [`varken/helpers.py`](../varken/helpers.py) | `connection_handler()` sends every service request and handles its errors; `GeoIPHandler` downloads, extracts and reads the GeoLite2 database; config value checks. |
| Logging | [`varken/varkenlogger.py`](../varken/varkenlogger.py) | Console and rotating file logs, with a filter that masks configured secrets. |
| Utilities | [`utilities/`](../utilities/) | Hand-run scripts: Grafana dashboard import and Tautulli history import ([interfaces.md](interfaces.md#utilities)). |

## A run, from start to finish

1. **Start-up.** Varken finds the data folder (`DATA_FOLDER`, `-d`, or `data/`) and stops if it doesn't
   exist. It logs to the console and `logs/varken.log`.
2. **Config.** It reads `varken.ini` (creating it from `varken.example.ini` if missing), applies the
   environment overrides, and builds the list of servers per enabled service. An invalid URL or private
   `fallback_ip` stops it here.
3. **InfluxDB.** It pings InfluxDB and stops if it can't reach it. If the `varken` database doesn't exist,
   it creates it with the retention policy `varken 30d-1h`.
4. **GeoIP** (only with Tautulli enabled). It opens `GeoLite2-City.mmdb`, downloading it from MaxMind
   first if it's missing; it stops if that download fails. A job checks every 12 to 24 hours whether the file
   is more than 30 days old and replaces it if so. Only the `.mmdb` file is extracted from the archive, with
   Python's `data` extraction filter, so the archive can't write anywhere else.
5. **Jobs.** For every enabled server and feature (for example `tautulli-1` activity, `sonarr-2` queue) it
   registers a job with the [schedule](https://schedule.readthedocs.io/) library at that feature's
   `*_run_seconds` interval. It stops if no service is enabled.
6. **Loop.** It runs every job once immediately, then checks every second for jobs that are due. Each job
   runs in its own thread, so a slow service doesn't delay the others.
7. **Each job** sends its requests through `connection_handler()`, turns the JSON into points (described in
   [interfaces.md](interfaces.md#output-influxdb)) and writes them in one batch.

### When something fails

- **A service is down, slow or answers with an error**: the job logs it (401: wrong API key, 404: wrong
  URL, connection or TLS errors) and writes nothing; the next run tries again. Requests have no timeout,
  so a service that accepts the connection but never answers holds that job's thread
  ([a known weakness](security.md#known-weaknesses)).
- **An answer has a shape Varken doesn't expect**: an unknown field is logged and that item (or that
  run) skipped; a missing field ends that run with a Python traceback in the log. Either way the next run
  tries again.
- **UniFi rejects the session**: the job logs in again once, then gives up until its next run.
- **InfluxDB is unreachable after start-up, or rejects a write**: that batch is dropped, with an error or a
  traceback in the log. Varken doesn't queue data for later.
- **A viewer can't be located**: Varken tries `fallback_ip`, then the host's own public address from
  `https://api.ipify.org`, and records placeholder location values if all fail.

## State

Varken keeps almost nothing itself. Its data folder holds `varken.ini`, the GeoLite2 database (which can
be downloaded again) and logs. Everything it collects is in InfluxDB, which keeps it for the retention
policy's 30 days unless you change the policy. Restarting Varken loses nothing but jobs in flight.

## Planned: Prometheus output

**Planned, not built** ([roadmap](roadmap.md), Phase 2). Varken will optionally expose a Prometheus
`/metrics` endpoint, so it can feed Prometheus-based stacks such as the maintainer's
[Argus](https://github.com/HoneyBearTech/Argus), which retired InfluxDB:

```
Tautulli (first), other modules later ─▶ Varken jobs ─┬─▶ InfluxDB (optional, on by default)
                                                      └─▶ in-memory gauges ─▶ GET /metrics (:9180) ◀── Prometheus
```

- The same scheduled jobs update both outputs; a scrape only reads the latest values and never calls a
  service.
- InfluxDB becomes optional (`[influxdb] enabled`), so a Prometheus-only setup needs no InfluxDB. Existing
  InfluxDB users are unaffected.
- Tautulli comes first, because its per-stream detail (transcode decision, quality, player, bandwidth,
  location) and library counts are what other exporters don't provide. Sonarr, Radarr, Lidarr and UniFi
  already have good Prometheus exporters, so their Varken metrics come later.
- Per-viewer labels are left out by default; viewer addresses are never labels.
- It must run in a hardened container: read-only root filesystem, no capabilities, non-root, with secrets
  read from files (`VRKN_<SECTION>_<KEY>_FILE`).

The proposed settings and metric names are in [configuration.md](configuration.md#planned-settings) and
[interfaces.md](interfaces.md#prometheus-metrics-planned).

## Technology

Python 3.14 with [requests](https://requests.readthedocs.io/), [geoip2](https://github.com/maxmind/GeoIP2-python),
the [influxdb](https://github.com/influxdata/influxdb-python) client (archived upstream; to be replaced,
see [dependencies.md](dependencies.md)), [schedule](https://github.com/dbader/schedule) and
[distro](https://github.com/python-distro/distro). Distributed as a container image for linux/amd64 and
linux/arm64, or run from a checkout.
