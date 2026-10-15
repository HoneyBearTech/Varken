# Varken documentation

Start with the [README](../README.md) for what Varken is and how to run it.

| Document | For |
| --- | --- |
| [Quick start](quick-start.md) | Varken, InfluxDB and Grafana with Docker Compose, reading one Tautulli server |
| [Installing](installing.md) | Compose, `docker run`, Unraid or bare Python with systemd; running it securely; uninstalling |
| [Configuration](configuration.md) | Every `varken.ini` key and its `VRKN_*` environment variable |
| [How it works](architecture.md) | Actors, components, what a run does, failure behaviour, and the Prometheus output |
| [Interfaces](interfaces.md) | The command line, the InfluxDB measurements it writes, the Prometheus metrics it serves at `/metrics`, every outbound request, and files |
| [Upgrading](upgrading.md) | Moving from upstream Varken 1.7.x to 2.0.0, between releases, backups and rolling back |
| [Verifying releases](verifying-releases.md) | Checking that images and release files came from this repository, unchanged |
| [Security requirements](security.md) | What Varken guarantees, how to run it securely, and its known weaknesses |
| [Assurance case](assurance-case.md) | The threat model, trust boundaries and how common weaknesses are countered |
| [Dependencies](dependencies.md) | How dependencies are chosen, pinned, tracked and patched |
| [Roadmap](roadmap.md) | What's planned for the next year, and what Varken will not do |

Project policies live at the top of the repository: [CONTRIBUTING.md](../CONTRIBUTING.md),
[GOVERNANCE.md](../GOVERNANCE.md), [SECURITY.md](../SECURITY.md), [SUPPORT.md](../SUPPORT.md),
[CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) and [CHANGELOG.md](../CHANGELOG.md).

Varken has no user interface of its own (it is a background service, configured by a file or environment
variables), so there is no accessibility guide; the dashboards you build on its data are Grafana's.

These documents change in the same pull request as the behaviour they describe. If you find one that's
wrong, please [open an issue](https://github.com/HoneyBearTech/Varken/issues): it's treated as a bug.
