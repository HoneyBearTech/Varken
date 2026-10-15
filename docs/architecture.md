# How it works

Varken is a long-running Python process with no user interface. On a schedule it asks the services you
configure for their current state, turns the answers into points, and keeps the last run of each job in
memory. A Prometheus `/metrics` endpoint builds metrics from those snapshots whenever Prometheus scrapes it,
and Grafana dashboards read them from Prometheus. It only reads from those services. Its security properties are in
[security.md](security.md) and the [assurance case](assurance-case.md); every input and output is listed in
[interfaces.md](interfaces.md).

```
Tautulli ─┐
Sonarr ───┤
Radarr ───┤  HTTP(S) GET,  ┌──────────────────┐
Lidarr ───┼─ API key ─────▶│      Varken      │─┬─▶ GET /metrics (:9180) ◀── Prometheus scrape ◀── Grafana
Ombi ─────┤                │ scheduled jobs   │ │
SickChill ┤                └──────────────────┘ │
UniFi ────┘                  │            ▲     └─▶ logs (stdout; data/logs/varken.log unless LOG_TO_FILE=false)
                             │ lookup     │ download every ~30 days
                             ▼            │ (license key; only with GeoIP on)
                    data/GeoLite2-City.mmdb ◀── MaxMind
```

## Actors and what they do

| Actor | Does |
| --- | --- |
| Operator | Installs Varken, writes `varken.ini` or the environment, supplies API keys and, optionally, the MaxMind license key, runs Prometheus and Grafana, and reads the dashboards. |
| Media services (Tautulli, Sonarr, Radarr, Lidarr, Ombi, SickChill) | Answer Varken's read-only API requests with their current activity, queues, calendars, requests and library counts. |
| UniFi controller | Answers a login and device-statistics requests for one gateway. |
| Viewers | Don't interact with Varken, but their streams (username, title, device and, with GeoIP on, approximate location) are what Tautulli reports and Varken records. |
| MaxMind | Serves the GeoLite2-City database to the operator's license key. Not contacted when no key is set (GeoIP off). |
| Prometheus | Scrapes Varken's `/metrics` endpoint and stores the metrics for its own retention time. It sends no credentials and gets none. [Argus](https://github.com/HoneyBearTech/Argus) is one such stack (that integration is planned, in the Argus repository). |
| Grafana (and its users) | Reads the metrics from Prometheus; Varken never talks to it. |

## Components

| Component | File | Role |
| --- | --- | --- |
| Entry point | [`Varken.py`](../Varken.py) | Parses the command line, finds the data folder, sets up logging, loads the config, starts the metrics server, registers one job per enabled server and feature, then runs the scheduler loop. `thread()` starts each job in its own thread, through the metrics collector. |
| Config | [`varken/iniparser.py`](../varken/iniparser.py) | Reads `VRKN_*_FILE` secrets, reads `varken.ini`, applies `VRKN_*` overrides, validates URLs, `fallback_ip` and the `[prometheus]` address and port, fills missing keys from the example, and builds the `[prometheus]` settings and one server record per section ([configuration.md](configuration.md)). |
| Data shapes | [`varken/structures.py`](../varken/structures.py) | Named tuples for the metrics endpoint's settings (`PrometheusServer`), each server's settings and the API responses Varken understands. |
| Modules | [`varken/tautulli.py`](../varken/tautulli.py), [`sonarr.py`](../varken/sonarr.py), [`radarr.py`](../varken/radarr.py), [`lidarr.py`](../varken/lidarr.py), [`ombi.py`](../varken/ombi.py), [`sickchill.py`](../varken/sickchill.py), [`unifi.py`](../varken/unifi.py) | One class per service. Each job makes its requests, maps the answer onto the data shapes, builds points and hands them to the metrics collector (`Metrics.write_points`). |
| Metrics collector | [`varken/metrics.py`](../varken/metrics.py) | Varken's output. Runs each job, records whether it succeeded and the points it wrote, and builds the metrics from those snapshots on every scrape; serves them with prometheus_client's HTTP server. |
| Helpers | [`varken/helpers.py`](../varken/helpers.py) | `connection_handler()` sends every service request, handles its errors and flags a failed request for the metrics (`request_state`); `geoip_handler()` returns a `GeoIPHandler`, which downloads, extracts and reads the GeoLite2 database, or `NoGeoIP` when there's no license key; config value checks. |
| Logging | [`varken/varkenlogger.py`](../varken/varkenlogger.py) | Console and (unless `LOG_TO_FILE=false`) rotating file logs, with a filter that masks configured secrets. |

## A run, from start to finish

1. **Start-up.** Varken finds the data folder (`DATA_FOLDER`, `-d`, or `data/`) and stops if it doesn't
   exist. It logs to the console and, unless `LOG_TO_FILE=false`, to `logs/varken.log`.
2. **Config.** It reads the `VRKN_*_FILE` secrets into their variables, reads `varken.ini` (creating it from
   `varken.example.ini` if missing, and filling in missing keys), applies the environment overrides, and
   builds the `[prometheus]` settings and the list of servers per enabled service. An unreadable or
   doubly-set secret, an invalid URL, a private `fallback_ip` or an invalid `[prometheus]` `bind` or `port`
   stops it here. An `[influxdb]` section left over from upstream Varken is ignored.
3. **Metrics server.** It starts the metrics HTTP server on `bind`:`port`, and stops if it can't open the
   port (for example because something else has it).
4. **GeoIP** (only with Tautulli enabled and a MaxMind license key). It opens `GeoLite2-City.mmdb`,
   downloading it from MaxMind first if it's missing; it stops if that download fails. A job checks every 12
   to 24 hours whether the file is more than 30 days old and replaces it if so. Only the `.mmdb` file is
   extracted from the archive, with Python's `data` extraction filter, so the archive can't write anywhere
   else. Without a key, GeoIP is off: every stream gets an unknown location, and Varken contacts neither
   MaxMind nor `api.ipify.org`.
5. **Jobs.** For every enabled server and feature (for example `tautulli-1` activity, `sonarr-2` queue) it
   registers a job with the [schedule](https://schedule.readthedocs.io/) library at that feature's
   `*_run_seconds` interval. It stops if no service is enabled.
6. **Loop.** It runs every job once immediately, then checks every second for jobs that are due. Each job
   runs in its own thread, so a slow service doesn't delay the others.
7. **Each job** sends its requests through `connection_handler()`, turns the JSON into points and hands
   them in one batch to the metrics collector, which builds the
   [metrics](interfaces.md#output-prometheus-metrics) from them.

### When something fails

- **A service is down, slow or answers with an error**: the job logs it (401: wrong API key, 404: wrong
  URL, connection or TLS errors) and records nothing; the next run tries again. Requests have no timeout,
  so a service that accepts the connection but never answers holds that job's thread
  ([a known weakness](security.md#known-weaknesses)).
- **An answer has a shape Varken doesn't expect**: an unknown field is logged and that item (or that
  run) skipped; a missing field ends that run with a Python traceback in the log. Either way the next run
  tries again.
- **UniFi rejects the session**: the job logs in again once, then gives up until its next run.
- **A failed request or any error the job logs about its service** (including a single item skipped for an
  unexpected shape) marks the job down (`varken_job_up` 0) and drops its snapshot, so its data metrics
  disappear until a run succeeds. Varken doesn't queue data for later.
- **A viewer can't be located** (GeoIP on): Varken tries `fallback_ip`, then the host's own public address
  from `https://api.ipify.org`, and records placeholder location values if all fail.

## State

Varken keeps almost nothing itself. Its data folder holds `varken.ini`, the GeoLite2 database (which can
be downloaded again) and logs. In memory it holds the last successful run of each job. The history is in
Prometheus, which keeps what it scrapes for its own retention time. Restarting Varken loses nothing but jobs
in flight and those snapshots, which the first runs after start-up rebuild.

## The Prometheus output

Varken's only output, always on ([configuration](configuration.md#prometheus)): its metrics at `/metrics`,
for Prometheus to scrape.

```
module job ──▶ Metrics.write_points ─▶ this run's points
   │
   └─ run by Metrics.run: on success, the run's points replace the job's snapshot; on failure, it's dropped

Prometheus ──GET /metrics──▶ prometheus_client HTTP server ──▶ Metrics.collect: builds gauges from the snapshots
```

- **Jobs.** `thread()` in [`Varken.py`](../Varken.py) runs each module job through `Metrics.run`, keyed by
  service, server id and job name (the GeoLite2 update isn't a module job and just runs). `Metrics.run`
  clears the run's state, runs the job, and collects every batch of points the job hands to
  `Metrics.write_points`. Points written outside a job are ignored.
- **Success.** A run succeeded when no request failed (`connection_handler()` sets
  `helpers.request_state.failed`, per thread), no `ERROR` was logged from the job's thread (a logging
  handler watches for it), and the job didn't raise. Then its points replace the job's snapshot and its
  last-success time is set. Otherwise the job is marked down and its snapshot is emptied, so no stale data
  is exported.
- **Scrapes.** A scrape takes a copy of the snapshots under a lock and builds the gauges from it: the job
  metrics for every job, and the Tautulli metrics from the `activity` and `stats` points. It never calls a
  service and has no effect on the jobs. Per-viewer metrics are built only with `stream_details = true`;
  the viewer IP address isn't in the points, so it can't be exported.
- **Server.** prometheus_client's HTTP server, started once on `bind`:`port`, in its own thread. Plain
  HTTP without authentication ([security.md](security.md#the-metrics-endpoint)).

Tautulli has detailed metrics, because its per-stream detail (transcode decision, quality, player,
bandwidth) and library counts are what other exporters don't provide. The other modules have the job
metrics, whose `varken_job_points` counts the items in each queue and calendar. Detailed Ombi and UniFi
metrics are on the [roadmap](roadmap.md); the \*arr apps already have good Prometheus exporters. The
metric names are in [interfaces.md](interfaces.md#output-prometheus-metrics).

## Technology

Python 3.14 with [requests](https://requests.readthedocs.io/),
[geoip2](https://github.com/maxmind/GeoIP2-python),
[prometheus_client](https://github.com/prometheus/client_python),
[schedule](https://github.com/dbader/schedule) and [distro](https://github.com/python-distro/distro)
([dependencies.md](dependencies.md)).
Distributed as a container image for linux/amd64 and linux/arm64, or run from a checkout.

GitHub is the project's home. [`.gitlab-ci.yml`](../.gitlab-ci.yml) is the pipeline of the copy on the
maintainer's self-hosted GitLab: it mirrors GitHub and re-runs the CI checks that need no Docker daemon.
