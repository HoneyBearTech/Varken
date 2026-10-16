# Upgrading

Only the latest release and `main` get fixes ([SUPPORT.md](../SUPPORT.md)), so upgrade when a new one
comes out. Every release's notes (and [CHANGELOG.md](../CHANGELOG.md)) list what changed and anything you
need to do first.

## What's kept, and what to back up

Varken itself holds very little:

- **`varken.ini`** in the data folder (and, with compose, **`.env`**): your settings and secrets. Upgrades
  never change them, unless a key is missing, which Varken then fills in from the example
  ([configuration.md](configuration.md#how-values-are-read)).
- **`GeoLite2-City.mmdb`**: downloaded again when missing, so it needn't be backed up.
- **`logs/`**: only history.

The metrics Varken serves are stored by your Prometheus, which keeps them across Varken upgrades; Varken
itself holds only the last run of each job, in memory.

```sh
cp config/varken.ini config/varken.ini.backup     # or data/varken.ini for a bare install
cp .env .env.backup                               # compose only
```

## From upstream Varken 1.7.x (boerderij/varken) to 2.0.0

2.0.0 is the first release of this fork. Your `varken.ini` and your `VRKN_*` variables carry over, except
the InfluxDB ones, which are no longer used. On the first start Varken adds the `[prometheus]` section to
`varken.ini` with its defaults, which rewrites the file and drops its comments; it needs write access to it.
What changes:

1. **Varken no longer writes to InfluxDB.** It serves its data as Prometheus metrics on port 9180 instead,
   and upstream's Grafana dashboards, which query InfluxDB, stop updating at the upgrade. Before you start
   2.0.0:

   - **Decide what to do with the data already in InfluxDB.** It stays there; Varken never deletes it. Keep
     the InfluxDB running for as long as you want to look at the history (its retention policy, 30 days by
     default, still expires it), or back it up first with InfluxDB's own tools, for example
     `influxd backup -portable -db varken <dir>` inside the InfluxDB container
     ([InfluxDB 1.x backup and restore](https://docs.influxdata.com/influxdb/v1/administration/backup_and_restore/)).
     Once you don't need it, remove the InfluxDB service (and upstream's Grafana service, if you used its
     compose file); Varken needs neither.
   - **Set up Prometheus to scrape Varken.** Add a scrape job for `varken:9180` (same Docker network) or
     `<host>:9180` (published port), publish or allow port 9180 accordingly, and use that Prometheus as a
     Grafana data source ([installing.md](installing.md#scraping-it-with-prometheus)). Build dashboards on the
     [metrics](interfaces.md#output-prometheus-metrics); they replace the InfluxDB measurements, which have
     no direct equivalent. In the maintainer's setup, [Argus](https://github.com/HoneyBearTech/Argus) provides
     Prometheus and Grafana.
   - **The `[influxdb]` section can be deleted or left.** Varken ignores it, and any `VRKN_INFLUXDB_*`
     variables. Keep a copy if you might [roll back](#rolling-back) to 1.7.7, which needs it.
   - **The Tautulli history import and `utilities/` are gone**: `historical_tautulli_import.py` and
     `grafana_build.py`, which imported upstream's InfluxDB dashboard, are no longer in the repository or the
     image.

2. **The image name.** `boerderij/varken` (Docker Hub, and its GHCR and Quay copies) is replaced by
   `ghcr.io/honeybeartech/varken`. Change `image:` in your compose file or template, and pin a version:
   `ghcr.io/honeybeartech/varken:2.0.0`. You can [verify it](verifying-releases.md) first.
3. **The container no longer runs as root.** It runs as uid/gid 1000:1000, so a config folder written by
   the old root container isn't writable any more. Fix the ownership once, before starting 2.0.0:

   ```sh
   sudo chown -R 1000:1000 /path/to/varken/config
   ```

   Use another uid:gid if you run the container with `user:` (Unraid's template uses `99:100`). A named
   volume the old container wrote to needs the same fix, run as root inside a throwaway container:

   ```sh
   docker run --rm --user 0 --entrypoint chown -v <volume>:/config \
     ghcr.io/honeybeartech/varken:2.0.0 -R 1000:1000 /config
   ```

   Bind-mounted host directories (recommended, such as `CONFIG_ROOT/varken/config`) always need the `chown`.
   A new named volume needs none, since the image's `/config` belongs to 1000:1000, but `docker volume prune`
   deletes named volumes whose container is stopped.
4. **32-bit ARM (linux/arm/v7) images are no longer built.** Images exist for linux/amd64 and linux/arm64.
   On a 32-bit ARM device, move to a 64-bit OS or use a bare-Python install.
5. **Bare-Python installs need Python 3.14** and a fresh virtual environment with the hash-pinned
   requirements. Point the checkout at this repository and move to the release:

   ```sh
   cd /opt/Varken
   sudo git remote set-url origin https://github.com/HoneyBearTech/Varken.git
   sudo git fetch --tags && sudo git checkout v2.0.0
   sudo rm -rf varken-venv && sudo python3.14 -m venv varken-venv
   sudo varken-venv/bin/pip install --require-hashes --no-deps -r requirements.txt
   sudo systemctl restart varken
   ```

   [installing.md](installing.md#option-4-bare-python) has the rest, including systemd hardening.
6. **Rotate secrets that older versions may have exposed.** Up to 1.7.7, Varken could send the Tautulli API
   key to a third-party service over plain HTTP, and logged secrets set through environment variables
   unmasked ([security.md](security.md#fixed-in-200)). Regenerate the Tautulli API key if in doubt, and any
   secret that is in logs you kept or shared.

## Between 2.x releases

With compose: set the new `VARKEN_VERSION` in `.env`, optionally [verify the image](verifying-releases.md),
`git pull` (the compose file and `.env.example` can change between releases; compare your `.env` with the
new `.env.example`), then:

```sh
docker compose pull varken && docker compose up -d
docker compose logs -f varken
```

For a bare install: `git fetch --tags && git checkout vX.Y.Z`, reinstall `requirements.txt` with
`--require-hashes --no-deps` (it may have changed), and restart the service.

### 2.x to 3.0.0

- **GeoIP: set `maxmind_account_id`** (or `VRKN_GLOBAL_MAXMIND_ACCOUNT_ID`) if you haven't: with only the
  license key, 3.0.0 turns GeoIP off and logs `GeoIP needs your MaxMind account ID`.
- **TLS:** new configs check certificates. Your `varken.ini` keeps its `verify_ssl` values; Varken now logs a
  warning at start-up for every server on HTTPS without certificate checks. Turn them on where you can.
- **Logs:** masked secrets are `********`, with nothing of them kept. Anything that matched the old
  `********abcde` form needs changing.
- **Seerr** is new and off by default: set `seerr_server_ids` and the `[seerr-N]` section to use it. Your
  `varken.ini` gets the keys on the first start.
- 3.0.0 includes 2.3.0 (request timeouts, INFO logging by default): see below.

### 2.2.x to 2.3.0

- **The log is quieter:** Varken logs at INFO unless you set `DEBUG=true` (or pass `-D`). If you set
  `DEBUG=false` before, you can drop it.
- A service that takes more than 30 seconds to answer a request now fails that run instead of waiting forever.

### 2.1.x to 2.2.0

- **GeoIP users: add your MaxMind account ID** (`maxmind_account_id` or `VRKN_GLOBAL_MAXMIND_ACCOUNT_ID`; it's
  on MaxMind's account portal). Without it GeoIP keeps working through the old download URL, with a warning
  in the log. Your `varken.ini` gets the key, empty, on the first start.
- A failed GeoLite2 download no longer stops Varken.

### 2.0.x to 2.1.0

- **With the example compose file:** it now keeps Varken's data in `CONFIG_ROOT/varken/config` and needs
  `CONFIG_ROOT` in `.env` (it stops with "set CONFIG_ROOT in .env" otherwise); `VARKEN_CONFIG_DIR` is gone.
  Move your data folder there (2.0.0's default was `./config`), keep it owned by uid 1000, and set
  `CONFIG_ROOT`: for example `mkdir -p /srv/config/varken && mv ./config /srv/config/varken/config` with
  `CONFIG_ROOT=/srv/config`. Your own compose file needs no change.
- **Sonarr and Radarr 4 or later.** The Sonarr and Radarr modules now read `/api/v3`. Older Sonarr and Radarr
  releases aren't supported; with one, those jobs log an error and `varken_job_up` is `0`.
- New metrics only: nothing is renamed or removed. With `stream_details = true`, `varken_tautulli_session_info`
  gains labels (including the viewer's coordinates), and `varken_ombi_request_info` names each requester;
  check that's acceptable for everyone who can query your Prometheus ([security](security.md)).
- `varken_tautulli_session_info`'s `location` is now empty, not `👽`, for a viewer who can't be placed. Update
  any query that matched `👽`.

## Rolling back

Set the previous version (or check out the previous tag), restore `varken.ini` and `.env` from the backup,
and start it again. Going back to upstream 1.7.7 works too: its root-running container can still write to a
folder owned by uid 1000, and it writes to InfluxDB again, so it needs the `[influxdb]` section (restore it
from the backup if you deleted it) and a running InfluxDB. Nothing is written to InfluxDB while 2.0.0 runs,
so that gap stays in its data. Varken never changed anything in the services it reads, so there is nothing
to roll back there.
