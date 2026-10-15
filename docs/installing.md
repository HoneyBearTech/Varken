# Installing

Varken runs as one container (or one Python process) next to an InfluxDB 1.x server, a Prometheus server,
or both. It opens no ports unless the Prometheus output is on (port 9180); it only needs to reach the
services it reads, InfluxDB if enabled, and MaxMind if GeoIP is on. For a first look, the
[quick start](quick-start.md) is shorter; this page covers the choices.

## What you need

- **InfluxDB 1.x** (1.8 or later), reachable from Varken, **or Prometheus**, able to reach Varken
  ([below](#prometheus-instead-of-or-as-well-as-influxdb)), or both. InfluxDB 2 and 3 are not supported.
  Varken creates its database, `varken`, unless its user isn't allowed to; then create it yourself
  ([security.md](security.md#credentials)).
- **Grafana**, or anything else that can query InfluxDB or Prometheus, to look at the data.
- For Tautulli: your public IPv4 address for `fallback_ip` and, optionally, a **MaxMind license key**
  ([free GeoLite2 account](https://www.maxmind.com/en/geolite2/signup)) to place viewers on a map. Without
  a key, GeoIP is off and streams have no location.
- An API key for each service you want to read, or a read-only login for UniFi.
- With GeoIP on, outbound HTTPS to `download.maxmind.com` and, rarely, `api.ipify.org` (see
  [interfaces.md](interfaces.md#interfaces-varken-uses)). With GeoIP off, neither.
- For the image: a Linux host (amd64 or arm64) with Docker. For a bare install: Python 3.14 on any OS
  Python supports.

Every setting is in [configuration.md](configuration.md). Varken reads `varken.ini` in its data folder and
lets any key be overridden by a `VRKN_*` environment variable; the container examples below use an `.env`
file of those variables.

## Option 1: Docker Compose (recommended)

The repository's [`docker-compose.yml`](../docker-compose.yml) runs Varken, InfluxDB 1.x and Grafana with
images pinned by digest, and Varken locked down (non-root, read-only root filesystem, no capabilities).
Follow the [quick start](quick-start.md). If you already run InfluxDB or Grafana, delete those services from
the file and point `VRKN_INFLUXDB_URL` at yours.

The compose file reads these from `.env`, besides the `VRKN_*` settings:

| Variable | Default | What |
| --- | --- | --- |
| `VARKEN_VERSION` | `latest` | Image tag to run. Set a release such as `2.0.0`, so upgrades happen when you choose. |
| `VARKEN_CONFIG_DIR` | `./config` | Host folder mounted at `/config`. |
| `VARKEN_UID` / `VARKEN_GID` | `1000` | The user and group the container runs as; they must own `VARKEN_CONFIG_DIR`. |
| `GRAFANA_BIND` | `127.0.0.1:3000` | Where Grafana listens on the host. |
| `TZ` | `UTC` | Time zone for log timestamps. Points in InfluxDB carry their offset either way. |

## Option 2: `docker run`

```sh
mkdir -p config && sudo chown 1000:1000 config
docker run -d --name varken --restart unless-stopped \
  --user 1000:1000 --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true \
  --env-file .env -v "$PWD/config:/config" \
  --network <the network InfluxDB is on> \
  ghcr.io/honeybeartech/varken:2.0.0
```

A bind-mounted folder such as `config/` must belong to uid 1000. A Docker named volume
(`-v varken-config:/config`) needs no `chown`: the image creates `/config` owned by 1000:1000, and a new
volume starts out with that ownership. To scrape the Prometheus output from outside Docker, add
`-p 127.0.0.1:9180:9180`.

Instead of an `.env` file you can write `config/varken.ini` yourself from
[`data/varken.example.ini`](../data/varken.example.ini) (`chmod 600`, owned by uid 1000). Images are
published for linux/amd64 and linux/arm64 as `ghcr.io/honeybeartech/varken`, tagged with the version
(`2.0.0`), major.minor (`2.0`) and `latest`. [Verify the image](verifying-releases.md) before the first
start; pinning its digest is stronger than pinning a tag.

## Option 3: Unraid

[`varken.xml`](../varken.xml) is an Unraid container template (still marked work in progress). It runs the
GHCR image as `99:100` (Unraid's `nobody:users`), so the appdata folder must belong to them:
`chown -R 99:100 /mnt/user/appdata/varken`. Put your settings in `varken.ini` in that folder, or add
`VRKN_*` variables to the template.

## Option 4: Bare Python

For hosts without Docker. The repository's [`varken.systemd`](../varken.systemd) unit assumes the checkout
is in `/opt/Varken`, a virtual environment in `/opt/Varken/varken-venv`, and a `varken` system user.

```sh
sudo git clone https://github.com/HoneyBearTech/Varken.git /opt/Varken
cd /opt/Varken && sudo git checkout v2.0.0
sudo python3.14 -m venv varken-venv
sudo varken-venv/bin/pip install --require-hashes --no-deps -r requirements.txt

sudo useradd --system --no-create-home --shell /usr/sbin/nologin varken   # Debian/Ubuntu: adduser --system --group --no-create-home varken
sudo cp data/varken.example.ini data/varken.ini      # then edit it
sudo chown -R varken:varken data && sudo chmod 600 data/varken.ini
```

`--require-hashes --no-deps` makes pip install exactly the packages and versions in `requirements.txt`, and
refuse any file whose hash doesn't match. Only `data/` belongs to the `varken` user: it doesn't need to
write to its own code. Try it in the foreground first:

```sh
sudo -u varken /opt/Varken/varken-venv/bin/python /opt/Varken/Varken.py -ND   # -ND: log at INFO
```

The data folder defaults to `data/` next to `Varken.py`; use `-d /some/folder` or `DATA_FOLDER` to keep it
elsewhere.

### Running under systemd

```sh
sudo cp /opt/Varken/varken.systemd /etc/systemd/system/varken.service
sudo systemctl edit varken        # add the hardening below
sudo systemctl daemon-reload
sudo systemctl enable --now varken
journalctl -u varken -f
```

The unit runs Varken as `varken:varken` and restarts it 30 seconds after a failure. The drop-in below turns
debug logging off and gives the service the same kind of sandbox as the container: it can write only to
the data folder.

```ini
[Service]
Environment=DEBUG=false
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=/opt/Varken/data
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
CapabilityBoundingSet=
```

## Prometheus instead of, or as well as, InfluxDB

Varken can serve its data as Prometheus metrics, instead of writing to InfluxDB or as well as. The settings
are in [configuration.md](configuration.md#prometheus), the metrics in
[interfaces.md](interfaces.md#output-prometheus-metrics):

| Setting | Environment variable | Default | What |
| --- | --- | --- | --- |
| `[prometheus]` `enabled` | `VRKN_PROMETHEUS_ENABLED` | `false` | Serve `/metrics`. |
| `[prometheus]` `bind` | `VRKN_PROMETHEUS_BIND` | `0.0.0.0` | IP address to listen on; `127.0.0.1` for a Prometheus on the same host. |
| `[prometheus]` `port` | `VRKN_PROMETHEUS_PORT` | `9180` | Port to listen on (ScyllaDB also uses 9180; change it if it clashes). |
| `[prometheus]` `stream_details` | `VRKN_PROMETHEUS_STREAM_DETAILS` | `false` | Add per-viewer metrics (who watches what, and from which city). |
| `[influxdb]` `enabled` | `VRKN_INFLUXDB_ENABLED` | `true` | `false` for a Prometheus-only setup. At least one output must be on. |

A `varken.ini` from an earlier version gets these keys, with the defaults, on its first start, so an upgrade
keeps writing to InfluxDB with Prometheus off. Then add a scrape job to Prometheus:

```yaml
scrape_configs:
  - job_name: varken
    scrape_interval: 30s
    static_configs:
      - targets: ["varken:9180"]
```

`varken:9180` works when Prometheus is on the same Docker network as the Varken container. Otherwise use the
address you published or bound the port on: `127.0.0.1:9180` with the compose file's commented `ports` lines
or `docker run -p 127.0.0.1:9180:9180`, or the host's address for a bare install with `bind` set to it. The
endpoint has no authentication and no TLS, so keep it off any network others can reach
([security.md](security.md#the-metrics-endpoint)).

## Running it securely

- Keep `varken.ini` and `.env` at `600`, owned by the user Varken runs as, and never commit them. With
  Docker or compose secrets, point `VRKN_<SECTION>_<KEY>_FILE` at the secret file instead of putting the value
  in `.env` ([configuration.md](configuration.md#values-from-files-_file)).
- Use `ssl = true` and `verify_ssl = true` for every service you reach over a network you don't fully
  trust; both are off in the example.
- Give Varken its own API keys, a read-only UniFi account, and a non-admin InfluxDB user where you can.
- Set `DEBUG=false`. The debug log is on by default and contains viewing data. In a container,
  `LOG_TO_FILE=false` logs to stdout only, with no `logs/` folder in `/config`.
- Keep the container non-root with a read-only root filesystem, no capabilities and `no-new-privileges`, as
  in the compose file. Publish no ports for InfluxDB, and none for Varken unless Prometheus must reach it
  from outside Docker; then publish 9180 on a private or loopback address only.
- Leave `stream_details` off unless everyone who can read the metrics may see per-viewer data.

The reasons, and the known weaknesses, are in [security.md](security.md).

## Uninstalling

```sh
docker compose down               # add -v to delete the InfluxDB and Grafana volumes, and the data with them
rm -rf config .env
```

For a bare install: `sudo systemctl disable --now varken`, remove `/etc/systemd/system/varken.service`,
`/opt/Varken` and the `varken` user. If you keep InfluxDB, drop the data with `DROP DATABASE varken`.
Varken changed nothing in the services it read; revoke the API keys and MaxMind license key you made for
it.
