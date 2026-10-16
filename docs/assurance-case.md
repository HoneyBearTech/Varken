# Assurance case

This document argues that Varken meets its [security requirements](security.md), and says plainly where it
doesn't yet. It describes the threat model, identifies the trust boundaries, shows how secure design
principles are applied, and lists how common weaknesses are countered, with pointers to the code and checks
that back each claim. How Varken works is in [architecture.md](architecture.md).

The top-level claim is:

> **Deployed as documented, Varken collects data from the services its operator configures and serves it
> to Prometheus without changing anything in those services, without executing
> anything it receives, without writing outside its data folder, without exposing its credentials, and with
> releases whose origin can be verified, within the limits and known weaknesses stated in
> [security.md](security.md).**

It rests on four arguments: the threat model is understood (1), every trust boundary is mediated or
explicitly accepted (2), the design follows secure design principles (3), and the implementation counters
common weaknesses or records the ones it doesn't yet (4), verified continuously (5).

## 1. Threat model

**Assets**, most valuable first: the credentials Varken holds (API keys for Tautulli and the \*arr apps,
which can change or delete media there; a UniFi controller login; the MaxMind license key); the viewing data it collects (who watched what, when, on which device and from roughly
where); the integrity of the services it reads; the integrity of the published image and release files;
and the host it runs on.

**Actors and what they may try:**

| Actor | Trusted with | Threats considered |
| --- | --- | --- |
| Operator | Everything in the config and the host | Mistakes: plain HTTP or unverified TLS across an untrusted network, debug logs shared in a support request, a world-readable `varken.ini`. |
| Media services and UniFi controller | Answering read requests | A compromised or buggy service returning malformed, huge or hostile JSON: unexpected types, values that create unbounded metric series, strings aimed at logs or dashboards; a service that never answers. |
| MaxMind download | Serving the GeoLite2 archive | A tampered archive with path-traversal entries, links or a huge file. |
| Public-address service (`api.ipify.org`) | Nothing | Returning a false address (it is sent nothing but the request itself). Not contacted with GeoIP off. |
| Anyone who can reach `/metrics` (Prometheus, or anything else on that network) | Reading the metrics | Reading viewing activity (aggregate by default, per viewer with `stream_details`); flooding the endpoint with requests. |
| Network attacker | Nothing | Intercepting credentials and data on unencrypted or unverified connections; tampering with responses. |
| Viewers | Nothing (they never talk to Varken) | Their privacy is an asset, not a threat: the data about them must not leak beyond the operator's stack. |
| Contributor | Proposing changes | A pull request that adds a write request, leaks a credential, or a malicious workflow change. |
| Supply chain | Nothing beyond what's pinned | A tampered base image, Python package or GitHub Action; a tampered Varken image between registry and user. |

**Out of scope** (see [security.md](security.md#what-varken-does-not-protect-against)): anyone with write
access to the host, its Docker daemon, the data folder or the container's environment; the access control of
Prometheus and Grafana; vulnerabilities in the services Varken reads, in Python or in the base image (handled by
updating them, [dependencies.md](dependencies.md)).

## 2. Trust boundaries

| # | Boundary | What crosses it | How it is mediated |
| --- | --- | --- | --- |
| B1 | Operator → Varken | `varken.ini`, `VRKN_*` (and files named by `VRKN_*_FILE`) and `DATA_FOLDER`/`DEBUG`/`LOG_TO_FILE` environment variables | Trusted input. A `_FILE` that can't be read, or is set together with its variable, stops Varken. Read with `ConfigParser(interpolation=None)`; URLs must match a host[:port][/path] pattern and are combined with a scheme chosen by `ssl`, so a config value can't pick another scheme; `fallback_ip` must be a public IPv4 address; `[prometheus]` `bind` must be an IP address and `port` 1 to 65535, or Varken stops; numbers must parse, or the server is skipped ([`iniparser.py`](../varken/iniparser.py)). |
| B2 | Services → Varken | JSON over HTTP(S) | `GET` only (UniFi: login `POST`), through `connection_handler()` ([`helpers.py`](../varken/helpers.py)); responses parsed as JSON by requests; Tautulli, Ombi and SickChill replies are mapped onto fixed `NamedTuple` structures ([`structures.py`](../varken/structures.py)), so an unknown field is rejected (logged, item skipped), while Sonarr, Radarr and Lidarr replies (since 2.1.0) are read field by field and a reply of the wrong shape fails the run; values become metric values and labels, as data. TLS verification only with `verify_ssl = true` (**off by default: a known weakness**). A 10 s connect and 30 s read timeout on every request (since 2.3.0). |
| B3 | Varken → services | API keys, UniFi credentials | Each credential is attached only to its own service's session (header for Sonarr, Radarr, Lidarr, Ombi; query or path where Tautulli's and SickChill's APIs require it). The public-address lookup is a separate request with no credentials; before 2.0.0 it reused the Tautulli session and leaked its key ([fixed](security.md#fixed-in-200)). |
| B4 | MaxMind → data folder | GeoLite2 tar.gz over HTTPS | Crossed only with a license key set (GeoIP on). Fixed HTTPS URL with certificate verification; only the member named `GeoLite2-City.mmdb` is extracted, under its base name, with the `data` extraction filter (no links, devices or paths outside the folder) ([`helpers.py`](../varken/helpers.py) `GeoIPHandler.download`). With `maxmind_account_id` set, the account ID and license key travel as HTTP Basic auth, and requests drops them on the redirect to MaxMind's storage; without it, the license key is a query parameter (**known weakness**). A failed download leaves Varken running without locations. |
| B5 | Varken → host | Files, logs | The image runs as uid 1000 and writes only to `/config`; it can run with a read-only root filesystem and no capabilities. Logs mask configured secrets (partially: **known weakness**); `LOG_TO_FILE=false` keeps them out of the data folder. The only port it opens is `/metrics` (B8). |
| B6 | Contributor → repository | Pull requests | Changes reach `main` only through pull requests that pass the required "Checks + tests" job; DCO sign-off; gitleaks over the full history in CI; workflows from forks get read-only tokens and no secrets; CodeQL analyses the code and workflows. |
| B7 | Upstream → build → GHCR → user | Base image, packages, Actions, the published image | Base image pinned by version and digest, Python packages by hash, Actions by commit SHA; the release workflow signs the image keylessly (identity: the workflow on the tag), attaches SBOM and provenance, and signs the release checksums; users verify with cosign ([verifying-releases.md](verifying-releases.md)). |
| B8 | Network → Varken (`/metrics`) | HTTP requests to `bind`:`port`; the metrics in reply | Always on: it is Varken's output. Served by prometheus_client's HTTP server, which reads only the request path, query (`name[]` filters) and `Accept` and `Accept-Encoding` headers; answers are built from in-memory snapshots of the last run of each job ([`metrics.py`](../varken/metrics.py)), so a request can't reach a service, a file or the configuration. Metrics hold no credentials or URLs; per-viewer labels only with `stream_details = true`; viewer IP addresses never (the points don't contain them; `tests/test_metrics.py` checks it). **No authentication, TLS or rate limit**: accepted, and mediated by the deployment (a private network, or `bind = 127.0.0.1`) ([security.md](security.md#the-metrics-endpoint)). |

### Attack surface

Varken's untrusted inputs are the JSON responses of the services it reads, the GeoLite2 archive and the
`api.ipify.org` answer (both only with GeoIP on), and HTTP requests to its one listening socket, `/metrics`
(B8). It listens on nothing else.

## 3. Secure design principles

| Principle | How Varken applies it |
| --- | --- |
| Economy of mechanism | A single process with a small set of dependencies; one function, `connection_handler()`, sends every service request; one `Metrics` object takes every point and serves the metrics built from them. |
| Fail-safe defaults | Replies of an unexpected shape fail the run rather than being guessed at; an invalid URL, private `fallback_ip` or invalid `[prometheus]` address stops Varken; a failed job records nothing, and its metrics are dropped rather than left stale. The per-viewer metrics are off by default, and without a MaxMind key no location lookups or GeoIP requests happen. Debug logging is off by default (since 2.3.0). **Not yet**: `verify_ssl` defaults to the unsafe side (roadmap). |
| Complete mediation | Every service request goes through `connection_handler()`, every config value (including `_FILE` secrets) through `INIParser`, and every point through `Metrics.write_points`. |
| Open design | Everything is public and documented; security rests on the operator's credentials and file permissions, not on secrecy of the code. |
| Separation of privilege | Publishing a release needs both a signed tag pushed by the maintainer and the release workflow's identity; changes need a pull request and a passing check. |
| Least privilege | Only read requests; the metrics endpoint can only read snapshots, never trigger a request; dedicated read-only accounts recommended; the container runs non-root, needs no capabilities and only `/config` writable; workflows default to `contents: read`. |
| Least common mechanism | Varken shares nothing with the services it reads but their APIs; each server gets its own HTTP session. |
| Psychological acceptability | One config file (or environment variables) with an example for every key; the secure container settings are a few lines of compose ([security.md](security.md#the-container)). |

## 4. Countering common weaknesses

Status: **Countered**, **Partly** (countered with gaps), or **Open** (known, on the [roadmap](roadmap.md)).

| Weakness | Status | Countermeasure or gap | Evidence |
| --- | --- | --- | --- |
| Path traversal / link following when extracting an archive (CWE-22, CWE-59) | Countered | Only the `.mmdb` member, renamed to its base name, extracted with `filter="data"` | `GeoIPHandler.download` in [`helpers.py`](../varken/helpers.py) |
| Deserialization of untrusted data (CWE-502) | Countered | JSON only (no pickle, YAML or `eval`); config via `ConfigParser` without interpolation | [`varken/`](../varken/); CodeQL |
| OS command injection (CWE-78) and code injection (CWE-94) | Countered | Varken runs no subprocesses and evaluates nothing | [`varken/`](../varken/); CodeQL |
| Injection into the metrics output (CWE-74) | Countered | Values from responses become label values, which prometheus_client's text encoder escapes; metric and label names are fixed in the code | [`metrics.py`](../varken/metrics.py); `promtool check metrics` in CI |
| SSRF / unexpected URL schemes (CWE-918) | Countered | Service URLs come from the trusted config, can't carry a scheme, and get `http://` or `https://` from `ssl`; response data never chooses a URL | `url_check` in [`iniparser.py`](../varken/iniparser.py) |
| Improper certificate validation (CWE-295) | Open | `verify_ssl` defaults to false and the warning is silenced | [security.md](security.md#known-weaknesses); roadmap: default true |
| Cleartext transmission of sensitive information (CWE-319) | Open | `ssl` defaults to false for every service (the public-address lookup moved to HTTPS in 2.0.0) | [security.md](security.md#transport) |
| Credentials sent to the wrong party (CWE-201, CWE-522) | Countered (fixed in 2.0.0) | Each key is attached only to its own service's session; the public-address lookup is a separate request without credentials. Before 2.0.0 it carried the Tautulli API key to `ip.42.pl` | `PUBLIC_IP_URL` and `requests_get` in [`tautulli.py`](../varken/tautulli.py); [security.md](security.md#fixed-in-200) |
| Sensitive information in a query string (CWE-598) | Partly | Sonarr, Radarr, Lidarr and Ombi keys go in headers; Tautulli's and SickChill's APIs only accept keys in the URL; the MaxMind key uses Basic auth with `maxmind_account_id`, and is in the URL only without it | set `maxmind_account_id` |
| Sensitive information in log files (CWE-532) | Partly | `BlacklistFilter` masks configured secrets from `varken.ini` and from `VRKN_*` variables, including the MaxMind key, in every log argument (fixed in 2.0.0: environment values and the MaxMind key used to be missed). It keeps the last five characters, and debug logging (on by default) records every request URL | [`varkenlogger.py`](../varken/varkenlogger.py), `config_blacklist` in [`iniparser.py`](../varken/iniparser.py); roadmap: INFO default, full masking |
| Missing authentication for the metrics endpoint (CWE-306) and cleartext metrics (CWE-319) | Partly | Read-only; no credentials in it; bind address configurable (`127.0.0.1` for the same host); documented to stay on a private network. It has no authentication or TLS of its own | [`metrics.py`](../varken/metrics.py), [security.md](security.md#the-metrics-endpoint) |
| Exposure of personal information to an unauthorized actor (CWE-359) | Partly | Metrics carry no viewer or requester identity by default; `stream_details` is an explicit opt-in; viewer IP addresses are never exported; GeoIP can be left off. Prometheus and Grafana still hold viewing data for whoever can read them | `test_tautulli_activity_keeps_viewers_out_by_default` and `test_tautulli_stream_details_when_enabled` in [`tests/test_metrics.py`](../tests/test_metrics.py); `test_ombi_requests_keep_the_requester_out_by_default` in [`tests/test_arrs.py`](../tests/test_arrs.py) |
| Improper output neutralization for logs (CWE-117) | Open | Strings from responses are logged as received; a hostile service could forge log lines | |
| Hard-coded or committed credentials (CWE-798, CWE-312) | Countered | No credentials in code; examples use placeholders; `data/varken.ini` is gitignored; gitleaks scans the history in CI; secrets can come from Docker or compose secret files (`VRKN_*_FILE`) instead of the environment | [`.gitignore`](../.gitignore), [`ci.yml`](../.github/workflows/ci.yml) |
| Uncontrolled resource consumption (CWE-400) | Partly | Sonarr, Lidarr's queue and SickChill requests ask for at most 1,000 items; metrics series are bounded by the current sessions and libraries; every request has a 10 s connect and 30 s read timeout (since 2.3.0), so a job's thread can't hang for good; but there is a thread per job run, no limit on response size, and no rate limit on the metrics endpoint | |
| Execution with unnecessary privileges (CWE-250) | Countered | Non-root image (uid 1000), no capabilities needed, read-only root filesystem supported | [`Dockerfile`](../Dockerfile), [security.md](security.md#the-container) |
| Inclusion of functionality from an untrusted source (CWE-829, CWE-494) | Countered | Digest-pinned base image, hash-pinned packages, SHA-pinned Actions; signed releases with provenance | [`Dockerfile`](../Dockerfile), [`requirements.txt`](../requirements.txt), the workflows; OpenSSF Scorecard |
| Injection into CI scripts (CWE-78, CWE-94) | Countered | Untrusted values reach `run:` scripts only through `env:`; no `pull_request_target` | actionlint and shellcheck in CI; CodeQL for Actions |
| Use of components with known vulnerabilities (CWE-1395) | Countered | pip-audit (OSV) in CI, Dependabot, dependency review and a weekly Trivy image scan; the archived `influxdb` client was removed in 2.0.0 | [dependencies.md](dependencies.md) |

## 5. Verification evidence

On every push and pull request, CI ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) runs ruff
(including the bandit security rules), yamllint, actionlint with shellcheck, hadolint, gitleaks over the full
history, pip-audit against the pinned requirements, the offline unit tests with a coverage floor (including the metrics tests in
[`tests/test_metrics.py`](../tests/test_metrics.py)), Prometheus' `promtool check metrics` on a sample scrape
with every metric (`python -m tests.sample_metrics`), and an image build. CodeQL analyses the
Python code and the workflows on every change and weekly; dependency review and a DCO check run on every
pull request; Trivy scans the image weekly; OpenSSF Scorecard scores the repository weekly. Releases are
signed and carry an SBOM and provenance.

This document is reviewed when the threat model changes: a new input or output (it was for the
Prometheus endpoint, boundary B8), a new kind of credential, any write request to a service, any code path
that writes outside the data folder, or a change to how releases are built. When an **Open** item is fixed, its row and
[security.md](security.md#known-weaknesses) change in the same pull request.
