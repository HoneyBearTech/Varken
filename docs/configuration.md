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

Varken also reads three plain environment variables: `DATA_FOLDER` (above), and `DEBUG` and `LOG_TO_FILE`
(see [Logging](#logging)).

## Values from files (`_FILE`)

Any `VRKN_<SECTION>_<KEY>` can instead be read from a file, for Docker and compose secrets: set
`VRKN_<SECTION>_<KEY>_FILE` to the file's path, and Varken uses the file's contents, with surrounding
whitespace and the trailing newline stripped, as the value of `VRKN_<SECTION>_<KEY>`. For example, with a
compose secret named `tautulli_api_key`:

```yaml
services:
  varken:
    environment:
      VRKN_TAUTULLI_1_APIKEY_FILE: /run/secrets/tautulli_api_key
    secrets:
      - tautulli_api_key
secrets:
  tautulli_api_key:
    file: ./secrets/tautulli_api_key.txt
```

- Set one or the other: if both `VRKN_<SECTION>_<KEY>` and `VRKN_<SECTION>_<KEY>_FILE` are set, Varken stops.
  Remove the plain variable from `.env` when you move it to a file.
- If the file can't be read, Varken stops and logs the variable and the path. It must be readable by the
  user Varken runs as (uid 1000 in the image).
- The rules above still apply: the key must exist in `varken.ini`, and values read this way are masked in
  the logs like any other ([Logging](#logging)).
- The file is read once, at start-up; restart Varken after changing it. Varken copies the value into its
  own process environment, so it isn't in the container's configuration (`docker inspect`) or in `.env`.

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
| `maxmind_license_key` | `VRKN_GLOBAL_MAXMIND_LICENSE_KEY` | placeholder | Optional. Your MaxMind license key, used to download the GeoLite2-City database that places Tautulli viewers on a map. Free with a [MaxMind account](https://www.maxmind.com/en/geolite2/signup). Empty, or still the example's `xxxx…` placeholder, turns GeoIP off ([below](#tautulli-n)). **Secret.** |

Varken stops if every service is disabled.

## `[prometheus]`

Varken's output, always on: an HTTP endpoint at `/metrics` that Prometheus scrapes. The metrics are listed in
[interfaces.md](interfaces.md#output-prometheus-metrics).

| Key | Environment variable | Example | Meaning |
| --- | --- | --- | --- |
| `bind` | `VRKN_PROMETHEUS_BIND` | `0.0.0.0` | The address to listen on. Must be an IP address (IPv4 or IPv6), not a host name, or Varken stops. `0.0.0.0` is every IPv4 interface (in a container, the container's own); `127.0.0.1` keeps it to the same host. |
| `port` | `VRKN_PROMETHEUS_PORT` | `9180` | The port to listen on, from 1 to 65535, or Varken stops. ScyllaDB also uses 9180 by default; pick another port if something on the host already has it. |
| `stream_details` | `VRKN_PROMETHEUS_STREAM_DETAILS` | `false` | Add the per-viewer Tautulli metrics: who is watching what, on which player, and from which city. Personal data, so off by default; viewer IP addresses are never exported either way. |

The endpoint has no authentication and no TLS. Keep it on a private network (a Docker network shared with
Prometheus, for example) or bind it to `127.0.0.1`; see [security.md](security.md#the-metrics-endpoint).

**From upstream Varken.** A `varken.ini` from upstream 1.7.x has no `[prometheus]` section: on its first
start Varken adds it with the defaults above, as for any [missing key](#how-values-are-read) (which needs
write access to the file). Its `[influxdb]` section, and any `VRKN_INFLUXDB_*` variable, is ignored: Varken no
longer writes to InfluxDB. Delete the section or leave it ([upgrading.md](upgrading.md)).

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
| `fallback_ip` | `VRKN_TAUTULLI_<ID>_FALLBACK_IP` | a public IPv4 address | Located instead of a viewer whose address isn't in the GeoLite2 database (typically viewers on your LAN). Must be a public IPv4 address, normally your own; a private address stops Varken. It is checked even with GeoIP off, though not used then. |
| `get_activity` | `VRKN_TAUTULLI_<ID>_GET_ACTIVITY` | `true` | Record current streams and stream totals. |
| `get_activity_run_seconds` | `VRKN_TAUTULLI_<ID>_GET_ACTIVITY_RUN_SECONDS` | `30` | How often. |
| `get_stats` | `VRKN_TAUTULLI_<ID>_GET_STATS` | `true` | Record library item counts. |
| `get_stats_run_seconds` | `VRKN_TAUTULLI_<ID>_GET_STATS_RUN_SECONDS` | `3600` | How often. |

**GeoIP is optional.** With Tautulli enabled and a `maxmind_license_key` set, Varken uses the GeoLite2
database to place viewers: it downloads it at start-up if it is missing (and stops if it can't), and checks
every 12 to 24 hours whether it is more than 30 days old. Without a key (empty, or the example's placeholder)
it logs `No MaxMind license key: GeoIP is off and Tautulli streams have no location.` and every stream gets the
unknown location ([interfaces.md](interfaces.md#output-prometheus-metrics)); Varken then never contacts MaxMind
or `api.ipify.org`.

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

- **`LOG_TO_FILE=false`** (or `no`, any case) in the environment logs to stdout only, and Varken creates no
  `logs/` folder in the data folder. Useful in a container whose logs are collected anyway (`docker logs`,
  journald). It is `true` by default.

- **Debug logging is on by default.** Set `DEBUG=false` in the environment, or pass `-ND` / `--no_debug`
  (which only applies when `DEBUG` isn't set), to log at INFO. The debug log includes the URL of every request
  Varken makes (secrets masked as below); see [security.md](security.md#known-weaknesses). Turning it off by
  default is on the [roadmap](roadmap.md).
- Secrets are masked in log lines as `********` followed by their last five characters: the values of the
  `apikey`, `username`, `password`, `url` and `maxmind_license_key` keys in `varken.ini`, and of every
  `VRKN_*` variable whose name ends in `_APIKEY`, `_USERNAME`, `_PASSWORD`, `_URL` or
  `_MAXMIND_LICENSE_KEY`. Before 2.0.0, values from environment variables and the MaxMind key were not
  masked ([security.md](security.md#fixed-in-200)).

## Example

A minimal `varken.ini` that reads one Tautulli server over HTTPS and serves its metrics on port 9180.
Sections of disabled services aren't read, so they can be left out (or left as they are in the example file);
`[global]` and `[prometheus]` are always read.

```ini
[global]
sonarr_server_ids = false
radarr_server_ids = false
lidarr_server_ids = false
tautulli_server_ids = 1
ombi_server_ids = false
sickchill_server_ids = false
unifi_server_ids = false
maxmind_license_key = <your MaxMind license key, or empty for no GeoIP>

[prometheus]
bind = 0.0.0.0
port = 9180
stream_details = false

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
