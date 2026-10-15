# Security

Varken holds API keys for your media stack, your InfluxDB password and, with UniFi, a controller login, and
it records who watched what and from roughly where. This page states what it is designed to guarantee, how
to run it so those guarantees hold, and, honestly, where it falls short today. Why the guarantees hold is
argued in the [assurance case](assurance-case.md).

## Intended deployment

One Varken per home lab or small server, run by the person who also runs the services it reads, on the
same trusted network as those services and InfluxDB or Prometheus. It is not designed to be exposed to the
internet, and it doesn't need to be: it opens no ports unless you turn on the Prometheus output, and then
only its `/metrics` port, for a Prometheus on the same private network.

## What Varken is designed to guarantee

- **It only reads.** Every request to Tautulli, Sonarr, Radarr, Lidarr, Ombi and SickChill is a `GET`, and
  the UniFi module only logs in and reads device statistics. No code path changes anything in those
  services ([interfaces.md](interfaces.md#interfaces-varken-uses)).
- **Credentials go only to the service they belong to.** Each API key, password and the MaxMind license key
  is sent only to the host configured for it (and InfluxDB's only to InfluxDB). Varken sends no telemetry and
  contacts nothing you haven't configured, except, with GeoIP on, MaxMind for the database and, in one
  fallback case, `https://api.ipify.org` with no credentials. With GeoIP off (no MaxMind license key) it
  contacts neither ([interfaces.md](interfaces.md#interfaces-varken-uses)).
- **Metrics carry no secrets, and scrapes change nothing.** The `/metrics` endpoint serves gauges built from
  the last run of each job: no API keys, passwords, URLs or configuration. A scrape never calls a service
  ([interfaces.md](interfaces.md#output-prometheus-metrics)).
- **It writes only to its data folder and InfluxDB.** In the folder: `varken.ini` (when it creates or
  completes it), the GeoLite2 database and logs. The database archive is extracted with Python's `data`
  filter, so a tampered archive can't write elsewhere or create links.
- **Responses are data.** API responses are parsed as JSON and mapped onto fixed structures; nothing from
  them is executed. The config is read with `ConfigParser` without interpolation.
- **Viewer IP addresses aren't stored or exported.** The Tautulli module turns a viewer's public address
  into a city, region and coordinates (or nothing, with GeoIP off), and writes those; the address itself
  never reaches InfluxDB or the metrics. Who watches what is in the metrics only with `stream_details = true`.

## Running it securely

### Credentials

- Keep secrets in `varken.ini` with `chmod 600`, owned by the user Varken runs as (uid 1000 in the image),
  in `VRKN_*` environment variables passed from a file only that user can read (the compose setup's `.env`,
  which should be `chmod 600` too), or in Docker or compose secrets named by `VRKN_<SECTION>_<KEY>_FILE`
  ([configuration.md](configuration.md#values-from-files-_file)), which keeps them out of the container's
  configuration. Never commit them; the repository ignores `data/varken.ini` and `.env`.
- Give Varken its own credentials wherever the service allows it: a dedicated API key you can rotate alone, a
  read-only UniFi admin account, and an InfluxDB user that isn't an admin. For the latter, create the
  database yourself (`CREATE DATABASE varken`, and a retention policy if you want one) and grant the user
  `WRITE` on `varken`; Varken then skips creating it.
- Change the example InfluxDB credentials (`root`/`root`) and UniFi credentials (`ubnt`/`ubnt`). The
  example [`docker-compose.yml`](../docker-compose.yml) runs InfluxDB with authentication off (the InfluxDB
  1.x default) and publishes no InfluxDB port, so it is reachable only from the compose network; if you
  publish its port or share the network, turn on InfluxDB authentication first.
- If a key leaks, revoke and regenerate it in that service, then update `varken.ini` and restart Varken.

### Transport

Turn on `ssl = true` and `verify_ssl = true` for every service and for InfluxDB unless the traffic never
leaves a network you fully trust (for example, a private Docker network on one host). Both are **off** in
the example config, and with them off, API keys and passwords cross the network in clear text. Varken also
hides urllib3's warning about unverified certificates, so nothing in the log tells you.

### The container

The image runs as the unprivileged uid/gid 1000:1000 and only needs `/config` to be writable. The example
[`docker-compose.yml`](../docker-compose.yml) already runs it locked down; keep these settings if you write
your own:

```yaml
services:
  varken:
    image: ghcr.io/honeybeartech/varken:2.0.0
    user: "1000:1000"
    read_only: true
    tmpfs:
      - /tmp
    cap_drop: [ALL]
    security_opt:
      - no-new-privileges:true
    env_file: .env
    volumes:
      - ./config:/config
```

Don't publish any ports unless a Prometheus outside the container's network has to scrape Varken; then
publish only the metrics port, on a private or loopback address (`127.0.0.1:9180:9180`, as commented in the
compose file), never on all interfaces of an internet-facing host. Keep Grafana bound to `127.0.0.1` (the
compose default) unless a reverse proxy or firewall protects it. Pin a version (or a digest) rather than `latest`, and
[verify it](verifying-releases.md) before the first start. For a bare-Python install under systemd, see
[installing.md](installing.md#running-under-systemd) for the equivalent hardening.

### The metrics endpoint

With `[prometheus]` `enabled = true`, Varken listens on `bind`:`port` (default `0.0.0.0:9180`) and answers
anyone who can reach it. The endpoint has **no authentication and no TLS**, and no rate limit.

- Keep it on a private network: the Docker network Prometheus is on, or `bind = 127.0.0.1` when Prometheus
  runs on the same host outside a container. In a container, `0.0.0.0` is the container's own interface,
  reachable from its Docker networks and from any port you publish.
- Even without per-viewer metrics, it shows how many streams are running, on which platforms and in which
  quality, and what your libraries hold.
- Leave `stream_details = false` unless everyone who can reach the endpoint or query Prometheus may see who
  is watching what and from which city. Viewer IP addresses are never exported.
- Prometheus keeps what it scrapes for its own retention time; treat it like InfluxDB below.

### Logs and data

- Set `DEBUG=false` (in `.env` for the compose setup, or pass `-ND`). The debug log, on by default, records
  every point written to InfluxDB (usernames, titles, locations) and request URLs (with secrets masked).
- `LOG_TO_FILE=false` keeps the log out of the data folder, so it lives only where the container runtime or
  journald keeps stdout.
- Treat InfluxDB, Prometheus, Grafana and Varken's logs as personal data: Tautulli points show who watched
  what, when, on which device and, with GeoIP on, from roughly where. Restrict who can open those dashboards,
  and think before sharing a viewer account. The default retention policy keeps 30 days. Without a MaxMind
  license key, no locations are recorded at all.

## Releases

Released images and files are signed keylessly and carry an SBOM and build provenance; tags are signed.
Check them before you run them: [verifying-releases.md](verifying-releases.md).

## Known weaknesses

These are inherited from upstream Varken and are already public. Each has a planned fix on the
[roadmap](roadmap.md); until then, the workaround is listed. Weaknesses already fixed are listed
[below](#fixed-in-200).

| Weakness | Effect | Workaround today | Plan |
| --- | --- | --- | --- |
| `verify_ssl` defaults to `false`, and the insecure-request warning is silenced | A network attacker can intercept HTTPS traffic to a service without any warning | Set `verify_ssl = true` everywhere you use `ssl = true` | Default `true` (a breaking change, announced in the changelog) |
| No request timeouts | A service that accepts a connection but never answers ties up a thread per run, which can pile up | Keep services reachable; restart Varken if it stops writing | Add timeouts to every request |
| Debug logging is on by default | Logs hold personal viewing data and request URLs | `DEBUG=false` or `-ND` | Default INFO |
| Masked secrets keep their last five characters | A masked value is logged as `********` plus its last five characters, which narrows a guess for short secrets | Use long, random API keys and passwords; keep logs private | Mask completely |
| The MaxMind license key is sent as a URL query parameter | The key can end up in proxy or server logs along the way (the connection itself is HTTPS) | Use a license key dedicated to Varken | Use MaxMind's account ID + license key Basic-auth download |
| Archived InfluxDB client | The `influxdb` Python package gets no more fixes | none needed today | Replace it with direct HTTP writes of InfluxDB line protocol |
| Config rewrite | When keys are missing, Varken rewrites `varken.ini` with values from the example, dropping comments | Keep `varken.ini` complete | |

### Fixed in 2.0.0

Both were present in upstream Varken 1.7.7 and earlier. If you ran an affected version, regenerate the
credentials named below.

| Weakness | What happened | Fix |
| --- | --- | --- |
| Tautulli API key sent to a third party over plain HTTP | When neither a viewer's address nor `fallback_ip` was in the GeoLite2 database, Varken asked `http://ip.42.pl/raw` for the host's public address through the Tautulli session, which adds `?apikey=<Tautulli key>` to every request. `ip.42.pl`, and anyone on the path, could read the key. | The lookup now uses a separate request to `https://api.ipify.org` with no credentials and a 10-second timeout. Regenerate your Tautulli API key if the old version's log ever showed `Looked the public IP`, or if you can't tell. |
| Secrets from environment variables were not masked in logs | Only `varken.ini` values were masked, so API keys, usernames, passwords and URLs set through `VRKN_*` variables (the usual Docker setup), and the MaxMind license key from either source, could appear in the debug log, which is on by default, for example in Tautulli request URLs. Masking also skipped log arguments that weren't strings, such as exceptions. | Values of `VRKN_*` variables ending in `_APIKEY`, `_USERNAME`, `_PASSWORD`, `_URL` and `_MAXMIND_LICENSE_KEY`, and `maxmind_license_key` in `varken.ini`, are masked too, and every non-numeric log argument is masked through its text. Rotate any secret that may be in logs you kept or shared. |
## What Varken does not protect against

- **Anyone who can write to the host**, its Docker daemon, the data folder, `varken.ini` or the container's
  environment. Those are trusted inputs: whoever controls them controls where Varken sends its credentials.
- **The services it reads.** A compromised Tautulli or \*arr app can send Varken misleading data, very large
  answers, or values that flood InfluxDB with new series; Varken stores what they report.
- **Access to InfluxDB, Prometheus and Grafana.** Who can read the collected data is decided by their
  configuration, not Varken's.
- **Who can reach the metrics endpoint.** It has no authentication of its own; the network you put it on
  decides who can read it.
- **Unencrypted connections you configure.** With `ssl = false`, credentials and data cross the network in
  clear text.
- **Privacy decisions.** Varken records viewers' activity and approximate location as Tautulli reports it.
  Telling your viewers, and deciding how long to keep it, is up to you.

Report anything that breaks the guarantees above as described in [SECURITY.md](../SECURITY.md).
