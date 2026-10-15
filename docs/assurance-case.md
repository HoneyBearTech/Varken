# Assurance case

This document argues that Varken meets its [security requirements](security.md), and says plainly where it
doesn't yet. It describes the threat model, identifies the trust boundaries, shows how secure design
principles are applied, and lists how common weaknesses are countered, with pointers to the code and checks
that back each claim. How Varken works is in [architecture.md](architecture.md).

The top-level claim is:

> **Deployed as documented, Varken collects data from the services its operator configures and writes it
> to InfluxDB without changing anything in those services, without executing anything it receives, without
> writing outside its data folder, and with releases whose origin can be verified, within the limits and
> known weaknesses stated in [security.md](security.md).**

It rests on four arguments: the threat model is understood (1), every trust boundary is mediated or
explicitly accepted (2), the design follows secure design principles (3), and the implementation counters
common weaknesses or records the ones it doesn't yet (4), verified continuously (5).

## 1. Threat model

**Assets**, most valuable first: the credentials Varken holds (API keys for Tautulli and the \*arr apps,
which can change or delete media there; the InfluxDB password; a UniFi controller login; the MaxMind
license key); the viewing data it collects (who watched what, when, on which device and from roughly
where); the integrity of the services it reads; the integrity of the published image and release files;
and the host it runs on.

**Actors and what they may try:**

| Actor | Trusted with | Threats considered |
| --- | --- | --- |
| Operator | Everything in the config and the host | Mistakes: plain HTTP or unverified TLS across an untrusted network, debug logs shared in a support request, a world-readable `varken.ini`. |
| Media services and UniFi controller | Answering read requests | A compromised or buggy service returning malformed, huge or hostile JSON: unexpected types, values that create unbounded InfluxDB series, strings aimed at logs or dashboards; a service that never answers. |
| MaxMind download | Serving the GeoLite2 archive | A tampered archive with path-traversal entries, links or a huge file. |
| Public-address service (`api.ipify.org`) | Nothing | Returning a false address (it is sent nothing but the request itself). |
| InfluxDB | Storing points | Rejecting writes or being unreachable; an InfluxDB reachable by others exposing the collected data. |
| Network attacker | Nothing | Intercepting credentials and data on unencrypted or unverified connections; tampering with responses. |
| Viewers | Nothing (they never talk to Varken) | Their privacy is an asset, not a threat: the data about them must not leak beyond the operator's stack. |
| Contributor | Proposing changes | A pull request that adds a write request, leaks a credential, or a malicious workflow change. |
| Supply chain | Nothing beyond what's pinned | A tampered base image, Python package or GitHub Action; a tampered Varken image between registry and user. |

**Out of scope** (see [security.md](security.md#what-varken-does-not-protect-against)): anyone with write
access to the host, its Docker daemon, the data folder or the container's environment; the access control of
InfluxDB and Grafana; vulnerabilities in the services Varken reads, in Python or in the base image (handled by
updating them, [dependencies.md](dependencies.md)).

## 2. Trust boundaries

| # | Boundary | What crosses it | How it is mediated |
| --- | --- | --- | --- |
| B1 | Operator → Varken | `varken.ini`, `VRKN_*` and `DATA_FOLDER`/`DEBUG` environment variables | Trusted input. Read with `ConfigParser(interpolation=None)`; URLs must match a host[:port][/path] pattern and are combined with a scheme chosen by `ssl`, so a config value can't pick another scheme; `fallback_ip` must be a public IPv4 address; numbers must parse, or the server is skipped ([`iniparser.py`](../varken/iniparser.py)). |
| B2 | Services → Varken | JSON over HTTP(S) | `GET` only (UniFi: login `POST`), through `connection_handler()` ([`helpers.py`](../varken/helpers.py)); responses parsed as JSON by requests and mapped onto fixed `NamedTuple` structures ([`structures.py`](../varken/structures.py)), so an unknown field is rejected (logged, item skipped) rather than trusted; values go to InfluxDB as data. TLS verification only with `verify_ssl = true` (**off by default: a known weakness**). No timeouts (**known weakness**). |
| B3 | Varken → services | API keys, UniFi credentials | Each credential is attached only to its own service's session (header for Sonarr, Radarr, Lidarr, Ombi; query or path where Tautulli's and SickChill's APIs require it). The public-address lookup is a separate request with no credentials; before 2.0.0 it reused the Tautulli session and leaked its key ([fixed](security.md#fixed-in-200)). |
| B4 | MaxMind → data folder | GeoLite2 tar.gz over HTTPS | Fixed HTTPS URL with certificate verification; only the member named `GeoLite2-City.mmdb` is extracted, under its base name, with the `data` extraction filter (no links, devices or paths outside the folder) ([`helpers.py`](../varken/helpers.py) `GeoIPHandler.download`). The license key travels as a query parameter (**known weakness**). |
| B5 | Varken → InfluxDB | Points, InfluxDB credentials | The configured host only; HTTPS and verification per `ssl`/`verify_ssl`. Writes go through the `influxdb` client's line-protocol encoding (no query strings built from data). |
| B6 | Varken → host | Files, logs | The image runs as uid 1000 and writes only to `/config`; it can run with a read-only root filesystem and no capabilities. Logs mask configured secrets (partially: **known weakness**). No ports are opened. |
| B7 | Contributor → repository | Pull requests | Changes reach `master` only through pull requests that pass the required "Checks + tests" job; DCO sign-off; gitleaks over the full history in CI; workflows from forks get read-only tokens and no secrets; CodeQL analyses the code and workflows. |
| B8 | Upstream → build → GHCR → user | Base image, packages, Actions, the published image | Base image pinned by version and digest, Python packages by hash, Actions by commit SHA; the release workflow signs the image keylessly (identity: the workflow on the tag), attaches SBOM and provenance, and signs the release checksums; users verify with cosign ([verifying-releases.md](verifying-releases.md)). |

### Attack surface

Varken listens on nothing today. Its untrusted inputs are the JSON responses of the services it reads, the
GeoLite2 archive, the `api.ipify.org` answer, and InfluxDB's responses. The planned `/metrics` endpoint will be
its first listening socket; this document will be updated with a new boundary (Prometheus → Varken,
read-only, no secrets in metrics) before it ships.

## 3. Secure design principles

| Principle | How Varken applies it |
| --- | --- |
| Economy of mechanism | A single process with a small set of dependencies; one function, `connection_handler()`, sends every service request; one writer talks to InfluxDB. |
| Fail-safe defaults | Unknown response fields are rejected, not guessed at; an invalid URL or private `fallback_ip` stops Varken; a failed job writes nothing. **Not yet**: `verify_ssl` and debug logging default to the unsafe side (roadmap). |
| Complete mediation | Every service request goes through `connection_handler()` and every config value through `INIParser`. |
| Open design | Everything is public and documented; security rests on the operator's credentials and file permissions, not on secrecy of the code. |
| Separation of privilege | Publishing a release needs both a signed tag pushed by the maintainer and the release workflow's identity; changes need a pull request and a passing check. |
| Least privilege | Only read requests; dedicated read-only accounts recommended; a non-admin InfluxDB user works once the database exists; the container runs non-root, needs no capabilities and only `/config` writable; workflows default to `contents: read`. |
| Least common mechanism | Varken shares nothing with the services it reads but their APIs; each server gets its own HTTP session. |
| Psychological acceptability | One config file (or environment variables) with an example for every key; the secure container settings are a few lines of compose ([security.md](security.md#the-container)). |

## 4. Countering common weaknesses

Status: **Countered**, **Partly** (countered with gaps), or **Open** (known, on the [roadmap](roadmap.md)).

| Weakness | Status | Countermeasure or gap | Evidence |
| --- | --- | --- | --- |
| Path traversal / link following when extracting an archive (CWE-22, CWE-59) | Countered | Only the `.mmdb` member, renamed to its base name, extracted with `filter="data"` | `GeoIPHandler.download` in [`helpers.py`](../varken/helpers.py) |
| Deserialization of untrusted data (CWE-502) | Countered | JSON only (no pickle, YAML or `eval`); config via `ConfigParser` without interpolation | [`varken/`](../varken/); CodeQL |
| OS command injection (CWE-78) and code injection (CWE-94) | Countered | Varken runs no subprocesses and evaluates nothing | [`varken/`](../varken/); CodeQL |
| Injection into InfluxDB (CWE-74) | Countered | Points are written through the client's line-protocol encoder; the only queries are fixed database and retention-policy statements | [`dbmanager.py`](../varken/dbmanager.py) |
| SSRF / unexpected URL schemes (CWE-918) | Countered | Service URLs come from the trusted config, can't carry a scheme, and get `http://` or `https://` from `ssl`; response data never chooses a URL | `url_check` in [`iniparser.py`](../varken/iniparser.py) |
| Improper certificate validation (CWE-295) | Open | `verify_ssl` defaults to false and the warning is silenced | [security.md](security.md#known-weaknesses); roadmap: default true |
| Cleartext transmission of sensitive information (CWE-319) | Open | `ssl` defaults to false for every service and InfluxDB (the public-address lookup moved to HTTPS in 2.0.0) | [security.md](security.md#transport) |
| Credentials sent to the wrong party (CWE-201, CWE-522) | Countered (fixed in 2.0.0) | Each key is attached only to its own service's session; the public-address lookup is a separate request without credentials. Before 2.0.0 it carried the Tautulli API key to `ip.42.pl` | `PUBLIC_IP_URL` and `requests_get` in [`tautulli.py`](../varken/tautulli.py); [security.md](security.md#fixed-in-200) |
| Sensitive information in a query string (CWE-598) | Partly | Sonarr, Radarr, Lidarr and Ombi keys go in headers; Tautulli's and SickChill's APIs only accept keys in the URL; the MaxMind key is in the URL | roadmap: MaxMind Basic auth |
| Sensitive information in log files (CWE-532) | Partly | `BlacklistFilter` masks configured secrets from `varken.ini` and from `VRKN_*` variables, including the MaxMind key, in every log argument (fixed in 2.0.0: environment values and the MaxMind key used to be missed). It keeps the last five characters, and debug logging (on by default) records full InfluxDB payloads, which are personal data | [`varkenlogger.py`](../varken/varkenlogger.py), `config_blacklist` in [`iniparser.py`](../varken/iniparser.py); roadmap: INFO default, full masking |
| Improper output neutralization for logs (CWE-117) | Open | Strings from responses are logged as received; a hostile service could forge log lines | |
| Hard-coded or committed credentials (CWE-798, CWE-312) | Countered | No credentials in code; examples use placeholders; `data/varken.ini` is gitignored; gitleaks scans the history in CI | [`.gitignore`](../.gitignore), [`ci.yml`](../.github/workflows/ci.yml) |
| Uncontrolled resource consumption (CWE-400) | Partly | Sonarr, Lidarr's queue and SickChill requests ask for at most 1,000 items; but there are no request timeouts, a thread per job run, and no limit on response size or on new InfluxDB series | roadmap: timeouts |
| Execution with unnecessary privileges (CWE-250) | Countered | Non-root image (uid 1000), no capabilities needed, read-only root filesystem supported | [`Dockerfile`](../Dockerfile), [security.md](security.md#the-container) |
| Use of a broken hash (CWE-328) | Not applicable | SHA-256 (MD5 before 2.0.0) builds the `hash` field that dashboards count distinct items by; it protects nothing | [`helpers.py`](../varken/helpers.py) `hashit` |
| Inclusion of functionality from an untrusted source (CWE-829, CWE-494) | Countered | Digest-pinned base image, hash-pinned packages, SHA-pinned Actions; signed releases with provenance | [`Dockerfile`](../Dockerfile), [`requirements.txt`](../requirements.txt), the workflows; OpenSSF Scorecard |
| Injection into CI scripts (CWE-78, CWE-94) | Countered | Untrusted values reach `run:` scripts only through `env:`; no `pull_request_target` | actionlint and shellcheck in CI; CodeQL for Actions |
| Use of components with known vulnerabilities (CWE-1395) | Partly | pip-audit (OSV) in CI, Dependabot, dependency review and a weekly Trivy image scan; but the `influxdb` client is archived and will get no fixes | [dependencies.md](dependencies.md); roadmap: replace it |

## 5. Verification evidence

On every push and pull request, CI ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) runs ruff
(including the bandit security rules), yamllint, actionlint with shellcheck, hadolint, gitleaks over the full history, pip-audit against the
pinned requirements, the offline unit tests with a coverage floor, and an image build. CodeQL analyses the
Python code and the workflows on every change and weekly; dependency review and a DCO check run on every
pull request; Trivy scans the image weekly; OpenSSF Scorecard scores the repository weekly. Releases are
signed and carry an SBOM and provenance.

This document is reviewed when the threat model changes: a new input or output (the Prometheus endpoint
first), a new kind of credential, any write request to a service, any code path that writes outside the
data folder, or a change to how releases are built. When an **Open** item is fixed, its row and
[security.md](security.md#known-weaknesses) change in the same pull request.
