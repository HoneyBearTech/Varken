# Varken

[![CI](https://github.com/HoneyBearTech/Varken/actions/workflows/ci.yml/badge.svg)](https://github.com/HoneyBearTech/Varken/actions/workflows/ci.yml)
[![CodeQL](https://github.com/HoneyBearTech/Varken/actions/workflows/codeql.yml/badge.svg)](https://github.com/HoneyBearTech/Varken/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/HoneyBearTech/Varken/badge)](https://scorecard.dev/viewer/?uri=github.com/HoneyBearTech/Varken)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/15525/badge)](https://www.bestpractices.dev/projects/15525)
[![OpenSSF Baseline](https://www.bestpractices.dev/projects/15525/baseline)](https://www.bestpractices.dev/projects/15525)

<p align="center">
<img width="800" src="assets/varken_full_banner.jpg" alt="Varken logo banner">
</p>

Varken collects data from the Plex ecosystem (Tautulli, Sonarr, Radarr, Lidarr, Ombi, SickChill) and UniFi and
serves it as Prometheus metrics at `/metrics`, for Prometheus to scrape and Grafana to chart.

Varken is Dutch for PIG; PIG stood for Plex/InfluxDB/Grafana, the stack it was first written for (it no longer
writes to InfluxDB). This is a standalone continuation of
[Boerderij/Varken](https://github.com/Boerderij/Varken) by DirtyCajunRice, samwiseg0 and contributors, whose
last release was 1.7.7 in 2020. It's maintained by [HoneyBearTech](https://github.com/HoneyBearTech) and isn't
affiliated with the original authors: please don't take questions about this version to their channels.

<p align="center">
<img width="800" src="https://i.imgur.com/3hNZTkC.png" alt="Example Grafana dashboard built on Varken's data">
</p>

## Documentation

- [Quick start](docs/quick-start.md), [installing](docs/installing.md) (Docker, Docker Compose or Python),
  [upgrading from upstream 1.7.x and backups](docs/upgrading.md) and [verifying releases](docs/verifying-releases.md).
- [Configuration](docs/configuration.md): every `varken.ini` setting and the `VRKN_*` variable that overrides it.
- [Architecture](docs/architecture.md): the components, and how data flows from each service to the Prometheus
  metrics.
- [Security requirements](docs/security.md): what Varken does and doesn't protect, the known weaknesses, and the
  [assurance case](docs/assurance-case.md) behind them.
- [External interfaces](docs/interfaces.md): the APIs Varken calls, the Prometheus metrics it serves, and the
  command line. [Dependencies and vulnerability management](docs/dependencies.md).
- [Grafana dashboard](dashboard/README.md): the original Varken dashboard on the Prometheus metrics, ready to
  import.
- [Roadmap](docs/roadmap.md): where the project is going, and what it won't do.
- [Support](SUPPORT.md): which versions get fixes, and for how long.
- [Contributing](CONTRIBUTING.md), [Code of Conduct](CODE_OF_CONDUCT.md), [Governance](GOVERNANCE.md) and
  [reporting a vulnerability](SECURITY.md). The full index is in [docs/README.md](docs/README.md).

## What it collects

| Service | Data |
|---|---|
| [Tautulli](https://tautulli.com/) | Current streams (player, quality, transcode decision, bandwidth, GeoIP location) and library sizes |
| [Sonarr](https://sonarr.tv/) 4+ | Queue, missing episodes and upcoming episodes |
| [Radarr](https://radarr.video/) 4+ | Queue and missing movies |
| [Lidarr](https://lidarr.audio/) 1+ | Queue, missing albums and upcoming albums (job health only) |
| [Ombi](https://ombi.io/) | Request and issue counts by status, and each request |
| [SickChill](https://sickchill.github.io/) | Missed and upcoming episodes |
| [UniFi](https://ui.com/) | Gateway (USG) statistics |

Every module supports several servers. Tautulli locations come from MaxMind's
[GeoLite2](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) database, which needs a free MaxMind
account (its account ID and a license key); without a key, Varken runs with GeoIP off and streams have no
location.

## Getting started

You need Docker with Compose, a Prometheus to scrape Varken and a Grafana to look at the data. Varken ships
neither; in the maintainer's setup, [Argus](https://github.com/HoneyBearTech/Argus) provides both. The
[example compose file](docker-compose.yml) runs Varken alone and publishes `/metrics` on `127.0.0.1:9180`:

```sh
git clone https://github.com/HoneyBearTech/Varken.git
cd Varken
cp .env.example .env                       # fill in your services; never commit .env
sudo mkdir -p /srv/config/varken/config && sudo chown -R 1000:1000 /srv/config/varken   # CONFIG_ROOT
docker compose up -d
docker compose logs -f varken
```

Then add a scrape job to your Prometheus: `varken:9180` when Prometheus shares Varken's Docker network, or
`<host>:9180` through the published port ([quick start](docs/quick-start.md#3-scrape-it-with-prometheus)). In
Grafana, use that Prometheus as the data source and import the [Varken dashboard](dashboard/README.md), or
build your own on the [metrics Varken serves](docs/interfaces.md#output-prometheus-metrics). The [quick start](docs/quick-start.md)
walks through the first run, and [installing](docs/installing.md) covers running the image on its own
(`ghcr.io/honeybeartech/varken`), Unraid, and Python with systemd.

Upgrading from `boerderij/varken`? Varken no longer writes to InfluxDB, the image name changed and the
container no longer runs as root: read [upgrading](docs/upgrading.md) first.

## Configuration

Varken reads `varken.ini` from its data folder (`/config` in the container), which it creates from
[`data/varken.example.ini`](data/varken.example.ini) on the first start. Any key can be overridden by an
environment variable named `VRKN_<SECTION>_<KEY>`, for example `VRKN_TAUTULLI_1_APIKEY`. That's how
[`.env.example`](.env.example) configures the compose setup. [docs/configuration.md](docs/configuration.md)
lists every setting and its default.

- `[global]`: which server ids each module collects from (`false` turns a module off), and the MaxMind license
  key and account ID.
- `[prometheus]`: the `/metrics` endpoint, which is always on: `bind` (`0.0.0.0`), `port` (`9180`) and
  `stream_details` (per-viewer metrics and Ombi requesters, off by default). An `[influxdb]` section left over from upstream is
  ignored.
- `[<module>-<id>]`, such as `[tautulli-1]` or `[sonarr-2]`: the server's address, API key, TLS settings, which
  data to collect and how often.

Any `VRKN_*` value can also be read from a file, for Docker and compose secrets: set
`VRKN_<SECTION>_<KEY>_FILE` to its path. Environment settings for the container: `DATA_FOLDER` (default
`/config`), `DEBUG` (`false` by default, which logs at INFO; `true` for debug logs), `LOG_TO_FILE` (`true` by default;
`false` logs to stdout only) and `TZ`.

## Running it securely

- Run the image as shipped: an unprivileged user (uid 1000), and in the example compose file a read-only root
  filesystem, no Linux capabilities and `no-new-privileges`.
- Varken holds API keys for every service it reads, so keep `varken.ini` and `.env` readable only by you. It
  redacts known secrets from its logs, but check the logs before sharing them.
- Use HTTPS with `verify_ssl = true` wherever a service supports it. Verification is off by default, for
  compatibility with upstream configs.
- The `/metrics` endpoint has no authentication or TLS: keep it on a private network. The example compose file
  publishes it on `127.0.0.1` only (`VARKEN_METRICS_BIND`). Leave `stream_details` off unless everyone who can
  read the metrics may see who watches what.
- Keep Prometheus and Grafana off the internet too: they hold the same data.

[docs/security.md](docs/security.md) has the details and the known weaknesses still being worked on.

## Related projects

[Argus](https://github.com/HoneyBearTech/Argus), the maintainer's Prometheus and Grafana homelab monitoring stack,
will scrape Varken's metrics for its Tautulli dashboards (planned, in the Argus repository).

## License

[MIT](LICENSE). Copyright (c) 2018 Boerderij and (c) 2026 HoneyBearTech.
