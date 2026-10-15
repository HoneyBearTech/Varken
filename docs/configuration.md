# Configuration

Varken reads one file, `varken.ini`, in its data folder. Every key in it can be overridden by an
environment variable. This page lists every section and key that Varken reads (from
[`varken/iniparser.py`](../varken/iniparser.py)); the template is
[`data/varken.example.ini`](../data/varken.example.ini).

## Where the file lives

The data folder is, in order of precedence:

1. the `DATA_FOLDER` environment variable (the image sets it to `/config`);
2. `-d` / `--data-folder` on the command line;
3. `data/` next to `Varken.py` (a bare-Python checkout).

If `varken.ini` is missing, Varken copies `varken.example.ini` from the same folder to `varken.ini` (the
image puts that file into `/config` on every start). Keep `varken.ini` readable only by the user Varken runs
as (`chmod 600`): it holds API keys and passwords.

## How values are read

- **Environment variables win.** For each key, Varken uses `VRKN_<SECTION>_<KEY>` if it is set, otherwise
  the value in `varken.ini`. The section name is upper-cased and its `-` becomes `_`, so `[tautulli-1]`
  `apikey` is `VRKN_TAUTULLI_1_APIKEY`.
- **The key must still exist in `varken.ini`**, even when its environment variable is set: Varken reads
  the file's value first. In practice, keep a complete `varken.ini` (the example has every key) and use
  environment variables to override values in it. A server section that doesn't exist in the file, such as
  `[sonarr-3]`, can't be created from environment variables alone; add it to the file.
- **A missing key is filled in.** If a key or section Varken needs is missing from `varken.ini`, Varken
  copies it from `varken.example.ini` (along with every other missing or empty key and section in that
  file) and rewrites `varken.ini`, which drops any comments. This needs write access to the file; if the
  file is read-only, Varken stops. The "Example" column below is that value.
- **Booleans** are true only for `true` or `yes` (any case); anything else is false.
- **Server ids** (`<service>_server_ids`) are comma-separated whole numbers that name sections: `1,2` means
  `[sonarr-1]` and `[sonarr-2]`. `false` or `no` disables the service.
- **URLs are given without a scheme**: `tautulli.example.com:8181` or `example.com/tautulli`, never
  `https://...`. Whether Varken uses `http://` or `https://` is decided by the section's `ssl` key.
- **`verify_ssl` only matters with `ssl = true`.** With `ssl = false`, certificate checking is off because
  there is no TLS at all. Turn on both for any service you reach over a network you don't fully trust; see
  [security.md](security.md#transport).
- **`*_run_seconds`** is how often that job runs. Every job also runs once at start-up.
- A value that isn't a valid number (or a `fallback_ip` that isn't an IPv4 address) logs
  `Invalid configuration value` and skips that server. An invalid URL stops Varken.

Varken also reads two plain environment variables: `DATA_FOLDER` (above) and `DEBUG` (see
[Logging](#logging)).

## `[global]`

| Key | Environment variable | Example | Meaning |
| --- | --- | --- | --- |
| `sonarr_server_ids` | `VRKN_GLOBAL_SONARR_SERVER_IDS` | `1,2` | Sonarr servers to read, or `false`. |
| `radarr_server_ids` | `VRKN_GLOBAL_RADARR_SERVER_IDS` | `1,2` | Radarr servers to read, or `false`. |
| `lidarr_server_ids` | `VRKN_GLOBAL_LIDARR_SERVER_IDS` | `false` | Lidarr servers to read, or `false`. |
| `tautulli_server_ids` | `VRKN_GLOBAL_TAUTULLI_SERVER_IDS` | `1` | Tautulli servers to read, or `false`. |
| `ombi_server_ids` | `VRKN_GLOBAL_OMBI_SERVER_IDS` | `1` | Ombi servers to read, or `false`. |
| `sickchill_server_ids` | `VRKN_GLOBAL_SICKCHILL_SERVER_IDS` | `false` | SickChill servers to read, or `false`. |
| `unifi_server_ids` | `VRKN_GLOBAL_UNIFI_SERVER_IDS` | `false` | UniFi controllers to read, or `false`. |
| `maxmind_license_key` | `VRKN_GLOBAL_MAXMIND_LICENSE_KEY` | placeholder | Your MaxMind license key, used to download the GeoLite2-City database when Tautulli is enabled. Free with a [MaxMind account](https://www.maxmind.com/en/geolite2/signup). **Secret.** |

Varken stops if every service is disabled.

## `[influxdb]`

Varken writes to the database `varken` on this InfluxDB 1.x server, and creates it (with a default
retention policy `varken 30d-1h`: 30 days, 1-hour shards) if it doesn't exist. The database name isn't
configurable.

| Key | Environment variable | Example | Meaning |
| --- | --- | --- | --- |
| `url` | `VRKN_INFLUXDB_URL` | `influxdb.domain.tld` | Host name or IP of InfluxDB, without scheme or port. Varken refuses to start while it is still the example value. |
| `port` | `VRKN_INFLUXDB_PORT` | `8086` | InfluxDB HTTP port. |
| `ssl` | `VRKN_INFLUXDB_SSL` | `false` | Use HTTPS. |
| `verify_ssl` | `VRKN_INFLUXDB_VERIFY_SSL` | `false` | Check InfluxDB's TLS certificate. |
| `username` | `VRKN_INFLUXDB_USERNAME` | `root` | InfluxDB user. |
| `password` | `VRKN_INFLUXDB_PASSWORD` | `root` | That user's password. **Secret.** Change it from the example. |

## Keys every server section has

Each server is a section named `[<service>-<id>]`, for example `[tautulli-1]` or `[radarr-2]`.

| Key | Environment variable | Example | Meaning |
| --- | --- | --- | --- |
| `url` | `VRKN_<SERVICE>_<ID>_URL` | `tautulli.domain.tld:8181` | Host, optional port and optional path, without scheme. |
| `apikey` | `VRKN_<SERVICE>_<ID>_APIKEY` | placeholder | The service's API key. Not used by UniFi. **Secret.** |
| `ssl` | `VRKN_<SERVICE>_<ID>_SSL` | `false` | Use HTTPS. |
| `verify_ssl` | `VRKN_<SERVICE>_<ID>_VERIFY_SSL` | `false` | Check the service's TLS certificate (only with `ssl = true`). |

## `[tautulli-N]`

| Key | Environment variable | Example | Meaning |
| --- | --- | --- | --- |
| `fallback_ip` | `VRKN_TAUTULLI_<ID>_FALLBACK_IP` | a public IPv4 address | Located instead of a viewer whose address isn't in the GeoLite2 database (typically viewers on your LAN). Must be a public IPv4 address, normally your own; a private address stops Varken. |
| `get_activity` | `VRKN_TAUTULLI_<ID>_GET_ACTIVITY` | `true` | Record current streams and stream totals. |
| `get_activity_run_seconds` | `VRKN_TAUTULLI_<ID>_GET_ACTIVITY_RUN_SECONDS` | `30` | How often. |
| `get_stats` | `VRKN_TAUTULLI_<ID>_GET_STATS` | `true` | Record library item counts. |
| `get_stats_run_seconds` | `VRKN_TAUTULLI_<ID>_GET_STATS_RUN_SECONDS` | `3600` | How often. |

With Tautulli enabled, Varken needs the GeoLite2 database: it downloads it at start-up if it is missing
(and stops if it can't), and checks every 12 to 24 hours whether it is more than 30 days old.

## `[sonarr-N]`

| Key | Environment variable | Example | Meaning |
| --- | --- | --- | --- |
| `missing_days` | `VRKN_SONARR_<ID>_MISSING_DAYS` | `7` | Record monitored episodes without a file that aired in the last N days. `0` turns this off. |
| `missing_days_run_seconds` | `VRKN_SONARR_<ID>_MISSING_DAYS_RUN_SECONDS` | `300` | How often. |
| `future_days` | `VRKN_SONARR_<ID>_FUTURE_DAYS` | `1` | Record episodes airing in the next N days. `0` turns this off. |
| `future_days_run_seconds` | `VRKN_SONARR_<ID>_FUTURE_DAYS_RUN_SECONDS` | `300` | How often. |
| `queue` | `VRKN_SONARR_<ID>_QUEUE` | `true` | Record the download queue. |
| `queue_run_seconds` | `VRKN_SONARR_<ID>_QUEUE_RUN_SECONDS` | `300` | How often. |

## `[radarr-N]`

| Key | Environment variable | Example | Meaning |
| --- | --- | --- | --- |
| `queue` | `VRKN_RADARR_<ID>_QUEUE` | `true` | Record the download queue. |
| `queue_run_seconds` | `VRKN_RADARR_<ID>_QUEUE_RUN_SECONDS` | `300` | How often. |
| `get_missing` | `VRKN_RADARR_<ID>_GET_MISSING` | `true` | Record monitored movies without a file. |
| `get_missing_run_seconds` | `VRKN_RADARR_<ID>_GET_MISSING_RUN_SECONDS` | `300` | How often. |

## `[lidarr-N]`

| Key | Environment variable | Example | Meaning |
| --- | --- | --- | --- |
| `missing_days` | `VRKN_LIDARR_<ID>_MISSING_DAYS` | `30` | Record incomplete albums released in the last N days. `0` turns this off. |
| `missing_days_run_seconds` | `VRKN_LIDARR_<ID>_MISSING_DAYS_RUN_SECONDS` | `300` | How often. |
| `future_days` | `VRKN_LIDARR_<ID>_FUTURE_DAYS` | `30` | Record albums releasing in the next N days. `0` turns this off. |
| `future_days_run_seconds` | `VRKN_LIDARR_<ID>_FUTURE_DAYS_RUN_SECONDS` | `300` | How often. |
| `queue` | `VRKN_LIDARR_<ID>_QUEUE` | `true` | Record the download queue. |
| `queue_run_seconds` | `VRKN_LIDARR_<ID>_QUEUE_RUN_SECONDS` | `300` | How often. |

## `[ombi-N]`

| Key | Environment variable | Example | Meaning |
| --- | --- | --- | --- |
| `get_request_type_counts` | `VRKN_OMBI_<ID>_GET_REQUEST_TYPE_COUNTS` | `true` | Record the number of pending, approved and available requests. |
| `request_type_run_seconds` | `VRKN_OMBI_<ID>_REQUEST_TYPE_RUN_SECONDS` | `300` | How often. |
| `get_request_total_counts` | `VRKN_OMBI_<ID>_GET_REQUEST_TOTAL_COUNTS` | `true` | Record request totals and one point per movie and TV request. |
| `request_total_run_seconds` | `VRKN_OMBI_<ID>_REQUEST_TOTAL_RUN_SECONDS` | `300` | How often. |
| `get_issue_status_counts` | `VRKN_OMBI_<ID>_GET_ISSUE_STATUS_COUNTS` | `true` | Record the number of pending, in-progress and resolved issues. |
| `issue_status_run_seconds` | `VRKN_OMBI_<ID>_ISSUE_STATUS_RUN_SECONDS` | `300` | How often. |

## `[sickchill-N]`

| Key | Environment variable | Example | Meaning |
| --- | --- | --- | --- |
| `get_missing` | `VRKN_SICKCHILL_<ID>_GET_MISSING` | `true` | Record missed, today's, soon and later episodes. |
| `get_missing_run_seconds` | `VRKN_SICKCHILL_<ID>_GET_MISSING_RUN_SECONDS` | `300` | How often. |

## `[unifi-N]`

UniFi has no `apikey`; it logs in with a username and password instead.

| Key | Environment variable | Example | Meaning |
| --- | --- | --- | --- |
| `username` | `VRKN_UNIFI_<ID>_USERNAME` | `ubnt` | Controller user. Use a dedicated read-only account. |
| `password` | `VRKN_UNIFI_<ID>_PASSWORD` | `ubnt` | That user's password. **Secret.** |
| `site` | `VRKN_UNIFI_<ID>_SITE` | `default` | Site name or description (case-insensitive). |
| `usg_name` | `VRKN_UNIFI_<ID>_USG_NAME` | `MyRouter` | Device name of the gateway to record, as shown in the controller. |
| `get_usg_stats_run_seconds` | `VRKN_UNIFI_<ID>_GET_USG_STATS_RUN_SECONDS` | `300` | How often. |

## Logging

Varken logs to stdout and to `logs/varken.log` in the data folder (rotated at 5 MB, five old files kept).

- **Debug logging is on by default.** Set `DEBUG=false` in the environment, or pass `-ND` / `--no_debug`
  (which only applies when `DEBUG` isn't set), to log at INFO. The debug log includes every point written to
  InfluxDB (usernames, titles, locations) and request URLs; see
  [security.md](security.md#known-weaknesses). Turning it off by default is on the
  [roadmap](roadmap.md).
- Secrets are masked in log lines as `********` followed by their last five characters: the values of the
  `apikey`, `username`, `password`, `url` and `maxmind_license_key` keys in `varken.ini`, and of every
  `VRKN_*` variable whose name ends in `_APIKEY`, `_USERNAME`, `_PASSWORD`, `_URL` or
  `_MAXMIND_LICENSE_KEY`. Before 2.0.0, values from environment variables and the MaxMind key were not
  masked ([security.md](security.md#fixed-in-200)).

## Example

A minimal `varken.ini` that reads one Tautulli server over HTTPS. Sections of disabled services aren't
read, so they can be left out (or left as they are in the example file).

```ini
[global]
sonarr_server_ids = false
radarr_server_ids = false
lidarr_server_ids = false
tautulli_server_ids = 1
ombi_server_ids = false
sickchill_server_ids = false
unifi_server_ids = false
maxmind_license_key = <your MaxMind license key>

[influxdb]
url = influxdb
port = 8086
ssl = false
verify_ssl = false
username = varken
password = <a strong password>

[tautulli-1]
url = tautulli.example.com
fallback_ip = <your public IPv4 address>
apikey = <your Tautulli API key>
ssl = true
verify_ssl = true
get_activity = true
get_activity_run_seconds = 30
get_stats = true
get_stats_run_seconds = 3600
```

## Planned settings

These are designed but **not built yet** ([roadmap](roadmap.md)); today Varken ignores them.

| Key | Environment variable | Default | Meaning |
| --- | --- | --- | --- |
| `[prometheus]` `enabled` | `VRKN_PROMETHEUS_ENABLED` | `false` | **Planned.** Serve Prometheus metrics ([interfaces.md](interfaces.md#prometheus-metrics-planned)). |
| `[prometheus]` `bind` | `VRKN_PROMETHEUS_BIND` | `0.0.0.0` | **Planned.** Address to listen on. |
| `[prometheus]` `port` | `VRKN_PROMETHEUS_PORT` | `9180` | **Planned.** Port to listen on. |
| `[influxdb]` `enabled` | `VRKN_INFLUXDB_ENABLED` | `true` | **Planned.** Turn the InfluxDB output off, for Prometheus-only setups. |
| any key | `VRKN_<SECTION>_<KEY>_FILE` | unset | **Planned.** Read the value from a file, for Docker and compose secrets. |
