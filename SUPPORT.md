# Support

Varken is maintained by one person in their own time (see [GOVERNANCE.md](GOVERNANCE.md)), so this is a
best-effort policy, not a contract.

## Getting help

- **Questions, bugs and ideas**: [GitHub Issues](https://github.com/HoneyBearTech/Varken/issues). Say which
  Varken version you run, whether you use the image or bare Python, which module and service version is
  involved, and what you expected. Leave out API keys, passwords, hostnames, IP addresses, usernames and
  media titles: Varken's debug log contains them, so redact any log lines you paste.
- **Security vulnerabilities**: never in a public issue; see [SECURITY.md](SECURITY.md).
- **Documentation**: the [README](README.md) and [docs/](docs/README.md), starting with the
  [quick start](docs/quick-start.md).

This fork is a separate project from the original Boerderij/Varken. Please don't ask about it in the
original project's Discord, wiki or issue tracker, and don't expect help with this fork there.

## Which versions are supported, and for how long

| Version | Supported with | Until |
| --- | --- | --- |
| The latest release | bug fixes and security fixes | the next release is published |
| An older release | nothing | it stopped being supported when the next release came out |
| `master` (the default branch) | bug fixes and security fixes | always (it's where fixes land first) |
| Upstream Boerderij/Varken 1.7.7 and earlier, and the `boerderij/varken` images | nothing from this project | unmaintained since 2020; [upgrade to 2.0.0](docs/upgrading.md) |

- A fix is released as a new version (a patch release such as 2.0.1 for fixes only), never applied to an
  older release.
- **A release stops receiving security updates the moment the next release is published.** Its notes and
  [CHANGELOG.md](CHANGELOG.md) say what changed and whether upgrading needs steps; upgrading is described in
  [docs/upgrading.md](docs/upgrading.md).
- Releases follow [semantic versioning](https://semver.org/): a change to settings, measurements or the
  image that needs action on upgrade comes in a new major version and is listed in the changelog.
- Varken follows the APIs of the services it reads as they are when a release is made. When one of them
  changes in a way that breaks a module, the fix comes in a new release, if the module is still
  maintained ([roadmap](docs/roadmap.md)).
- If a supported line will end differently (for example a 2.x line kept alive after 3.0), it will be
  announced in the release notes and in this table first.

Images stay available on GHCR after their support ends, so existing installations keep working, but they
won't get fixes: run the latest release, or `master` from a checkout.
