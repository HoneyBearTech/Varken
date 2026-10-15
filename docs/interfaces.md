# Interfaces

Everything Varken reads, writes, connects to and listens on. Its only listening socket is the optional
Prometheus [`/metrics` endpoint](#output-prometheus-metrics), off by default; it has no other HTTP API.

## Interfaces Varken offers

### Configuration

`varken.ini` in the data folder, every key overridable by a `VRKN_<SECTION>_<KEY>` environment variable
(or by a file named in `VRKN_<SECTION>_<KEY>_FILE`), plus `DATA_FOLDER`, `DEBUG` and `LOG_TO_FILE`. Every key,
its variable, example value and meaning is in [configuration.md](configuration.md).

### Command line

```
python3 Varken.py [-d DATA_FOLDER] [-ND]
```

| Option | What it does |
| --- | --- |
| `-d`, `--data-folder` | The data folder (holds `varken.ini`, the GeoLite2 database and, unless `LOG_TO_FILE=false`, `logs/`). Ignored when `DATA_FOLDER` is set in the environment. Default: `data/` next to `Varken.py`. |
| `-ND`, `--no_debug` | Log at INFO instead of DEBUG. Ignored when `DEBUG` is set in the environment. |
| `-D`, `--debug` | Deprecated and has no effect: debug logging is already the default. |
| `-h`, `--help` | Print the options and exit. |

Varken runs until it is stopped. It exits with status 1 when the data folder is missing or unreadable, a
`VRKN_*_FILE` can't be read or is set together with the variable it replaces, a URL in the config is
invalid, `fallback_ip` is a private address, a `[prometheus]` setting is invalid (`bind` isn't an IP address,
`port` isn't a number from 1 to 65535), both outputs are disabled, InfluxDB is enabled and can't be reached
at start-up, the metrics port can't be opened (for example because it is in use; Varken logs which
address and port), every service is disabled, or a MaxMind license key is set and the GeoLite2 database is missing
and can't be downloaded.

The image copies the current `varken.example.ini` into `/config`, then runs `python /app/Varken.py` with
`DATA_FOLDER=/config` (and `DEBUG=True` unless you set it).

### Output: InfluxDB

With `[influxdb]` `enabled = true` (the default), Varken writes to the database `varken` on one InfluxDB 1.x
server ([configuration](configuration.md#influxdb)), creating it with the default retention policy
`varken 30d-1h` (30 days) if it doesn't exist. Every point is timestamped when the job ran (Tautulli history
imports use the time a stream stopped). The measurements, by module:

**`Tautulli`** (tag `type` tells the kinds apart; all have a `server` tag with the section id):

| `type` | Other tags | Fields |
| --- | --- | --- |
| `Session` (one per current stream) | `session_id`, `friendly_name`, `username`, `title`, `product`, `platform`, `product_version`, `device_type`, `quality`, `quality_profile`, `video_decision`, `transcode_decision`, `transcode_hw_decoding`, `transcode_hw_encoding`, `media_type`, `audio_codec`, `audio_profile`, `stream_audio_codec`, `progress_percent`, `player_state` (0 playing, 1 paused, 3 buffering; 100 for imported history), `relayed`, `secure`, `region_code`, `location` (city), `full_location`, `latitude`, `longitude` | `hash` |
| `current_stream_stats` | | `stream_count`, `total_bandwidth`, `wan_bandwidth`, `lan_bandwidth`, `transcode_streams`, `direct_play_streams`, `direct_streams` |
| `library_stats` (one per library) | `section_name`, `section_type` | `total`; for shows also `seasons`, `episodes`; for music also `artists`, `albums`, `tracks` |

The location tags come from the GeoLite2 lookup of the viewer's public address (or `fallback_ip`). The
address itself is never written. `full_location` is `<region> - <city>`, leaving out whichever part is
unknown. A viewer the database can't place gets the city `👽`, fixed coordinates, no `region_code` and an
empty `full_location`; with GeoIP off (no MaxMind license key, [configuration](configuration.md#tautulli-n))
every viewer gets those values.

**`Sonarr`** (field `hash`):

| `type` | Tags |
| --- | --- |
| `Missing`, `Future` | `server`, `sonarrId` (episode id), `name` (series), `epname`, `sxe` (`S01E02`), `airsUTC`, `downloaded` (0 or 1) |
| `Queue` | `server`, `sonarrId` (queue id), `name`, `epname`, `sxe`, `protocol`, `protocol_id` (1 Usenet, 0 torrent), `quality` |

**`Radarr`** (field `hash`):

| Kind | Tags |
| --- | --- |
| Missing movies (no `type` tag) | `Missing` (`True`), `Missing_Available` (0 available, 1 not yet), `tmdbId`, `server`, `name` (`Title (Year)`), `titleSlug` |
| `type` = `Queue` | `tmdbId` (holds the queue id), `server`, `name`, `quality`, `protocol`, `protocol_id`, `titleSlug` |

**`Lidarr`** (field `hash`):

| `type` | Tags |
| --- | --- |
| `Missing`, `Future` (albums not 100 % complete) | `server`, `sonarrId` (album id), `albumName`, `artistName`, `percentComplete`, `completeCount` (`tracks/total`), `releaseDate` |
| `Queue` | `server`, `id`, `title`, `quality`, `protocol`, `protocol_id`, `indexer` |

**`Ombi`**:

| `type` | Tags | Fields |
| --- | --- | --- |
| `Request_Total` | `server` | `total`, `movies`, `tv_shows` |
| `Requests` (one per request) | `server`, `request_type` (1 movie, 0 TV), `status` (0 denied, 1 approved, 2 available, 3 pending), `title`, `requested_user`, `requested_date` | `hash` |
| `Request_Counts` | (no `server` tag) | `pending`, `approved`, `available` |
| `Issues_Counts` | (no `server` tag) | `pending`, `in_progress`, `resolved` |

**`SickChill`** (field `hash`): tags `type` (1 later, 2 soon, 3 today, 4 missed), `indexerid`, `server`,
`name`, `epname`, `sxe`, `airdate`.

**`UniFi`**: tags `model`, `name` (the gateway); fields `bytes_current`, `rx_bytes_total`,
`rx_bytes_current`, `tx_bytes_total`, `tx_bytes_current`, `cpu_loadavg_1`, `cpu_loadavg_5`,
`cpu_loadavg_15`, `cpu_util`, `mem_util`.

The `hash` field is a SHA-256 (an MD5 before 2.0.0) of identifying values, used by dashboards to count distinct items; it is not a
security control. These names are kept as upstream Varken wrote them so existing Grafana dashboards keep
working; a change to them is a breaking change ([SUPPORT.md](../SUPPORT.md)).

### Output: Prometheus metrics

Off by default. With `[prometheus]` `enabled = true` ([configuration](configuration.md#prometheus)), Varken
serves its metrics in the Prometheus text format at `http://<bind>:<port>/metrics` (default `0.0.0.0:9180`),
using the HTTP server built into [prometheus_client](https://github.com/prometheus/client_python), which
gives the same answer on any other path. It is plain HTTP with **no authentication and no TLS**: keep it on a
private network, or bind it to `127.0.0.1` ([security.md](security.md#the-metrics-endpoint)). The log shows
`Serving Prometheus metrics on <bind>:<port>/metrics` when it starts.

**Where the values come from.** Every scheduled job of a module runs through the metrics collector
([`varken/metrics.py`](../varken/metrics.py)), which keeps the points the job hands to the outputs, the same
points InfluxDB gets. When the job ends, they replace that job's previous snapshot. A scrape only reads the
snapshots: it never calls a service, so values are as fresh as each job's `*_run_seconds`. A run counts as
successful when none of its requests failed, it logged no error and it didn't crash. A failed run drops that
job's snapshot, so its data metrics disappear until the next successful run rather than going stale. Every
job runs once at start-up, and its series appear when that run ends; nothing is kept across a restart.

**Every job:**

| Metric | Labels | Value |
| --- | --- | --- |
| `varken_build_info` | `version`, `branch` | Always `1`. |
| `varken_job_up` | `service`, `server`, `job` | `1` if the job's last run had no failed request and logged no error, else `0`. |
| `varken_job_last_success_timestamp_seconds` | `service`, `server`, `job` | When the job last ran successfully, in Unix time. Absent until its first success. |
| `varken_job_points` | `service`, `server`, `job` | Points the last successful run wrote; for the `queue`, `missing` and `future` jobs, the number of items. Only present while the job is up. |

`service` is the module and `server` its section id (`2` for `[sonarr-2]`). `job` is the job's function
without its `get_` prefix, or, for the Sonarr and Lidarr calendar jobs, the calendar query:

| `service` | `job` |
| --- | --- |
| `tautulli` | `activity`, `stats` |
| `sonarr` | `queue`, `missing`, `future` |
| `radarr` | `queue`, `missing` |
| `lidarr` | `queue`, `missing`, `future` |
| `ombi` | `request_counts`, `all_requests`, `issue_counts` |
| `sickchill` | `missing` |
| `unifi` | `usg_stats` |

Only the jobs a server has turned on appear. The GeoLite2 update job isn't a module job and has no metrics.

**Tautulli** (from the `activity` and `stats` jobs; `server` is the section id):

| Metric | Labels | Value |
| --- | --- | --- |
| `varken_tautulli_streams` | `server` | Current streams. |
| `varken_tautulli_streams_by_decision` | `server`, `decision` (`transcode`, `direct_play`, `direct_stream`) | Current streams by transcode decision. |
| `varken_tautulli_bandwidth_bytes_per_second` | `server`, `network` (`total`, `lan`, `wan`) | Bandwidth of the current streams: Tautulli's kbit/s × 125. |
| `varken_tautulli_sessions` | `server`, `state` (`playing`, `paused`, `buffering`, `other`), `media_type`, `transcode_decision`, `video_decision`, `quality`, `platform` | Number of current sessions with those labels. No viewer identity. |
| `varken_tautulli_library_items` | `server`, `library`, `type`, `item` | Items in each library. `item` is `total` for every library (movies, shows or artists); show libraries add `seasons` and `episodes`, music libraries `artists`, `albums` and `tracks`. |

`media_type`, `transcode_decision` and `video_decision` are lower-cased with spaces as underscores (`episode`,
`direct_play`; `video_decision` is `music` for audio). `quality`, `platform`, `library` and `type` are as in
the InfluxDB `Session` and `library_stats` points above.

**Per-viewer metrics**, only with `[prometheus]` `stream_details = true` (off by default):

| Metric | Labels | Value |
| --- | --- | --- |
| `varken_tautulli_session_info` | `server`, `session_id`, `user`, `title`, `product`, `platform`, `quality`, `transcode_decision`, `location`, `region_code` | Always `1`, one series per current session. |
| `varken_tautulli_session_progress_ratio` | `server`, `session_id` | How far into the item the session is, from 0 to 1. |

These say who is watching what, on which player, and from which city (`location`, the GeoLite2 city, or `👽`
when it can't be placed; `region_code`, the region's ISO code). That is personal data, and every session adds
series, which is why they are off by default. Viewer IP addresses are never exported, with or without
`stream_details`.

**Other modules.** Sonarr, Radarr, Lidarr, SickChill, Ombi and UniFi have only the job metrics so far; for the
\*arr apps and SickChill, `varken_job_points` already counts the items in each queue and calendar. Detailed
Ombi and UniFi metrics are on the [roadmap](roadmap.md).

CI checks a sample scrape with every metric in it (`python -m tests.sample_metrics`) using Prometheus'
`promtool check metrics`.

### Output: logs

Stdout and, unless `LOG_TO_FILE=false`, `logs/varken.log` in the data folder (5 MB, five rotated files),
format `date time : LEVEL : module : message`. What the debug log contains, and what is masked, is in
[configuration.md](configuration.md#logging).

## Interfaces Varken uses

All requests are made with [requests](https://requests.readthedocs.io/) from the scheduled jobs, over
`https://` when the section's `ssl` is true and `http://` otherwise, with certificate checks only when
`verify_ssl` is also true. Apart from the UniFi login, every request is a `GET`: Varken changes nothing in
the services it reads.

| Service | Requests (relative to the configured `url`) | Credential |
| --- | --- | --- |
| Tautulli | `GET /api/v2?cmd=get_activity`, `GET /api/v2?cmd=get_libraries` (history import: `get_history`, `get_stream_data`) | `apikey` as a query parameter (Tautulli's API requires it) |
| Sonarr | `GET /api/calendar/?start=&end=`, `GET /api/queue` | `X-Api-Key` header |
| Radarr | `GET /api/movie`, `GET /api/queue` | `X-Api-Key` header |
| Lidarr | `GET /api/v1/calendar?start=&end=`, `GET /api/v1/queue` | `X-Api-Key` header |
| Ombi | `GET /api/v1/Request/count`, `GET /api/v1/Request/movie`, `GET /api/v1/Request/tv`, `GET /api/v1/Issues/count` | `Apikey` header |
| SickChill | `GET /api/<apikey>/?cmd=future&type=missed\|today\|soon\|later\|snatched` | the key is part of the path (SickChill's API requires it) |
| UniFi controller | `POST /api/login` (username and password as JSON; keeps the `unifises` cookie), `GET /api/self/sites`, `GET /api/s/<site>/stat/device` | session cookie |
| InfluxDB | `GET /ping`, `SHOW DATABASES`, `CREATE DATABASE`, `CREATE RETENTION POLICY` (first start only), writes | username and password |
| MaxMind | `GET https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City&suffix=tar.gz&license_key=…` when the database is missing or over 30 days old; only with a license key set (GeoIP on) | license key as a query parameter ([a known weakness](security.md#known-weaknesses)) |
| ipify | `GET https://api.ipify.org` (10 s timeout) to learn the host's own public address, only with GeoIP on and when neither a viewer's address nor `fallback_ip` is in the GeoLite2 database; the answer is then reused until Varken restarts | none (a separate request; before 2.0.0 this went to `http://ip.42.pl` with the Tautulli API key attached, [now fixed](security.md#fixed-in-200)) |

The Sonarr and Radarr modules use the API paths without a version (`/api/...`) that upstream Varken was
written against. Recent Sonarr and Radarr releases serve their API under `/api/v3`; check that these
modules work with your version before relying on them.

Requests to the services, InfluxDB and MaxMind have no timeouts today ([security.md](security.md#known-weaknesses)); only the ipify lookup has one.

## Files

| Path (in the data folder) | Written by Varken | Contents |
| --- | --- | --- |
| `varken.ini` | when created from the example, or when missing keys are filled in | the configuration ([configuration.md](configuration.md)) |
| `varken.example.ini` | no (the image copies it in on start) | the template |
| `GeoLite2-City.mmdb` | downloaded and replaced about every 30 days, when Tautulli is enabled with a MaxMind license key | MaxMind's city database; only the `.mmdb` file is extracted from the archive |
| `GeoLite2-City.tar.gz` | temporarily, during a download | |
| `logs/varken.log*` | unless `LOG_TO_FILE=false` | the log |

Nothing else is written. The data that matters lives in InfluxDB, or in the Prometheus server that scrapes
Varken.

## Utilities

Two scripts in [`utilities/`](../utilities/) (copied into the image at `/app/data/utilities/`) are run by
hand, not by Varken:

- **`grafana_build.py`** creates an InfluxDB data source and imports the upstream Varken dashboard
  (grafana.com dashboard 9585) through the Grafana HTTP API. Edit the settings at the top (Grafana URL and
  admin credentials, library names, links), then run it once. It talks to Grafana only; Grafana fetches
  the dashboard from grafana.com.
- **`historical_tautulli_import.py`** (`-d DATA_FOLDER`, `-D DAYS`, default 30) reads Tautulli's history
  and writes it as `Session` points. In this release it fails at start-up because it doesn't pass the
  MaxMind license key to the GeoIP code; it's listed on the [roadmap](roadmap.md) to be fixed.

## Image

`ghcr.io/honeybeartech/varken`, built from the [`Dockerfile`](../Dockerfile): `python:3.14-slim` pinned by
version and digest, the hash-pinned packages from [`requirements.txt`](../requirements.txt), and Varken in
`/app`. It runs as the unprivileged uid/gid 1000:1000 with `DATA_FOLDER=/config`; `/config` is the only
path it writes to, and belongs to 1000:1000 in the image, so a new named volume there starts out writable.
Releases are published for linux/amd64 and linux/arm64, tagged with the version
(`2.0.0`), major.minor (`2.0`) and `latest`, signed and with an SBOM and provenance
([verifying-releases.md](verifying-releases.md)). It declares `EXPOSE 9180` for the Prometheus output, which
listens only when `[prometheus]` `enabled = true`.
