# Interfaces

Everything Varken reads, writes and connects to. Today it listens on no ports and has no HTTP API; the
first one, a Prometheus `/metrics` endpoint, is [planned](#prometheus-metrics-planned).

## Interfaces Varken offers

### Configuration

`varken.ini` in the data folder, every key overridable by a `VRKN_<SECTION>_<KEY>` environment variable,
plus `DATA_FOLDER` and `DEBUG`. Every key, its variable, example value and meaning is in
[configuration.md](configuration.md).

### Command line

```
python3 Varken.py [-d DATA_FOLDER] [-ND]
```

| Option | What it does |
| --- | --- |
| `-d`, `--data-folder` | The data folder (holds `varken.ini`, the GeoLite2 database and `logs/`). Ignored when `DATA_FOLDER` is set in the environment. Default: `data/` next to `Varken.py`. |
| `-ND`, `--no_debug` | Log at INFO instead of DEBUG. Ignored when `DEBUG` is set in the environment. |
| `-D`, `--debug` | Deprecated and has no effect: debug logging is already the default. |
| `-h`, `--help` | Print the options and exit. |

Varken runs until it is stopped. It exits with status 1 when the data folder is missing or unreadable, a
URL in the config is invalid, `fallback_ip` is a private address, InfluxDB can't be reached at start-up,
every service is disabled, or the GeoLite2 database is missing and can't be downloaded.

The image copies the current `varken.example.ini` into `/config`, then runs `python /app/Varken.py` with
`DATA_FOLDER=/config` (and `DEBUG=True` unless you set it).

### Output: InfluxDB

Varken writes to the database `varken` on one InfluxDB 1.x server ([configuration](configuration.md#influxdb)),
creating it with the default retention policy `varken 30d-1h` (30 days) if it doesn't exist. Every point is
timestamped when the job ran (Tautulli history imports use the time a stream stopped). The measurements, by
module:

**`Tautulli`** (tag `type` tells the kinds apart; all have a `server` tag with the section id):

| `type` | Other tags | Fields |
| --- | --- | --- |
| `Session` (one per current stream) | `session_id`, `friendly_name`, `username`, `title`, `product`, `platform`, `product_version`, `device_type`, `quality`, `quality_profile`, `video_decision`, `transcode_decision`, `transcode_hw_decoding`, `transcode_hw_encoding`, `media_type`, `audio_codec`, `audio_profile`, `stream_audio_codec`, `progress_percent`, `player_state` (0 playing, 1 paused, 3 buffering; 100 for imported history), `relayed`, `secure`, `region_code`, `location` (city), `full_location`, `latitude`, `longitude` | `hash` |
| `current_stream_stats` | | `stream_count`, `total_bandwidth`, `wan_bandwidth`, `lan_bandwidth`, `transcode_streams`, `direct_play_streams`, `direct_streams` |
| `library_stats` (one per library) | `section_name`, `section_type` | `total`; for shows also `seasons`, `episodes`; for music also `artists`, `albums`, `tracks` |

The location tags come from the GeoLite2 lookup of the viewer's public address (or `fallback_ip`). The
address itself is never written. A viewer the database can't place gets the city `👽` and fixed
coordinates.

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

### Output: logs

Stdout and `logs/varken.log` in the data folder (5 MB, five rotated files), format
`date time : LEVEL : module : message`. What the debug log contains, and what is masked, is in
[configuration.md](configuration.md#logging).

### Prometheus metrics (Planned)

**Planned, not built.** An optional HTTP endpoint so Prometheus can scrape Varken, for Prometheus-based
stacks such as [Argus](https://github.com/HoneyBearTech/Argus). The proposed design:

- Off by default; turned on with `[prometheus]` `enabled`, listening on `bind`:`port` (default
  `0.0.0.0:9180`), path `/metrics`, in the Prometheus text format. InfluxDB stays available, and either or
  both outputs can be used.
- Gauges are updated by the same scheduled jobs that write to InfluxDB; a scrape does no work against the
  services.
- Metric names start with `varken_`, Tautulli first, for example `varken_tautulli_streams{server, state}`,
  `varken_tautulli_stream_bandwidth_kbps`, `varken_tautulli_streams_by_decision{decision}`,
  `varken_tautulli_library_items{library, type}`, plus `varken_up{service, server}` and
  `varken_last_success_timestamp_seconds{service, server, job}` for every module.
- Per-viewer labels (user, title, player, city) are personal and high-cardinality, so they are left out by
  default or put behind an opt-in. Viewer IP addresses are never labels.

The final names will be listed here when it ships.

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
| MaxMind | `GET https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City&suffix=tar.gz&license_key=…` when the database is missing or over 30 days old | license key as a query parameter ([a known weakness](security.md#known-weaknesses)) |
| ipify | `GET https://api.ipify.org` (10 s timeout) to learn the host's own public address, only when neither a viewer's address nor `fallback_ip` is in the GeoLite2 database; the answer is then reused until Varken restarts | none (a separate request; before 2.0.0 this went to `http://ip.42.pl` with the Tautulli API key attached, [now fixed](security.md#fixed-in-200)) |

The Sonarr and Radarr modules use the API paths without a version (`/api/...`) that upstream Varken was
written against. Recent Sonarr and Radarr releases serve their API under `/api/v3`; check that these
modules work with your version before relying on them.

Requests to the services, InfluxDB and MaxMind have no timeouts today ([security.md](security.md#known-weaknesses)); only the ipify lookup has one.

## Files

| Path (in the data folder) | Written by Varken | Contents |
| --- | --- | --- |
| `varken.ini` | when created from the example, or when missing keys are filled in | the configuration ([configuration.md](configuration.md)) |
| `varken.example.ini` | no (the image copies it in on start) | the template |
| `GeoLite2-City.mmdb` | downloaded and replaced about every 30 days, when Tautulli is enabled | MaxMind's city database; only the `.mmdb` file is extracted from the archive |
| `GeoLite2-City.tar.gz` | temporarily, during a download | |
| `logs/varken.log*` | always | the log |

Nothing else is written. The data that matters lives in InfluxDB.

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
path it writes to. Releases are published for linux/amd64 and linux/arm64, tagged with the version
(`2.0.0`), major.minor (`2.0`) and `latest`, signed and with an SBOM and provenance
([verifying-releases.md](verifying-releases.md)). It exposes no ports.
