# Quick start

Run Varken on one Docker host, collecting from one Tautulli server, scrape it with a Prometheus you already
run, and chart it in Grafana. Varken includes neither Prometheus nor Grafana; in the maintainer's setup,
[Argus](https://github.com/HoneyBearTech/Argus) provides both. You need Docker with Compose v2 and Tautulli's
address and API key (Tautulli: Settings, Web Interface, API).
Optionally, a MaxMind license key, free with a [GeoLite2 account](https://www.maxmind.com/en/geolite2/signup),
places viewers on a map; without one, streams have no location.

## 1. Get the files and configure

```sh
git clone https://github.com/HoneyBearTech/Varken.git && cd Varken
git checkout v2.2.1                        # a release tag instead of master
cp .env.example .env && chmod 600 .env
sudo mkdir -p /srv/config/varken/config && sudo chown -R 1000:1000 /srv/config/varken
```

`CONFIG_ROOT/varken/config` (`CONFIG_ROOT` is `/srv/config` in `.env.example`) holds `varken.ini`, the GeoLite2
database and the logs. It must belong to uid 1000, the user the image runs as (or set `VARKEN_UID`/`VARKEN_GID`
in `.env` and give it to them instead). Keep it a host directory rather than a named Docker volume:
`docker volume prune` deletes named volumes whose container is stopped.

Edit `.env`:

- `VARKEN_VERSION`: the release to run, for example `2.2.1`.
- `VRKN_GLOBAL_MAXMIND_LICENSE_KEY` and `VRKN_GLOBAL_MAXMIND_ACCOUNT_ID`: your MaxMind license key and
  account ID, or leave the key empty to run without GeoIP (Varken then never contacts MaxMind).
- `VRKN_TAUTULLI_1_URL`: Tautulli's host and port without `http://`, for example
  `tautulli.example.com:8181`, and `VRKN_TAUTULLI_1_APIKEY`. If you reach Tautulli over HTTPS, set
  `VRKN_TAUTULLI_1_SSL=true` and `VRKN_TAUTULLI_1_VERIFY_SSL=true`.
- `VRKN_TAUTULLI_1_FALLBACK_IP`: your own public IPv4 address. Viewers on your LAN are placed there,
  since their private addresses can't be located.
- `VARKEN_METRICS_BIND`: where the compose file publishes `/metrics` on the host, `127.0.0.1:9180` by default
  (see [step 3](#3-scrape-it-with-prometheus)).
- Add `DEBUG=false`, unless you are troubleshooting: the debug log is on by default and records every
  request Varken makes.

Every other setting, and how to turn on Sonarr, Radarr and the rest, is in
[configuration.md](configuration.md). `.env` holds secrets and is gitignored; never commit it.

## 2. Start it

```sh
docker compose up -d
docker compose logs -f varken
```

On the first start Varken creates `config/varken.ini` from the example (the values in `.env` override it),
downloads the GeoLite2 database (with a MaxMind key), starts serving `/metrics` and runs every job once. You
should see lines like these (timestamps left out):

```
INFO : Varken : Starting Varken...
INFO : helpers : TAUTULLI_SERVER_IDS : [1]
INFO : metrics : Serving Prometheus metrics on 0.0.0.0:9180/metrics
```

`0.0.0.0:9180` is inside the container; on the host the port is published on `VARKEN_METRICS_BIND`. Check that
the jobs ran:

```sh
curl -s http://127.0.0.1:9180/metrics | grep varken_job_up
```

`varken_job_up{service="tautulli",server="1",job="activity"} 1.0` means Tautulli answered; `0.0` means the
last run failed, and the log says why. After that, with `DEBUG=false`, Varken stays quiet unless something
fails. Common first-run errors:

- `MaxMind refused the account ID and license key` or `Could not download the MaxMind DB`: check both, or
  leave the key empty to run without GeoIP. Varken keeps running either way, with no locations.
- `No MaxMind license key: GeoIP is off ...` is not an error: it means no key is set.
- `Your api key is incorrect for ...` or `Cannot resolve the url/ip/port`: check the Tautulli URL, key
  and `SSL` setting.
- `Invalid fallback_ip`: the fallback address must be a public IPv4 address.
- A `PermissionError` naming `/config`: `config/` doesn't belong to uid 1000 (step 1).
- `port is already allocated` from Docker: something on the host already uses 9180. Set
  `VARKEN_METRICS_BIND` to another port, for example `127.0.0.1:9181`, and scrape that.

To try unreleased changes, skip the `git checkout`, build the image from `master` yourself with
`docker build -t ghcr.io/honeybeartech/varken:latest .`, and leave `VARKEN_VERSION=latest`.

## 3. Scrape it with Prometheus

Add a scrape job to your Prometheus configuration (`prometheus.yml`) and reload Prometheus:

```yaml
scrape_configs:
  - job_name: varken
    scrape_interval: 30s
    static_configs:
      - targets: ["varken:9180"]
```

The target depends on where Prometheus runs:

- **In Docker, on a shared network** (the usual case, and how Argus runs it): connect the Prometheus
  container to Varken's network, `varken_default` (`docker network connect varken_default <prometheus>`, or
  list it as an external network in Prometheus' compose file), and scrape `varken:9180`. Nothing needs to be
  published on the host then; you can delete the `ports` entry from `docker-compose.yml`.
- **On the same host, outside Docker**: scrape `127.0.0.1:9180`, the compose file's default
  `VARKEN_METRICS_BIND`.
- **On another host**: set `VARKEN_METRICS_BIND` to the Docker host's private address, for example
  `<private-ip>:9180`, run `docker compose up -d` again, and scrape `<private-ip>:9180`.

The endpoint has no authentication or TLS: never publish it on an address others can reach
([security.md](security.md#the-metrics-endpoint)). In Prometheus' Targets page, `varken` should show as UP.

## 4. Chart it in Grafana

Add your Prometheus as a data source in Grafana, if it isn't one already, and build panels on Varken's
metrics. A few to start with:

| Panel | Query |
| --- | --- |
| Current streams | `sum by (server) (varken_tautulli_streams)` |
| Transcodes vs. direct play | `varken_tautulli_streams_by_decision` |
| WAN bandwidth | `varken_tautulli_bandwidth_bytes_per_second{network="wan"}` |
| Library sizes | `varken_tautulli_library_items{item="total"}` |
| Jobs failing (for an alert) | `varken_job_up == 0` |

Every metric and label is listed in [interfaces.md](interfaces.md#output-prometheus-metrics). Upstream
Varken's Grafana dashboards (such as grafana.com dashboard 9585) query InfluxDB and don't work with these
metrics. Leave `VRKN_PROMETHEUS_STREAM_DETAILS=false` unless whoever can read your metrics may see who is
watching what, and from where.

## Next

- [Installing](installing.md) covers other ways to run Varken (plain `docker run`, Unraid, bare Python with
  systemd) and running it securely.
- [Configuration](configuration.md) has every setting, for adding Sonarr, Radarr, Lidarr, Ombi, SickChill
  and UniFi, and for reading secrets from files (`VRKN_*_FILE`) or logging to stdout only (`LOG_TO_FILE`).
