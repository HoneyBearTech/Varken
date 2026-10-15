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
writes it to InfluxDB 1.x for Grafana dashboards. A Prometheus `/metrics` output is
[planned](docs/roadmap.md), so it can also feed Prometheus-based stacks.

Varken is Dutch for PIG; PIG stands for Plex/InfluxDB/Grafana. This is a standalone continuation of
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
- [Architecture](docs/architecture.md): the components, and how data flows from each service to InfluxDB.
- [Security requirements](docs/security.md): what Varken does and doesn't protect, the known weaknesses, and the
  [assurance case](docs/assurance-case.md) behind them.
- [External interfaces](docs/interfaces.md): the APIs Varken calls, the InfluxDB measurements it writes, and the
  command line. [Dependencies and vulnerability management](docs/dependencies.md).
- [Roadmap](docs/roadmap.md): where the project is going, and what it won't do.
- [Support](SUPPORT.md): which versions get fixes, and for how long.
- [Contributing](CONTRIBUTING.md), [Code of Conduct](CODE_OF_CONDUCT.md), [Governance](GOVERNANCE.md) and
  [reporting a vulnerability](SECURITY.md). The full index is in [docs/README.md](docs/README.md).

## What it collects

| Service | Data |
|---|---|
| [Tautulli](https://tautulli.com/) | Current streams (player, quality, transcode decision, bandwidth, GeoIP location) and library sizes |
| [Sonarr](https://sonarr.tv/) | Queue, missing episodes and upcoming episodes |
| [Radarr](https://radarr.video/) | Queue and missing movies |
| [Lidarr](https://lidarr.audio/) | Queue, missing albums and upcoming albums |
| [Ombi](https://ombi.io/) | Request counts by type and status, issue counts |
| [SickChill](https://sickchill.github.io/) | Missing episodes |
| [UniFi](https://ui.com/) | Gateway (USG) statistics |

Every module supports several servers. Tautulli locations come from MaxMind's
[GeoLite2](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) database, which needs a free MaxMind
license key.

## Getting started

You need Docker with Compose. The [example compose file](docker-compose.yml) runs Varken with InfluxDB 1.12 and
Grafana:

```sh
git clone https://github.com/HoneyBearTech/Varken.git
cd Varken
cp .env.example .env                       # fill in your services; never commit .env
mkdir -p config && sudo chown 1000:1000 config
docker compose up -d
docker compose logs -f varken
```

Grafana listens on <http://127.0.0.1:3000>. Add InfluxDB (`http://influxdb:8086`, database `varken`) as a data
source and build dashboards on the [measurements Varken writes](docs/interfaces.md). The
[quick start](docs/quick-start.md) walks through the first run, and [installing](docs/installing.md) covers
running the image on its own (`ghcr.io/honeybeartech/varken`), Unraid, and Python with systemd.

Upgrading from `boerderij/varken`? The image name changed and the container no longer runs as root: read
[upgrading](docs/upgrading.md) first.

## Configuration

Varken reads `varken.ini` from its data folder (`/config` in the container), which it creates from
[`data/varken.example.ini`](data/varken.example.ini) on the first start. Any key can be overridden by an
environment variable named `VRKN_<SECTION>_<KEY>`, for example `VRKN_TAUTULLI_1_APIKEY`. That's how
[`.env.example`](.env.example) configures the compose setup. [docs/configuration.md](docs/configuration.md)
lists every setting and its default.

- `[global]`: which server ids each module collects from (`false` turns a module off), and the MaxMind license
  key.
- `[influxdb]`: where to write. Varken creates the `varken` database with a 30-day retention policy unless it
  already exists.
- `[<module>-<id>]`, such as `[tautulli-1]` or `[sonarr-2]`: the server's address, API key, TLS settings, which
  data to collect and how often.

Environment settings for the container: `DATA_FOLDER` (default `/config`), `DEBUG` (`True` by default; set
`False` for info-level logs) and `TZ`.

## Running it securely

- Run the image as shipped: an unprivileged user (uid 1000), and in the example compose file a read-only root
  filesystem, no Linux capabilities and `no-new-privileges`.
- Varken holds API keys for every service it reads, so keep `varken.ini` and `.env` readable only by you. It
  redacts known secrets from its logs, but check the logs before sharing them.
- Use HTTPS with `verify_ssl = true` wherever a service supports it. Verification is off by default, for
  compatibility with upstream configs.
- Keep InfluxDB and Grafana off the internet. The example binds Grafana to localhost only.

[docs/security.md](docs/security.md) has the details and the known weaknesses still being worked on.

## Related projects

[Argus](https://github.com/HoneyBearTech/Argus), the maintainer's Prometheus and Grafana homelab monitoring stack,
will scrape Varken's planned Prometheus output for its Tautulli dashboards.

## License

[MIT](LICENSE). Copyright (c) 2018 Boerderij and (c) 2026 HoneyBearTech.
