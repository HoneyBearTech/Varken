# Security review

A record of each security review of Varken: what was reviewed, how, what was found and what was decided. The next
review is due by **October 2027**, or before a release that adds a network interface, a new kind of credential or
a new service module, whichever comes first.

## 2026-10-16 — Varken 3.2.0 and `main`

**Reviewed by** the maintainer (@HoneyBearTech), with an AI coding assistant (Claude Code) doing the line-by-line
reading and running the tools. This is a review by a project member, not an independent audit.

### Scope

Everything Varken 3.2.0 ships and everything that builds it:

- **Security requirements** ([security.md](security.md)): what Varken promises (it only reads, credentials only to
  their own service, viewer addresses never exported, only the data folder written) and whether the code keeps
  each promise.
- **Every trust boundary** in the [assurance case](assurance-case.md): the operator's configuration (B1), service
  replies (B2), credentials sent to services (B3), the GeoLite2 download (B4), the host (B5), contributions (B6),
  the supply chain from base image to published image (B7), and the unauthenticated `/metrics` endpoint (B8).
- **The code paths** that handle untrusted input: settings and `VRKN_*` variables, URL validation, every service
  module's reply parsing (Tautulli, Sonarr, Radarr, Lidarr, Ombi, Seerr, SickChill, UniFi), log masking, the
  GeoLite2 download and extraction, and building the scrape.
- **The pipeline**: workflows (permissions, inputs, triggers), the release (signing, SBOM, provenance), the
  repository rules, and the GitLab mirror job.

### Method

- Reading the code along each boundary against the assurance case's claims.
- Property-based tests (Hypothesis) and coverage-guided fuzzing (Atheris) of every untrusted input, run for this
  review; adding them to the repository and to CI is in progress, together with the fixes for findings 1–4.
- The standing tools: CodeQL, ruff's bandit rules, pip-audit, dependency review, gitleaks, Trivy, OpenSSF
  Scorecard; checking each workflow by hand for `pull_request_target`, untrusted interpolation and write tokens.
- Verifying the published 3.2.0 release from outside: anonymous pull, cosign signatures on the image and the
  checksums, SLSA provenance, and the image running as uid 1000 with a read-only root filesystem.

### Findings

| # | Finding | Severity | Status |
| --- | --- | --- | --- |
| 1 | A lone surrogate in a title from a service made the whole `/metrics` scrape fail to encode, so every metric disappeared (a remote service could blank the monitoring) | Medium | Open: fix in progress (label values replace it with U+FFFD), with a property test |
| 2 | A `null` or other non-object in a Sonarr, Radarr, Lidarr or Seerr reply list crashed the job with a traceback | Low | Open: fix in progress (such entries are skipped with an error), with a property test |
| 3 | Two items with the same labels made a duplicate series in one scrape, which Prometheus drops | Low | Open: fix in progress (each info family emits a label set once), with a property test |
| 4 | A server id with no `varken.ini` section ended in a traceback instead of an error | Low | Open: fix in progress (Varken exits with a message naming the section), with a regression test |
| 5 | Secrets were masked to `********` plus their last five characters | Low | Fixed in 3.0.0: nothing is kept |
| 6 | The GeoLite2 download wasn't checked against MaxMind's published SHA-256 | Low | Fixed in 3.1.0 |
| 7 | Merges to `main` had no code-scanning gate: CodeQL's check passed even with alerts | Low | Fixed: the branch ruleset blocks a merge on a high or critical CodeQL alert |

### Accepted risks

Each is documented where users will see it:

- `/metrics` has no authentication or TLS, so anyone who can reach it reads the metrics: keep it on a private
  network ([security.md](security.md#the-metrics-endpoint)).
- Existing `varken.ini` files keep `verify_ssl = false` where the operator set it; Varken warns at start-up for
  each HTTPS server without certificate checks.
- Tautulli's and SickChill's APIs only take their keys in the URL; the keys are masked in logs.
- Seerr has no read-only API key, so Varken holds an admin key and only reads with it.
- One maintainer: no second person reviews changes, and the maintainer merges through the ruleset's pull-request
  bypass ([GOVERNANCE.md](../GOVERNANCE.md)).

### Result

Findings 5–7 are fixed. Findings 1–4 stay open until their fixes are merged, and this record is updated when they
are; none of them exposes a credential or viewer data. Apart from them, the security requirements in
[security.md](security.md) hold for 3.2.0.
