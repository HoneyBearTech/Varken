# Dependencies and vulnerability management

How Varken chooses, obtains, tracks and updates what it's built from, and what happens when one of those
dependencies has a vulnerability.

At runtime Varken needs Python and five packages, declared in [`requirements.in`](../requirements.in):
[requests](https://requests.readthedocs.io/) (and urllib3) for HTTP,
[geoip2](https://github.com/maxmind/GeoIP2-python) to read the GeoLite2 database,
[prometheus_client](https://github.com/prometheus/client_python) for the `/metrics` endpoint,
[schedule](https://github.com/dbader/schedule) for the job timer and
[distro](https://github.com/python-distro/distro) to log the host's distribution.
The exact list, with every transitive package, is [`requirements.txt`](../requirements.txt). The
`influxdb` client, archived upstream, was removed with the InfluxDB output in 2.0.0, and with it msgpack,
pytz, six and python-dateutil. The rest are
the tools its checks and tests use and the GitHub Actions in its workflows.

## Choosing a dependency

A new dependency must:

- be open source under an OSI-approved license compatible with MIT and with redistribution in an image (see
  "Licenses" below);
- be actively maintained (releases in the last year, security issues answered) and widely used;
- be worth it: the standard library and the packages already used are preferred, and nothing is added for
  what a few lines of code can do. A runtime dependency in particular needs a reason in the pull request
  that adds it.

## Obtaining dependencies

All dependencies are fetched by standard tooling from their official registries, pinned so that a build
always gets the same bytes:

| Dependency | Declared in | Pinned by | Fetched by |
| --- | --- | --- | --- |
| Base image (`python:3.14-slim`, which brings Python and Debian) | [`Dockerfile`](../Dockerfile) | version tag and multi-arch digest | Docker / BuildKit |
| Runtime Python packages | [`requirements.in`](../requirements.in) → [`requirements.txt`](../requirements.txt) | exact version and SHA-256 hashes (`uv pip compile --generate-hashes`) | `pip install --require-hashes --no-deps` |
| Check and test tools (ruff, pytest, coverage, yamllint) | [`requirements-dev.in`](../requirements-dev.in) → [`requirements-dev.txt`](../requirements-dev.txt) | exact version and SHA-256 hashes | `pip install --require-hashes --no-deps` |
| Linters and scanners used only by CI (actionlint, hadolint, gitleaks, pip-audit, Trivy) | [`.github/workflows/`](../.github/workflows/) | version, and digest for container images | CI |
| GitHub Actions | [`.github/workflows/`](../.github/workflows/) | full commit SHA (version in a comment) | GitHub Actions |
| Images of the GitLab copy's pipeline (Python, Docker CLI, git, gitleaks, actionlint, hadolint, Prometheus) | [`.gitlab-ci.yml`](../.gitlab-ci.yml) | version tag and digest | GitLab Runner (Docker executor) |

Released images carry an SBOM listing every package in them ([verifying-releases.md](verifying-releases.md)).
How to regenerate the pins is in [CONTRIBUTING.md](../CONTRIBUTING.md#updating-pinned-dependencies).

The GeoLite2-City database is not a dependency of the code and isn't shipped: each installation downloads
it from MaxMind with its own license key, under MaxMind's GeoLite2 license.

## Tracking dependencies

- **Dependabot** ([`.github/dependabot.yml`](../.github/dependabot.yml)) checks weekly for new versions of
  the base image, the Python packages and the GitHub Actions, and opens a pull request for each. The example
  compose file only runs Varken's own image, so it has no entry. The maintainer reviews and merges them by
  hand; nothing merges without "Checks + tests" passing.
- **Dependency review** ([`.github/workflows/dependency-review.yml`](../.github/workflows/dependency-review.yml))
  blocks a pull request that adds or changes a dependency with a known vulnerability of moderate severity or
  higher, or with a license outside the allowlist.
- The images in `.gitlab-ci.yml` aren't seen by Dependabot; they're bumped by hand at least every quarter.
  Its `checks` job uses the full Python image, not the slim one, because the tests need git; that git is
  Debian's package, so it's brought up to date by the same bump.
- A merged update reaches users only in the next release.

## Policy for vulnerabilities in dependencies

Known vulnerabilities are found by:

- **pip-audit** in every CI run, which checks the pinned runtime requirements against the
  [OSV](https://osv.dev/) database (including malicious-package reports) and fails the build on a finding;
- the weekly **image scan** ([`.github/workflows/scan.yml`](../.github/workflows/scan.yml)): Trivy scans the
  image for HIGH and CRITICAL vulnerabilities that have a fix available and reports each as a
  [code scanning alert](https://github.com/HoneyBearTech/Varken/security/code-scanning);
- **Dependabot alerts** and **dependency review** on pull requests;
- the base image's own advisories (Debian and the Python image).

Each finding is triaged within 14 days:

1. **If a fixed release exists**, bump to it (a Dependabot pull request usually already does) and merge. A
   fix for an exploitable critical or high-severity vulnerability goes out in a patch release within 30
   days; others go out with the next release, and within 90 days.
2. **If upstream hasn't released a fix**, assess whether the vulnerable code is reachable in Varken (it
   opens one port, for `/metrics`; its inputs are its own config, API responses from the operator's
   services, the GeoLite2 archive and HTTP requests to `/metrics`). If it is exploitable, mitigate it where possible and say so in
   the release notes; otherwise record the reason when dismissing the alert or in the pip-audit ignore
   list. Either way, it's fixed by a bump when upstream ships one.
3. **If a dependency is abandoned**, replace it before it accumulates vulnerabilities.

### Vulnerabilities that don't affect Varken (VEX)

A vulnerability reported in a dependency that Varken doesn't use in an affected way (the vulnerable function is
never called, say) is recorded, with the reasoning, as an [OpenVEX](https://openvex.dev/) statement in
[`.vex/varken.openvex.json`](../.vex/varken.openvex.json): `not_affected` with a justification, or `affected`
until it's fixed. The weekly image scan reads that file, so a finding with a `not_affected` statement doesn't
reopen. The file is part of every source release.

### Current findings

None: the document has no statements, because no finding has needed one. Each future entry gets a line here
with the date and the reasoning.

## Policy for findings from static analysis

CodeQL (security and quality queries, Python and the workflows) runs on every pull request, every change to
`main` and weekly; ruff's bandit (`S`) rules run in "Checks + tests".

- **Merges are gated.** A pull request can't merge while CodeQL reports a security alert of high or critical
  severity, or an error, in the code it changes (a code scanning rule in the branch ruleset), nor while ruff
  reports any `S` finding (the required "Checks + tests" job). Lower-severity CodeQL alerts are triaged as below.
- **Thresholds.** Each finding is triaged within 14 days. A critical or high-severity finding that's
  exploitable is fixed before the next release and within 30 days; medium within 90 days; low and notes with
  the next change to that code.
- **False positives** are dismissed in code scanning (or, for ruff, suppressed on the line with
  `# noqa: Sxxx -- <reason>`), always with the reason written down.

## Licenses

Every dependency must be under an OSI-approved open source license that allows redistribution in an image
(MIT, Apache-2.0, BSD, ISC, PSF, MPL-2.0 and similar); dependency review enforces the list. yamllint
(GPL-3.0) is allowed as a development tool only: it is never shipped in the image. Varken's own files are
MIT-licensed ([LICENSE](../LICENSE)).

## Policy for findings from static analysis (SAST)

CodeQL analyses the Python code and the workflows on every pull request and weekly, and ruff runs in CI. A
CodeQL finding of medium severity or higher is fixed before the next release, or, if it is a false positive,
dismissed in code scanning with a written reason. A ruff finding fails CI; a deliberate exception is a
per-line `noqa` with the reason next to it. Weaknesses that can't be fixed at once are listed in
[security.md](security.md#known-weaknesses) with a plan.

## Published vulnerabilities

Vulnerabilities in Varken itself are published as GitHub security advisories, as described in
[SECURITY.md](../SECURITY.md#published-vulnerabilities).
