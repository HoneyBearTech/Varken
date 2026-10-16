# Governance

Varken is a personal open-source project with a single maintainer. This document says how decisions are
made, who does what, who can reach the project's sensitive resources, and how the project carries on if the
maintainer can't.

## History and credit

Varken was created by [Boerderij](https://github.com/Boerderij), principally DirtyCajunRice and samwiseg0,
with many contributors; their last release was 1.7.7 in December 2020, and the original project is no
longer maintained. In 2026 HoneyBearTech forked it, detached the fork, and continues it here as a
standalone project under the same MIT license, keeping the original copyright notice in [LICENSE](LICENSE)
and the upstream history in git and [CHANGELOG.md](CHANGELOG.md). The original authors are not involved in
this project and are not responsible for it: please don't take questions about this fork to their channels.

## Decision model

Varken follows a "benevolent dictator" model: the maintainer makes the final call on every decision,
including what is in scope, which pull requests are merged, and when a release is made.

Decisions happen in the open wherever possible:

- **Bugs, features and questions** are discussed in
  [GitHub Issues](https://github.com/HoneyBearTech/Varken/issues). Anyone can open one or comment.
- **Changes** land only through pull requests to the default branch, `main`, which must pass the
  required checks, be up to date with `main`, and are squash-merged; nobody can push to `main` directly,
  force-push or delete it. A pull request needs a code owner's approval after its last push. With one
  maintainer there is no second reviewer: the maintainer, as repository admin, merges their own pull
  requests through the ruleset's pull-request-only bypass, so every change still goes through a pull request
  and its checks. A second maintainer would end that bypass. The pull request description records what
  changed and why.
- **Direction** is published in the [roadmap](docs/roadmap.md), including what the project does not intend
  to do. Larger design choices are explained in the pull requests that make them.
- **Security reports** are handled privately, as described in [SECURITY.md](SECURITY.md), until a fix is
  released.

If you disagree with a decision, say so in the issue or pull request. The maintainer will explain the
reasoning, and may change course. Because the code is MIT-licensed, you can always fork it.

## Roles and responsibilities

| Role | Who | Responsibilities |
| --- | --- | --- |
| Maintainer | Sean Stoube ([@HoneyBearTech](https://github.com/HoneyBearTech)) | Triage issues; review and merge pull requests; keep CI, dependencies and documentation current; triage dependency and code-scanning findings; respond to vulnerability reports as described in [SECURITY.md](SECURITY.md); cut and sign releases; enforce the [Code of Conduct](CODE_OF_CONDUCT.md); keep this document and the continuity arrangements below up to date. |
| Contributor | Anyone who opens an issue or pull request | Follow [CONTRIBUTING.md](CONTRIBUTING.md) (coding standards, tests, sign-off, no secrets, hostnames or viewing data) and the [Code of Conduct](CODE_OF_CONDUCT.md); report vulnerabilities privately. |
| Security reporter | Anyone who reports a vulnerability | Report privately and allow time for a fix before disclosing, as described in [SECURITY.md](SECURITY.md). |

Automated tools also take part: Dependabot proposes updates to the base image, the Python packages and the
GitHub Actions, which the maintainer reviews and merges by hand, and CI, CodeQL, dependency review and
OpenSSF Scorecard check every change.

## Access to sensitive resources

Who can change the code, releases and project settings, as of the date of this file's last change:

| Resource | Who has access | Through |
| --- | --- | --- |
| Repository administration (settings, branch rules, merging) | the maintainer (@HoneyBearTech) | GitHub account owner |
| Publishing images to GHCR (`ghcr.io/honeybeartech/varken`) | the release workflow, on a version tag pushed by the maintainer | GitHub Actions, short-lived `GITHUB_TOKEN` |
| Signing images and release files | the release workflow, on a version tag | Sigstore keyless signing with the job's GitHub identity; no stored key |
| Signing commits and version tags | the maintainer | personal SSH key (public half in [`.github/allowed_signers`](.github/allowed_signers)) |
| Mirroring the repository into the maintainer's self-hosted GitLab | the scheduled mirror job in [`.gitlab-ci.yml`](.gitlab-ci.yml) | a GitLab project access token (Maintainer role, `write_repository` only, with an expiry) in a masked, protected CI/CD variable on that GitLab; the maintainer creates and rotates it |
| The OpenSSF Best Practices badge entry ([project 15525](https://www.bestpractices.dev/projects/15525)) | the maintainer | GitHub sign-in |
| Security advisories and private vulnerability reports | the maintainer | GitHub |
| Automated changes | Dependabot (pull requests only) | GitHub, short-lived `GITHUB_TOKEN` |

There are no other collaborators. Workflows use the per-job `GITHUB_TOKEN`, read-only unless a job asks for
more, and pull requests from forks get read-only tokens and no secrets. The project stores no repository
secrets.

## Granting elevated access

Nobody gets write, maintain or admin access to the repository, or any of the resources above, without this
review:

1. The person has a public track record with the project: several merged pull requests of good quality
   over at least three months, and participation in reviews or issues.
2. Their identity is established: a GitHub account with history, two-factor authentication on, and a way
   for the maintainer to confirm who they are (for example a known employer, a long-standing open-source
   profile, or meeting in person).
3. The maintainer decides, records the decision and the role in a pull request that updates the tables in
   this file, and grants the least access that role needs.
4. Access is removed when someone steps back or is inactive for a year, also by a pull request here.

## The project's own secrets

The credentials the Varken project holds (not those of a Varken installation, such as its API keys and
UniFi password, which stay in that installation's `varken.ini` or environment), and how they're handled:

- **What exists**: the maintainer's GitHub account and its recovery codes, and the SSH key that signs
  commits and tags. Images and release files are signed keylessly (Sigstore), so there is no long-lived
  signing key, and the project stores no repository secrets.
- **Storage**: in the maintainer's password manager, never in the repository, CI logs, issues or pull
  requests. A gitleaks scan in CI blocks committed secrets, and `.gitignore` excludes `varken.ini`, the
  GeoLite2 database and logs.
- **Access**: the maintainer only; the successor reaches the GitHub account and the signing key through
  the lockbox described under Continuity.
- **Rotation**: recovery codes are regenerated after use and at least yearly, and the lockbox updated; the
  signing key is replaced (and `.github/allowed_signers` updated) if it may have been exposed. Any secret
  that might have leaked is revoked and replaced at once, and the incident handled as in
  [SECURITY.md](SECURITY.md).
- A new stored secret needs a reason, is scoped to the one workflow job that uses it, and is added to this
  section in the same pull request.

## Continuity

The project must be able to carry on, with issues opened and closed, changes accepted and releases made,
within a week of it being confirmed that the maintainer can no longer support it. To make that possible:

- **A lockbox**: the credentials needed to run the project are kept in a password-manager vault that a
  trusted person the maintainer has chosen can open through the password manager's **emergency access**,
  after a waiting period of a few days (short enough to act within the week). It holds the login and
  two-factor recovery codes of the GitHub account that owns the repository, access to that account's email
  address, and the SSH key that signs commits and release tags. It is the same arrangement that covers the
  maintainer's other projects under that account.
- **Releases keep working from the repository alone.** Images are signed keylessly by GitHub Actions, so
  whoever controls the repository can keep publishing verifiable releases to GHCR.
- **A succession note**, kept with the maintainer's personal papers and referenced from the lockbox, gives
  that person the right to continue the project or to hand it to a new maintainer.
- Everything else needed to keep working on the project is in this repository: the code, the CI
  configuration, the release process and the documentation.

Names and credentials are deliberately not published here. If the maintainer becomes unable to continue,
the successor will announce it in a pinned issue and update this file.

Varken has one maintainer, so its "bus factor" is 1: these arrangements keep the project from being
stranded, but they don't replace a second active maintainer, and Varken has already been abandoned once
upstream. Contributions remain welcome through pull requests, and anyone who wants to help maintain it can
go through [Granting elevated access](#granting-elevated-access). If the project does stall, the MIT
license lets anyone fork it again, as this project did.
