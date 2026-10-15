# Quick start

Run Varken with InfluxDB and Grafana on one Docker host, collecting from one Tautulli server. You need
Docker with Compose v2, Tautulli's address and API key (Tautulli: Settings, Web Interface, API), and a
MaxMind license key, which is free with a [GeoLite2 account](https://www.maxmind.com/en/geolite2/signup)
and is needed to place viewers on a map.

## 1. Get the files and configure

```sh
git clone https://github.com/HoneyBearTech/Varken.git && cd Varken
git checkout v2.0.0                        # a release tag instead of master
cp .env.example .env && chmod 600 .env
mkdir -p config && sudo chown 1000:1000 config
```

`config/` holds `varken.ini`, the GeoLite2 database and the logs. It must belong to uid 1000, the user the
image runs as (or set `VARKEN_UID`/`VARKEN_GID` in `.env` and give it to them instead).

Edit `.env`:

- `VARKEN_VERSION`: the release to run, for example `2.0.0`.
- `VRKN_GLOBAL_MAXMIND_LICENSE_KEY`: your MaxMind license key.
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
downloads the GeoLite2 database, creates the `varken` database in InfluxDB, and runs every job once. You
should see lines like these (timestamps left out):

```
INFO : Varken : Starting Varken...
INFO : helpers : TAUTULLI_SERVER_IDS : [1]
INFO : dbmanager : Influxdb version: 1.12.4
INFO : dbmanager : Creating varken database
```

After that, with `DEBUG=false`, it stays quiet unless something fails. Common first-run errors:

- `Could not download MaxMind DB`: a wrong or missing license key.
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

## Next

- [Installing](installing.md) covers other ways to run Varken (plain `docker run`, Unraid, bare Python with
  systemd) and running it securely.
- [Configuration](configuration.md) has every setting, for adding Sonarr, Radarr, Lidarr, Ombi, SickChill
  and UniFi.
