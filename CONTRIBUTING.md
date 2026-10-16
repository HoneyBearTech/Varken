# Contributing to Varken

Varken is a personal project with a single maintainer (see [GOVERNANCE.md](GOVERNANCE.md)). Contributions
are welcome, but there is no service-level agreement, and review may take a while. Releases are tagged
`vMAJOR.MINOR.PATCH`; only the latest release and the default branch, `main`, are supported
([SUPPORT.md](SUPPORT.md)). Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).

## Reporting bugs and suggesting changes

- Use [GitHub Issues](https://github.com/HoneyBearTech/Varken/issues) for bugs, questions and ideas. Say
  which Varken version you run, how you run it (image or bare Python), which module is involved and which
  version of that service (Tautulli, Sonarr and so on), and include the relevant log lines. Remove API keys,
  passwords, hostnames, IP addresses, usernames and media titles from anything you paste: Varken's debug
  log contains all of them. For anything bigger than a small fix, please open an issue first so we can
  agree on the approach. The [roadmap](docs/roadmap.md) says what's planned and what's out of scope.
- **Do not report security vulnerabilities in a public issue.** Follow [SECURITY.md](SECURITY.md) and use
  GitHub's private vulnerability reporting instead.

## Development setup

You need git, Python 3.14 (the image's version), and Docker if you want to build the image.

```sh
git clone https://github.com/HoneyBearTech/Varken.git && cd Varken
python3 -m venv .venv
.venv/bin/pip install --require-hashes --no-deps -r requirements-dev.txt -r requirements.txt
```

How Varken is put together is in [docs/architecture.md](docs/architecture.md). To run it against your own
services, copy the example config into the gitignored `data/varken.ini` and run it in the foreground:

```sh
cp data/varken.example.ini data/varken.ini && chmod 600 data/varken.ini   # then edit it
.venv/bin/python Varken.py
```

It serves its metrics on port 9180: `curl -s 127.0.0.1:9180/metrics` shows them (set `[prometheus]`
`bind = 127.0.0.1` to keep them to your machine). Every setting is in
[docs/configuration.md](docs/configuration.md).

## When and how tests run

Every push and pull request runs one CI job, "Checks + tests"
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)), which is the required check for merging. It runs
the linters below, a gitleaks scan of the whole history, pip-audit over the pinned runtime requirements, the
unit tests with a coverage floor, builds the image and checks that it runs as non-root and starts locked
down, and validates the compose file. CodeQL, dependency review, a DCO check and OpenSSF
Scorecard also run on the repository, and Trivy scans the image weekly for known vulnerabilities.

The maintainer also keeps a copy on a self-hosted GitLab, mirrored from GitHub by a scheduled job in
[`.gitlab-ci.yml`](.gitlab-ci.yml), which re-runs the "Checks + tests" steps that need no Docker daemon on
every commit it receives. Changes go to GitHub only; a commit made on the GitLab copy stops the mirror.

The tests in [`tests/`](tests/) are offline: they run against recorded API responses and mocks, and never
reach Tautulli, the \*arr apps or MaxMind.

## Before you open a pull request

Run what CI runs and make sure it passes:

```sh
.venv/bin/ruff check .
.venv/bin/yamllint --strict .
.venv/bin/coverage run -m pytest && .venv/bin/coverage report
docker build -t varken:dev .
```

actionlint, hadolint, gitleaks and pip-audit run in CI; the exact commands are in
[`ci.yml`](.github/workflows/ci.yml) if you want to run them locally.

## Coding standards

- **Python** (`Varken.py`, `varken/`, `tests/`): [PEP 8](https://peps.python.org/pep-0008/),
  enforced by [ruff](https://docs.astral.sh/ruff/) with a line length of 120 and the rule families in
  [`pyproject.toml`](pyproject.toml): pycodestyle, Pyflakes, bugbear and the bandit security rules. Most of
  the code predates this fork, so `ruff format` isn't applied yet (it would rewrite every file; it's on the
  [roadmap](docs/roadmap.md)): match the style of the surrounding code. New code gets type hints and docstrings.
- **Network calls** go through `connection_handler()` in [`varken/helpers.py`](varken/helpers.py), so error
  handling stays in one place. Varken only reads from the services it collects from: no request may change
  data there.
- **Secrets** (API keys, passwords, the MaxMind license key) are never logged in full, never put in a URL
  where a header would do, never sent anywhere but the service they belong to, and never in the metrics.
- **YAML** (workflows, compose file, issue forms): [yamllint](https://yamllint.readthedocs.io/) in strict
  mode, warnings treated as errors.
- **GitHub Actions workflows**: [actionlint](https://github.com/rhysd/actionlint), which also runs
  [shellcheck](https://www.shellcheck.net/) on every `run:` script. Actions are pinned by commit SHA, the
  top-level permission is `contents: read`, jobs ask only for what they need, and untrusted values reach
  scripts through `env:`, never `${{ }}` inside `run:`.
- **Dockerfile**: [hadolint](https://github.com/hadolint/hadolint); the base image pinned by version and
  digest, Python packages installed with `--require-hashes`, and the image runs as an unprivileged user.
- **Secrets in the repository**: [gitleaks](https://github.com/gitleaks/gitleaks) scans the whole history.
- **Dependencies**: [pip-audit](https://github.com/pypa/pip-audit) checks the pinned runtime requirements
  against the OSV database; see [docs/dependencies.md](docs/dependencies.md) before adding one.
- Exceptions are made per line (for example `# noqa: S310 - reason`) with the reason next to them, never by
  turning a rule off for the whole repository.

## Test policy

- **New behaviour comes with automated tests**: a new module, metric, setting or code path gets a test
  that exercises it against a recorded response.
- **Bug fixes come with a regression test** that fails before the fix, wherever the bug can be tested.
- **Tests are offline.** They use fixtures and mocks, never a real service or MaxMind, and never
  real API keys, hostnames or viewing data. Fixtures use placeholders such as `tautulli.example.com`.
- Coverage must stay at or above the floor in [`pyproject.toml`](pyproject.toml); CI fails below it. The
  floor only goes up, towards the 80 % target on the [roadmap](docs/roadmap.md).

## Updating pinned dependencies

Runtime dependencies are declared in `requirements.in` and pinned, with hashes, in `requirements.txt`; the
development tools likewise in `requirements-dev.in` and `requirements-dev.txt`. After editing a `.in` file
(or to pick up new versions), regenerate the pins with [uv](https://docs.astral.sh/uv/):

```sh
uv pip compile --generate-hashes --python-version 3.14 requirements.in -o requirements.txt
uv pip compile --generate-hashes --python-version 3.14 requirements-dev.in -o requirements-dev.txt
```

Commit the `.in` and `.txt` files together. Dependabot proposes routine updates; see
[docs/dependencies.md](docs/dependencies.md).

## Developer Certificate of Origin

Every commit must be signed off to certify the [Developer Certificate of Origin](https://developercertificate.org/):
that you wrote the change or otherwise have the right to submit it under the project's license. Add the
sign-off with `git commit -s`, which appends:

```
Signed-off-by: Your Name <you@example.com>
```

using your git `user.name` and `user.email`. The DCO check
([`.github/workflows/dco.yml`](.github/workflows/dco.yml)) fails a pull request with an unsigned commit; fix
it with `git rebase --signoff main` and force-push your branch.

## Pull requests

- Changes land on `main` only through a pull request that passes "Checks + tests". Pull requests are
  squash-merged.
- Keep each pull request focused on one change, and describe what it does and why.
- Add a line to `CHANGELOG.md` under `## [Unreleased]` for anything a user would notice, and update
  `data/varken.example.ini`, `.env.example`, [docs/configuration.md](docs/configuration.md) and the other docs when you
  change settings, metrics or behaviour. A change that needs action on upgrade says so in the
  changelog.
- **This repository is public.** Never commit API keys, passwords, MaxMind license keys, `varken.ini`,
  `.env` files, hostnames, IP addresses, usernames or media titles, including in test fixtures and
  screenshots. CI runs gitleaks over the history.

## Releases

The maintainer moves the "Unreleased" entries in `CHANGELOG.md` into a `## [x.y.z] - YYYY-MM-DD` section,
merges that, then pushes a signed tag:

```sh
git tag -s vX.Y.Z -m vX.Y.Z && git push origin vX.Y.Z
```

The release workflow builds, signs and publishes the image to GHCR and creates the GitHub Release from that
changelog section ([docs/verifying-releases.md](docs/verifying-releases.md)).

## License

By contributing, you agree that your contribution is licensed under the project's [MIT License](LICENSE).
