# Installing

Varken runs as one container (or one Python process) that a Prometheus server scrapes. It listens on one
port, 9180, for `/metrics`, and only needs to reach the services it reads and, with GeoIP on, MaxMind. For a
first look, the [quick start](quick-start.md) is shorter; this page covers the choices.

## What you need

- **Prometheus**, able to reach Varken on port 9180 ([below](#scraping-it-with-prometheus)).
- **Grafana**, or anything else that can query Prometheus, to look at the data. Varken includes neither; in
  the maintainer's setup, [Argus](https://github.com/HoneyBearTech/Argus) provides both.
- For Tautulli: your public IPv4 address for `fallback_ip` and, optionally, a **MaxMind license key and
  account ID** ([free GeoLite2 account](https://www.maxmind.com/en/geolite2/signup)) to place viewers on a map. Without
  a key, GeoIP is off and streams have no location.
- An API key for each service you want to read, or a read-only login for UniFi.
- With GeoIP on, outbound HTTPS to `download.maxmind.com` (which redirects to MaxMind's storage on
  `*.r2.cloudflarestorage.com`) and, rarely, `api.ipify.org` (see
  [interfaces.md](interfaces.md#interfaces-varken-uses)). With GeoIP off, neither.
- For the image: a Linux host (amd64 or arm64) with Docker. For a bare install: Python 3.14 on any OS
  Python supports.

Every setting is in [configuration.md](configuration.md). Varken reads `varken.ini` in its data folder and
lets any key be overridden by a `VRKN_*` environment variable; the container examples below use an `.env`
file of those variables.

## Option 1: Docker Compose (recommended)

The repository's [`docker-compose.yml`](../docker-compose.yml) runs Varken alone, locked down (non-root,
read-only root filesystem, no capabilities), and publishes `/metrics` on `127.0.0.1:9180`. It has no
Prometheus, InfluxDB or Grafana: point yours at it. Follow the [quick start](quick-start.md).

The compose file reads these from `.env`, besides the `VRKN_*` settings:

| Variable | Default | What |
| --- | --- | --- |
| `VARKEN_VERSION` | `latest` | Image tag to run. Set a release such as `2.1.0`, so upgrades happen when you choose. |
| `CONFIG_ROOT` | `/srv/config` (required) | Where app data lives; Varken's is `CONFIG_ROOT/varken/config`, mounted at `/config`. Not inside `/var/lib/docker/volumes`. |
| `VARKEN_UID` / `VARKEN_GID` | `1000` | The user and group the container runs as; they must own `CONFIG_ROOT/varken/config`. |
| `VARKEN_METRICS_BIND` | `127.0.0.1:9180` | Host address and port `/metrics` is published on. Keep it on a loopback or private address. |
| `TZ` | `UTC` | Time zone for log timestamps. |

When Prometheus runs in Docker on the same host, it can join Varken's network (`varken_default`) and scrape
`varken:9180` instead; then you can delete the `ports` entry, and nothing is published.

## Option 2: `docker run`

```sh
sudo mkdir -p /srv/config/varken/config && sudo chown -R 1000:1000 /srv/config/varken
docker run -d --name varken --restart unless-stopped \
  --user 1000:1000 --read-only --cap-drop ALL --security-opt no-new-privileges:true \
  --env-file .env -v /srv/config/varken/config:/config \
  --network <the network Prometheus is on> \
  ghcr.io/honeybeartech/varken:2.1.0
```

The host directory must belong to uid 1000. Prefer it to a Docker named volume: `docker volume prune` (and
Portainer's "remove unused volumes") deletes a named volume whose container is stopped. If you use one anyway,
it needs no `chown`: the image creates `/config` owned by 1000:1000. For a Prometheus outside Docker, replace `--network ...` with
`-p 127.0.0.1:9180:9180` (or a private address instead of `127.0.0.1`).

Instead of an `.env` file you can write `config/varken.ini` yourself from
[`data/varken.example.ini`](../data/varken.example.ini) (`chmod 600`, owned by uid 1000). Images are
published for linux/amd64 and linux/arm64 as `ghcr.io/honeybeartech/varken`, tagged with the version
(`2.1.0`), major.minor (`2.1`) and `latest`. [Verify the image](verifying-releases.md) before the first
start; pinning its digest is stronger than pinning a tag.

## Option 3: Unraid

[`varken.xml`](../varken.xml) is an Unraid container template (still marked work in progress). It runs the
GHCR image as `99:100` (Unraid's `nobody:users`), so the appdata folder must belong to them:
`chown -R 99:100 /mnt/user/appdata/varken`. Put your settings in `varken.ini` in that folder, or add
`VRKN_*` variables to the template. The template publishes port 9180 for Prometheus to scrape; the endpoint
has no authentication, so keep the server's port off networks others can reach.

## Option 4: Bare Python

For hosts without Docker. The repository's [`varken.systemd`](../varken.systemd) unit assumes the checkout
is in `/opt/Varken`, a virtual environment in `/opt/Varken/varken-venv`, and a `varken` system user.

```sh
sudo git clone https://github.com/HoneyBearTech/Varken.git /opt/Varken
cd /opt/Varken && sudo git checkout v2.1.0
sudo python3.14 -m venv varken-venv
sudo varken-venv/bin/pip install --require-hashes --no-deps -r requirements.txt

# Debian/Ubuntu also: sudo adduser --system --group --no-create-home varken
sudo useradd --system --no-create-home --shell /usr/sbin/nologin varken
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
elsewhere. `/metrics` listens on `[prometheus]` `bind`:`port`, `0.0.0.0:9180` by default: set `bind` to
`127.0.0.1` for a Prometheus on the same host, or to the host's private address.

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

## Scraping it with Prometheus

Varken always serves its metrics; these settings say where. They are in
[configuration.md](configuration.md#prometheus), the metrics in
[interfaces.md](interfaces.md#output-prometheus-metrics):

| Setting | Environment variable | Default | What |
| --- | --- | --- | --- |
| `[prometheus]` `bind` | `VRKN_PROMETHEUS_BIND` | `0.0.0.0` | IP address to listen on; `127.0.0.1` for a Prometheus on the same host. |
| `[prometheus]` `port` | `VRKN_PROMETHEUS_PORT` | `9180` | Port to listen on (ScyllaDB also uses 9180; change it if it clashes). |
| `[prometheus]` `stream_details` | `VRKN_PROMETHEUS_STREAM_DETAILS` | `false` | Add per-viewer metrics (who watches what, and from which city). |

A `varken.ini` from upstream Varken gets the `[prometheus]` section, with these defaults, on its first start
([upgrading.md](upgrading.md)). Then add a scrape job to Prometheus:

```yaml
scrape_configs:
  - job_name: varken
    scrape_interval: 30s
    static_configs:
      - targets: ["varken:9180"]
```

`varken:9180` works when Prometheus is on the same Docker network as the Varken container. Otherwise use the
address you published or bound the port on, `<host>:9180`: `127.0.0.1:9180` with the compose file's default
`VARKEN_METRICS_BIND` or `docker run -p 127.0.0.1:9180:9180`, a private address you published it on, or the
host's address for a bare install with `bind` set to it. The endpoint has no authentication and no TLS, so
keep it off any network others can reach ([security.md](security.md#the-metrics-endpoint)).

In Grafana, use that Prometheus as the data source and build dashboards on the metrics; the
[quick start](quick-start.md#4-chart-it-in-grafana) has a few queries to start with. Upstream Varken's
dashboards query InfluxDB and don't work with them.

## Running it securely

- Keep `varken.ini` and `.env` at `600`, owned by the user Varken runs as, and never commit them. With
  Docker or compose secrets, point `VRKN_<SECTION>_<KEY>_FILE` at the secret file instead of putting the value
  in `.env` ([configuration.md](configuration.md#values-from-files-_file)).
- Use `ssl = true` and `verify_ssl = true` for every service you reach over a network you don't fully
  trust; both are off in the example.
- Give Varken its own API keys and a read-only UniFi account.
- Set `DEBUG=false`. The debug log is on by default and records every request Varken makes. In a container,
  `LOG_TO_FILE=false` logs to stdout only, with no `logs/` folder in `/config`.
- Keep the container non-root with a read-only root filesystem, no capabilities and `no-new-privileges`, as
  in the compose file. Publish 9180 on a loopback or private address only, or not at all when Prometheus
  shares Varken's Docker network.
- Leave `stream_details` off unless everyone who can read the metrics may see per-viewer data.

The reasons, and the known weaknesses, are in [security.md](security.md).

## Uninstalling

```sh
docker compose down
rm -rf config .env
```

For a bare install: `sudo systemctl disable --now varken`, remove `/etc/systemd/system/varken.service`,
`/opt/Varken` and the `varken` user. Remove the `varken` scrape job from Prometheus; what it already scraped
stays there until Prometheus' retention removes it. Varken changed nothing in the services it read; revoke
the API keys and MaxMind license key you made for it.
