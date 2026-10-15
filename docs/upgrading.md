# Upgrading

Only the latest release and `master` get fixes ([SUPPORT.md](../SUPPORT.md)), so upgrade when a new one
comes out. Every release's notes (and [CHANGELOG.md](../CHANGELOG.md)) list what changed and anything you
need to do first.

## What's kept, and what to back up

Varken itself holds very little:

- **`varken.ini`** in the data folder (and, with compose, **`.env`**): your settings and secrets. Upgrades
  never change them, unless a key is missing, which Varken then fills in from the example
  ([configuration.md](configuration.md#how-values-are-read)).
- **`GeoLite2-City.mmdb`**: downloaded again when missing, so it needn't be backed up.
- **`logs/`**: only history.

The data Varken collects lives in **InfluxDB**, in the `varken` database. Back that up with InfluxDB's own
tools before a major upgrade, for example `influxd backup -portable -db varken <dir>` inside the InfluxDB
container ([InfluxDB 1.x backup and restore](https://docs.influxdata.com/influxdb/v1/administration/backup_and_restore/)).

```sh
cp config/varken.ini config/varken.ini.backup     # or data/varken.ini for a bare install
cp .env .env.backup                               # compose only
```

## From upstream Varken 1.7.x (boerderij/varken) to 2.0.0

2.0.0 is the first release of this fork. Your `varken.ini`, your `VRKN_*` variables and the data in
InfluxDB carry over unchanged: the settings and the measurements Varken writes are the same as in 1.7.7, so
existing dashboards keep working. What changes:

1. **The image name.** `boerderij/varken` (Docker Hub, and its GHCR and Quay copies) is replaced by
   `ghcr.io/honeybeartech/varken`. Change `image:` in your compose file or template, and pin a version:
   `ghcr.io/honeybeartech/varken:2.0.0`. You can [verify it](verifying-releases.md) first.
2. **The container no longer runs as root.** It runs as uid/gid 1000:1000, so a config folder written by
   the old root container isn't writable any more. Fix the ownership once, before starting 2.0.0:

   ```sh
   sudo chown -R 1000:1000 /path/to/varken/config
   ```

   Use another uid:gid if you run the container with `user:` (Unraid's template uses `99:100`).
3. **32-bit ARM (linux/arm/v7) images are no longer built.** Images exist for linux/amd64 and linux/arm64.
   On a 32-bit ARM device, move to a 64-bit OS or use a bare-Python install.
4. **Bare-Python installs need Python 3.14** and a fresh virtual environment with the hash-pinned
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
5. **Rotate secrets that older versions may have exposed.** Up to 1.7.7, Varken could send the Tautulli API
   key to a third-party service over plain HTTP, and logged secrets set through environment variables
   unmasked ([security.md](security.md#fixed-in-200)). Regenerate the Tautulli API key if in doubt, and any
   secret that is in logs you kept or shared.

Two related changes are worth knowing about:

- Upstream's example compose file used the untagged `influxdb` image, which now pulls InfluxDB 2 or later. Varken
  needs InfluxDB 1.x: pin a 1.x tag (the example compose file uses `influxdb:1.12.4`).
- Upstream's Grafana dashboard uses the Worldmap and old Pie Chart panels, which Grafana 12 and later
  removed. If you upgrade Grafana too, replace those panels with Geomap and Pie chart. Varken's data
  doesn't change.

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

## Rolling back

Set the previous version (or check out the previous tag), restore `varken.ini` and `.env` from the backup,
and start it again. Going back to upstream 1.7.7 works too: its root-running container can still write to a
folder owned by uid 1000. Data written to InfluxDB in the meantime stays there; restore the InfluxDB backup
only if the new version wrote something you need to undo. Varken never changed anything in the services
it reads, so there is nothing to roll back there.
