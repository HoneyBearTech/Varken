# Security Policy

## Reporting a vulnerability

Please report vulnerabilities in Varken through GitHub's private vulnerability reporting form:

https://github.com/HoneyBearTech/Varken/security/advisories/new

Do not report vulnerabilities through public issues. Include what you found, how to reproduce it, which
version or commit you tested, and what an attacker gains. Please avoid accessing or changing data that is
not yours while investigating, and leave real API keys, hostnames, addresses and viewing history out of
the report. If you'd like to be credited under a particular name, or not at all, say so.

## How reports are handled

This is a personal project maintained by one person (see [GOVERNANCE.md](GOVERNANCE.md)), so these are
targets rather than a contractual SLA:

1. **Acknowledge** the report within 7 days.
2. **Triage** it: reproduce the problem, decide whether it is a vulnerability in Varken (see "Scope" below)
   and agree its severity with you. If it isn't a vulnerability, you'll get an explanation, and the report
   may move to a public issue with your agreement.
3. **Fix** it privately in a [GitHub security advisory](https://docs.github.com/en/code-security/security-advisories/working-with-repository-security-advisories/about-repository-security-advisories),
   with a regression test where the problem can be tested, and invite you to review the fix if you want
   to.
4. **Release** the fix, then publish the advisory (requesting a CVE where it applies) with the affected
   and fixed versions and any workaround. The aim is to release fixes for critical and high-severity
   issues within 30 days of the report and others within 90 days, and to keep you updated at least every
   14 days until then.
5. **Credit** the reporter in the advisory and the release notes, unless you ask to stay anonymous.

## Coordinated disclosure

Please keep the details private until the advisory is published, or for 90 days after your report if no
fix has been released by then, whichever comes first. If you need a different timeline, say so in the
report.

## Supported versions

The latest release and the default branch (`master`) receive security fixes; a release stops receiving
them when the next one is published. Releases from this repository start at 2.0.0. The upstream
Boerderij/Varken releases (1.7.7 and earlier) are unmaintained and get no fixes from this project; see
[SUPPORT.md](SUPPORT.md) and [docs/upgrading.md](docs/upgrading.md).

## Published vulnerabilities

Vulnerabilities fixed in Varken are published as
[GitHub security advisories](https://github.com/HoneyBearTech/Varken/security/advisories) (with a CVE where
one applies), naming the affected and fixed versions, how to tell whether you're affected and how to fix or
work around it, and they're listed in the release notes and [CHANGELOG.md](CHANGELOG.md). None have been
reported so far.

Known weaknesses that are already public, such as `verify_ssl` defaulting to off, are listed in
[docs/security.md](docs/security.md#known-weaknesses) with the plan for each. Known vulnerabilities in what
Varken is built from (the Python base image and the Python packages) are handled as described in
[docs/dependencies.md](docs/dependencies.md).

## Scope

Varken is a collector: on a schedule it reads data from the Tautulli, Sonarr, Radarr, Lidarr, Ombi,
SickChill and UniFi servers its operator configures, optionally looks up viewer locations in a local MaxMind
GeoLite2 database, and serves the results as Prometheus metrics. Its one listening port is that `/metrics`
endpoint (9180 by default). What it does and doesn't protect
against is described in [docs/security.md](docs/security.md) (its security requirements), and the
reasoning in [docs/assurance-case.md](docs/assurance-case.md) (threat model, trust boundaries and the
defences against common weaknesses).

In scope: anything that breaks the guarantees in those documents, for example a way to make Varken change
data in one of the services it reads, write outside its data folder, send an API key or password to anyone
other than the service it belongs to, execute code from a crafted API response or GeoLite2 archive, a
release artifact that doesn't match its signature, or a published file that leaks a secret. Not
vulnerabilities: anything that needs write access to the host, the data folder, `varken.ini` or the
container's environment (they are trusted inputs); the weaknesses already listed in
[docs/security.md](docs/security.md#known-weaknesses); and the access control of Prometheus and Grafana
themselves. Vulnerabilities in Tautulli, the \*arr apps, Ombi, SickChill, UniFi, Prometheus, Grafana or
Python belong with those projects, but please tell us too if Varken makes one worse.
