# Interfaces

Everything Varken reads, writes, connects to and listens on. Its output, and its only listening socket, is
the Prometheus [`/metrics` endpoint](#output-prometheus-metrics); it has no other HTTP API.

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
`port` isn't a number from 1 to 65535), the metrics port can't be opened (for example because it is in
use; Varken logs which address and port), every service is disabled, or a MaxMind license key is set and the
GeoLite2 database is missing and can't be downloaded.

The image copies the current `varken.example.ini` into `/config`, then runs `python /app/Varken.py` with
`DATA_FOLDER=/config` (and `DEBUG=True` unless you set it).

### Output: Prometheus metrics

Always on. Varken serves its metrics ([configuration](configuration.md#prometheus)) in the Prometheus text
format at `http://<bind>:<port>/metrics` (default `0.0.0.0:9180`), using the HTTP server built into
[prometheus_client](https://github.com/prometheus/client_python), which gives the same answer on any other
path. It is plain HTTP with **no authentication and no TLS**: keep it on a
private network, or bind it to `127.0.0.1` ([security.md](security.md#the-metrics-endpoint)). The log shows
`Serving Prometheus metrics on <bind>:<port>/metrics` when it starts.

**Where the values come from.** Every scheduled job of a module runs through the metrics collector
([`varken/metrics.py`](../varken/metrics.py)), which keeps the points the job hands to `Metrics.write_points`
(internal data, not an interface). When the job ends, they replace that job's previous snapshot. A scrape only
reads the snapshots: it never calls a service, so values are as fresh as each job's `*_run_seconds`. A run counts as
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
`direct_play`; `video_decision` is `music` for audio). `quality` is the stream's video resolution as
Tautulli reports it (`SD` and `4K` upper-cased), or the container (`MP3`) for audio; `platform` is the
player's platform, as Tautulli reports it. `library` is the library's name and `type` its Tautulli section
type (`movie`, `show`, `artist`).

**Per-viewer metrics**, only with `[prometheus]` `stream_details = true` (off by default):

| Metric | Labels | Value |
| --- | --- | --- |
| `varken_tautulli_session_info` | `server`, `session_id`, `user`, `friendly_name`, `title`, `product`, `product_version`, `platform`, `quality`, `quality_profile`, `transcode_decision`, `video_decision`, `state`, `location`, `full_location`, `region_code`, `latitude`, `longitude` | Always `1`, one series per current session. |
| `varken_tautulli_session_progress_ratio` | `server`, `session_id` | How far into the item the session is, from 0 to 1. |

These say who is watching what, on which player, and from which city: `location` is the GeoLite2 city of the
viewer's public address, or of `fallback_ip` or the host's own address when that one isn't in the database;
`full_location` adds the region and country, `region_code` is the region's ISO code, and `latitude` and
`longitude` are the city's coordinates as decimal strings, for a map panel. All of them are empty when the
viewer can't be placed, and always with GeoIP off (no MaxMind license key,
[configuration](configuration.md#tautulli-n)). `user` is the Plex username and `friendly_name` the name
Tautulli shows; `state` is labelled as in `varken_tautulli_sessions`. That is personal data, and every
session adds series, which is why they are off by default. Viewer IP addresses are never exported, with or
without `stream_details`.

**Sonarr, Radarr and SickChill** (one series per item, value always `1`; count them in PromQL, for example
`count(varken_radarr_queue_item_info) or vector(0)`). A series exists while the item is in the last
successful run of its job, so a job that is down shows no items:

| Metric | Labels | Item |
| --- | --- | --- |
| `varken_sonarr_queue_item_info` | `server`, `series`, `episode`, `title`, `protocol`, `quality` | An episode in Sonarr's download queue (`queue` job). `episode` is `S01E02`, `title` the episode's title, `protocol` `usenet` or `torrent`. Downloads Sonarr hasn't matched to an episode are left out. |
| `varken_sonarr_episode_info` | `server`, `kind`, `series`, `episode`, `title`, `airs`, `downloaded` | `kind="missing"` (`missing` job): a monitored episode without a file that aired in the last `missing_days`. `kind="future"` (`future` job): an episode airing from today through `future_days`. `airs` is the air time in UTC (ISO 8601), `downloaded` `true` or `false`. |
| `varken_radarr_queue_item_info` | `server`, `movie`, `quality`, `protocol` | A movie in Radarr's download queue (`queue` job). `movie` is `Title (Year)`. |
| `varken_radarr_missing_info` | `server`, `movie`, `available` | A monitored movie without a file (`missing` job). `available` is `true` once Radarr considers it released, else `false`. |
| `varken_sickchill_episode_info` | `server`, `show`, `episode`, `title`, `airdate`, `status` | An episode on SickChill's coming-episodes list (`missing` job), `status` `missed`, `today`, `soon` or `later`. |

**Ombi**:

| Metric | Labels | Value |
| --- | --- | --- |
| `varken_ombi_requests` | `server`, `status` (`pending`, `approved`, `available`) | Requests by status (`request_counts` job). |
| `varken_ombi_issues` | `server`, `status` (`pending`, `in_progress`, `resolved`) | Issues by status (`issue_counts` job). |
| `varken_ombi_request_info` | `server`, `type` (`movie`, `tv`), `title`, `status` (`pending`, `approved`, `available`, `denied`), `requested`, `user` | Always `1`, one series per request (`all_requests` job). `requested` is the request date as Ombi gives it. `user`, the requester, is filled in only with `stream_details = true` and empty otherwise. |

**Lidarr and UniFi** have only the job metrics; for Lidarr, `varken_job_points` counts the albums in the queue
and calendar. Detailed UniFi metrics are on the [roadmap](roadmap.md).

CI checks a sample scrape with every metric in it (`python -m tests.sample_metrics`) using Prometheus'
`promtool check metrics`. Metric names and labels are kept stable so dashboards and alerts keep working;
renaming or removing one is a breaking change ([SUPPORT.md](../SUPPORT.md)).

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
| Tautulli | `GET /api/v2?cmd=get_activity`, `GET /api/v2?cmd=get_libraries` | `apikey` as a query parameter (Tautulli's API requires it) |
| Sonarr | `GET /api/v3/calendar?start=&end=&includeSeries=true`, `GET /api/v3/queue?includeSeries=true&includeEpisode=true` | `X-Api-Key` header |
| Radarr | `GET /api/v3/movie`, `GET /api/v3/queue?includeMovie=true` | `X-Api-Key` header |
| Lidarr | `GET /api/v1/calendar?start=&end=&includeArtist=true`, `GET /api/v1/queue` | `X-Api-Key` header |
| Ombi | `GET /api/v1/Request/count`, `GET /api/v1/Request/movie`, `GET /api/v1/Request/tv`, `GET /api/v1/Issues/count` | `Apikey` header |
| SickChill | `GET /api/<apikey>/?cmd=future&type=missed\|today\|soon\|later\|snatched` | the key is part of the path (SickChill's API requires it) |
| UniFi controller | `POST /api/login` (username and password as JSON; keeps the `unifises` cookie), `GET /api/self/sites`, `GET /api/s/<site>/stat/device` | session cookie |
| MaxMind | `GET https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City&suffix=tar.gz&license_key=…` when the database is missing or over 30 days old; only with a license key set (GeoIP on) | license key as a query parameter ([a known weakness](security.md#known-weaknesses)) |
| ipify | `GET https://api.ipify.org` (10 s timeout) to learn the host's own public address, only with GeoIP on and when neither a viewer's address nor `fallback_ip` is in the GeoLite2 database; the answer is then reused until Varken restarts | none (a separate request; before 2.0.0 this went to `http://ip.42.pl` with the Tautulli API key attached, [now fixed](security.md#fixed-in-200)) |

Supported versions: Sonarr 4 and Radarr 4 or later (their `/api/v3`), and Lidarr 1 or later (`/api/v1`).
Before 2.1.0 the Sonarr and Radarr modules used the unversioned `/api/...` paths, which current releases no
longer serve. A reply in an unexpected shape (an older API, say) logs an error and marks the job down.
Sonarr 5's new API is [planned](roadmap.md); Sonarr 5 is in beta as of 2.1.0.

Requests to the services and MaxMind have no timeouts today ([security.md](security.md#known-weaknesses));
only the ipify lookup has one.

## Files

| Path (in the data folder) | Written by Varken | Contents |
| --- | --- | --- |
| `varken.ini` | when created from the example, or when missing keys are filled in | the configuration ([configuration.md](configuration.md)) |
| `varken.example.ini` | no (the image copies it in on start) | the template |
| `GeoLite2-City.mmdb` | downloaded and replaced about every 30 days, when Tautulli is enabled with a MaxMind license key | MaxMind's city database; only the `.mmdb` file is extracted from the archive |
| `GeoLite2-City.tar.gz` | temporarily, during a download | |
| `logs/varken.log*` | unless `LOG_TO_FILE=false` | the log |

Nothing else is written. The data that matters lives in the Prometheus server that scrapes Varken.

## Image

`ghcr.io/honeybeartech/varken`, built from the [`Dockerfile`](../Dockerfile): `python:3.14-slim` pinned by
version and digest, the hash-pinned packages from [`requirements.txt`](../requirements.txt), and Varken in
`/app`. It runs as the unprivileged uid/gid 1000:1000 with `DATA_FOLDER=/config`; `/config` is the only
path it writes to, and belongs to 1000:1000 in the image, so a new named volume there starts out writable.
Releases are published for linux/amd64 and linux/arm64, tagged with the version
(`2.1.0`), major.minor (`2.1`) and `latest`, signed and with an SBOM and provenance
([verifying-releases.md](verifying-releases.md)). It declares `EXPOSE 9180` for `/metrics`.
