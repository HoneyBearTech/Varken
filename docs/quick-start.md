# Quick start

Run Varken with InfluxDB and Grafana on one Docker host, collecting from one Tautulli server. You need
Docker with Compose v2 and Tautulli's address and API key (Tautulli: Settings, Web Interface, API).
Optionally, a MaxMind license key, free with a [GeoLite2 account](https://www.maxmind.com/en/geolite2/signup),
places viewers on a map; without one, streams have no location. To use Prometheus instead of InfluxDB, or as
well, see [below](#prometheus-instead-of-or-as-well-as-influxdb).

## 1. Get the files and configure

```sh
git clone https://github.com/HoneyBearTech/Varken.git && cd Varken
git checkout v2.0.0                        # a release tag instead of master
cp .env.example .env && chmod 600 .env
mkdir -p config && sudo chown 1000:1000 config
```

`config/` holds `varken.ini`, the GeoLite2 database and the logs. It must belong to uid 1000, the user the
image runs as (or set `VARKEN_UID`/`VARKEN_GID` in `.env` and give it to them instead). A Docker named volume
in its place needs no `chown`: the image's `/config` already belongs to uid 1000.

Edit `.env`:

- `VARKEN_VERSION`: the release to run, for example `2.0.0`.
- `VRKN_GLOBAL_MAXMIND_LICENSE_KEY`: your MaxMind license key, or leave it empty to run without GeoIP
  (Varken then never contacts MaxMind).
- `VRKN_TAUTULLI_1_URL`: Tautulli's host and port without `http://`, for example
  `tautulli.example.com:8181`, and `VRKN_TAUTULLI_1_APIKEY`. If you reach Tautulli over HTTPS, set
  `VRKN_TAUTULLI_1_SSL=true` and `VRKN_TAUTULLI_1_VERIFY_SSL=true`.
- `VRKN_TAUTULLI_1_FALLBACK_IP`: your own public IPv4 address. Viewers on your LAN are placed there,
  since their private addresses can't be located.
- Add `DEBUG=false`, unless you are troubleshooting: the debug log is on by default and records who watched
  what.

The InfluxDB settings already point at the `influxdb` service in the compose file. Every other setting, and
how to turn on Sonarr, Radarr and the rest, is in [configuration.md](configuration.md). `.env` holds secrets
and is gitignored; never commit it.

## 2. Start it

```sh
docker compose up -d
docker compose logs -f varken
```

On the first start Varken creates `config/varken.ini` from the example (the values in `.env` override it),
downloads the GeoLite2 database (with a MaxMind key), creates the `varken` database in InfluxDB, and runs
every job once. You should see lines like these (timestamps left out):

```
INFO : Varken : Starting Varken...
INFO : helpers : TAUTULLI_SERVER_IDS : [1]
INFO : dbmanager : Influxdb version: 1.12.4
INFO : dbmanager : Creating varken database
```

After that, with `DEBUG=false`, it stays quiet unless something fails. Common first-run errors:

- `Could not download MaxMind DB`: a wrong license key. To run without GeoIP, leave the key empty.
- `No MaxMind license key: GeoIP is off ...` is not an error: it means no key is set.
- `Your api key is incorrect for ...` or `Cannot resolve the url/ip/port`: check the Tautulli URL, key
  and `SSL` setting.
- `Invalid fallback_ip`: the fallback address must be a public IPv4 address.
- A `PermissionError` naming `/config`: `config/` doesn't belong to uid 1000 (step 1).

Until 2.0.0 is published, skip the `git checkout`, build the image from `master` yourself with
`docker build -t ghcr.io/honeybeartech/varken:latest .`, and leave `VARKEN_VERSION=latest`.

## 3. Look at the data in Grafana

Open <http://127.0.0.1:3000> on the Docker host (Grafana's first login is `admin`/`admin`; it asks for a
new password), and add a data source:

- Type **InfluxDB**, query language **InfluxQL**, URL `http://influxdb:8086`, database `varken`.

The data is in the `Tautulli` measurement; [interfaces.md](interfaces.md#output-influxdb) lists every tag
and field. Upstream Varken's dashboard (grafana.com dashboard 9585, which
[`utilities/grafana_build.py`](../utilities/grafana_build.py) imports) uses the Worldmap and old Pie Chart
panels, which Grafana 12 and later no longer include; after importing it, replace those panels with
Geomap and Pie chart, or build your own panels.

Grafana listens only on `127.0.0.1` by default. Keep it that way unless a reverse proxy or firewall protects
it: the dashboards show who watched what, and from roughly where.

## Prometheus instead of, or as well as, InfluxDB

Varken can also serve its data as Prometheus metrics at `/metrics`. In `.env`:

- `VRKN_PROMETHEUS_ENABLED=true` turns the endpoint on, on port 9180 (`VRKN_PROMETHEUS_PORT` changes it; ScyllaDB
  also uses 9180 by default).
- `VRKN_INFLUXDB_ENABLED=false` turns InfluxDB off, for a Prometheus-only setup. You can then delete the
  `influxdb` service from `docker-compose.yml`, along with the `depends_on` entries that name it. At least
  one output must stay on.
- Leave `VRKN_PROMETHEUS_STREAM_DETAILS=false` unless whoever can read your metrics may see who is watching
  what, and from where.

After `docker compose up -d`, the log shows `Serving Prometheus metrics on 0.0.0.0:9180/metrics`. A
Prometheus on the same Docker network scrapes it as `varken:9180`:

```yaml
scrape_configs:
  - job_name: varken
    scrape_interval: 30s
    static_configs:
      - targets: ["varken:9180"]
```

For a Prometheus outside the compose project, uncomment the `ports` lines of the `varken` service in
`docker-compose.yml`, which publish the endpoint on `127.0.0.1:9180` only, and scrape `127.0.0.1:9180`. The
endpoint has no authentication: don't publish it on an address others can reach
([security.md](security.md#the-metrics-endpoint)). Every metric is listed in
[interfaces.md](interfaces.md#output-prometheus-metrics).

## Next

- [Installing](installing.md) covers other ways to run Varken (plain `docker run`, Unraid, bare Python with
  systemd) and running it securely.
- [Configuration](configuration.md) has every setting, for adding Sonarr, Radarr, Lidarr, Ombi, SickChill
  and UniFi, and for reading secrets from files (`VRKN_*_FILE`) or logging to stdout only (`LOG_TO_FILE`).
