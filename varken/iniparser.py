# SPDX-FileCopyrightText: 2018 Boerderij
# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
"""Varken's configuration: varken.ini, the VRKN_* environment variables over it and varken.example.ini under it."""

import re
import sys
from configparser import ConfigParser, NoOptionError, NoSectionError
from ipaddress import ip_address
from logging import getLogger
from os import environ as env
from pathlib import Path
from shutil import copyfile
from typing import Any, Literal, NoReturn

from varken.helpers import boolcheck, clean_sid_check, rfc1918_ip_check
from varken.structures import (
    OmbiServer,
    PrometheusServer,
    RadarrServer,
    SeerrServer,
    SickChillServer,
    SonarrServer,
    TautulliServer,
    UniFiServer,
)
from varken.varkenlogger import BlacklistFilter

MAX_PORT = 65535


class ConfigFile(ConfigParser):
    """varken.ini as Varken reads it.

    A key the file doesn't have (one a newer Varken added, usually) takes its value from varken.example.ini, in
    memory: the file itself is never written to.
    """

    def __init__(self, example_path: str | Path) -> None:
        """Start empty; `example_path` is where varken.example.ini is, and it is read only when it is needed."""
        super().__init__(interpolation=None)
        self.example_path = Path(example_path)
        self.example: ConfigParser | None = None  # varken.example.ini, once read
        self.defaulted: dict[str, list[str]] = {}  # section -> the keys whose values came from the example

    def read_example(self) -> ConfigParser:
        """varken.example.ini, or nothing where there is none: a complete varken.ini doesn't need it."""
        if self.example is None:
            self.example = ConfigParser(interpolation=None)
            if self.example_path.exists():
                with self.example_path.open() as example_ini:
                    self.example.read_file(example_ini)
        return self.example

    def get(self, section: str, option: str, **kwargs: Any) -> str:  # noqa: ANN401 - ConfigParser.get's keywords
        """Get the value from varken.ini, or from varken.example.ini when varken.ini doesn't have the key."""
        try:
            return super().get(section, option, **kwargs)
        except (NoSectionError, NoOptionError) as missing:
            try:
                value = self.read_example().get(section, option, **kwargs)
            except (NoSectionError, NoOptionError) as in_example:
                # In neither file. If varken.ini has the section and only lacks the key, say that: it is more to
                # the point than the example lacking the whole section.
                raise (missing if isinstance(missing, NoOptionError) else in_example) from None
            # With its VRKN_ variable set, the caller uses that and not this value, so nothing was defaulted.
            if f'VRKN_{section}_{option}'.upper().replace('-', '_') not in env:
                keys = self.defaulted.setdefault(section, [])
                if option not in keys:
                    keys.append(option)
            return value


class INIParser:
    """The settings Varken runs with: the servers of every enabled service, and where /metrics is served.

    A setting that can't be used is logged and ends the start with exit status 1.
    """

    def __init__(self, data_folder: str) -> None:
        """Read the configuration in the data folder."""
        self.config: ConfigFile | None = None
        self.data_folder = data_folder
        self.filtered_strings: list[str] | None = None
        self.services = ['sonarr', 'radarr', 'lidarr', 'ombi', 'seerr', 'tautulli', 'sickchill', 'unifi']

        self.logger = getLogger()
        self.prometheus_server = PrometheusServer()

        self.read_secret_files()
        try:
            self.parse_opts()
        except (NoSectionError, NoOptionError) as e:
            self.missing_setting(e)
        self.report_defaults()

    def read_secret_files(self) -> None:
        """VRKN_<SECTION>_<KEY>_FILE names a file that holds the value (Docker and compose secrets)."""
        for name, path in list(env.items()):
            if not (name.startswith('VRKN_') and name.endswith('_FILE')):
                continue
            target = name.removesuffix('_FILE')
            if target in env:
                self.logger.error('Both %s and %s are set; use one. Exiting.', target, name)
                sys.exit(1)
            try:
                # The path as it was given: Path('') would be the current folder.
                with open(path) as secret:  # noqa: PTH123
                    env[target] = secret.read().strip()
            except OSError as e:
                self.logger.error('Could not read %s (%s): %s. Exiting.', name, path, e)
                sys.exit(1)

    def config_blacklist(self) -> None:
        """Give every log handler a filter for the secrets in the configuration: in the file, the example or VRKN_*."""
        filtered_strings = [
            section.get(k)
            for key, section in self.config.items()
            for k in section
            if k in BlacklistFilter.blacklisted_strings
        ]
        # A key the file lacks takes the example's value, which is then used like the file's would be.
        filtered_strings.extend(
            value
            for name, section in self.config.read_example().items()
            for k, value in section.items()
            if k in BlacklistFilter.blacklisted_strings and not self.config.has_option(name, k)
        )
        # VRKN_* environment variables override the file, so their values are just as secret.
        secret_suffixes = tuple(f'_{key}' for key in BlacklistFilter.blacklisted_strings)
        filtered_strings.extend(
            value for name, value in env.items() if name.startswith('VRKN_') and name.lower().endswith(secret_suffixes)
        )
        self.filtered_strings = list(filter(None, filtered_strings))
        # Added matching for domains that use /locations. ConnectionPool ignores the location in logs
        domains_only = [string.split('/')[0] for string in filtered_strings if '/' in string]
        self.filtered_strings.extend(domains_only)
        # Added matching for domains that use :port. ConnectionPool splits the domain/ip from the port
        without_port = [string.split(':')[0] for string in filtered_strings if ':' in string]
        self.filtered_strings.extend(without_port)

        for handler in self.logger.handlers:
            handler.addFilter(BlacklistFilter(set(self.filtered_strings)))

    def enable_check(self, server_type: str | None = None) -> list[int] | Literal[False] | None:
        """Read a service's server ids from [global]: None when it is switched off, False when no id is a number."""
        t = server_type
        global_server_ids = env.get(f'VRKN_GLOBAL_{t.upper()}', self.config.get('global', t))
        if global_server_ids.lower() in ['false', 'no']:
            self.logger.info('%s disabled.', t.upper())
            return None
        return clean_sid_check(global_server_ids, t)

    def read_file(self) -> ConfigFile:
        """Read varken.ini.

        The only time Varken writes it is a first start, when it is copied from varken.example.ini; after that the
        file is the user's, comments and all.
        """
        example_path = Path(self.data_folder, 'varken.example.ini')
        file_path = Path(self.data_folder, 'varken.ini')
        config = ConfigFile(example_path)

        if not file_path.exists():
            # Normal on a first start.
            self.logger.info('No varken.ini in %s yet: creating it from varken.example.ini', self.data_folder)
            try:
                copyfile(example_path, file_path)
            except OSError as e:
                self.logger.error(
                    'Varken does not have permission to write to %s. Error: %s - Exiting.', self.data_folder, e
                )
                sys.exit(1)

        self.logger.debug('Reading from varken.ini')
        with file_path.open() as config_ini:
            config.read_file(config_ini)

        return config

    def url_check(self, url: str | None = None, *, include_port: bool = True, section: str | None = None) -> str:
        """Return the url as given when it is a host name or IP address, with or without a path; else stop.

        A port is allowed too, unless include_port is off.
        """
        url_check = url
        module = section
        inc_port = include_port

        search = (
            r'(?:([a-z0-9]+(-[a-z0-9]+)*\.)+[a-z]{2,}|'  # domain...
            r'localhost|'  # localhost...
            r'^[a-zA-Z0-9_-]*|'  # hostname only. My soul dies a little every time this is used...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        )
        # Include search for port if it is needed.
        if inc_port:
            search += r'(?::\d+)?'
        search += r'(?:/?|[/?]\S+)\Z'

        regex = re.compile(search, re.IGNORECASE)

        valid = re.match(regex, url_check) is not None
        if not valid:
            if inc_port:
                self.logger.error(
                    '%s is invalid in module [%s]! URL must host/IP and port if not 80 or 443. ie. localhost:8080',
                    url_check,
                    module,
                )
                sys.exit(1)
            else:
                self.logger.error('%s is invalid in module [%s]! URL must host/IP. ie. localhost', url_check, module)
                sys.exit(1)
        else:
            self.logger.debug('%s is a valid URL in module [%s].', url_check, module)
            return url_check

    def missing_setting(self, error: NoSectionError | NoOptionError) -> NoReturn:
        """Say which setting is in neither varken.ini nor varken.example.ini, and what to add, then stop."""
        if not self.config.example_path.exists():
            self.logger.error(
                'varken.ini has no [%s] %s, and there is no varken.example.ini in %s to take it from. Exiting.',
                error.section,
                getattr(error, 'option', 'section'),
                self.data_folder,
            )
        elif isinstance(error, NoOptionError):
            self.logger.error(
                '[%s] %s is missing from varken.ini and from varken.example.ini. Exiting.',
                error.section,
                error.option,
            )
        elif error.section in ('global', 'prometheus'):
            self.logger.error('varken.ini and varken.example.ini have no [%s] section. Exiting.', error.section)
        else:
            # A server id without a section of its own (sonarr_server_ids = 3, no [sonarr-3]): the example can't
            # supply that section, so say what to add rather than fail with a traceback.
            self.logger.error(
                'varken.ini has no [%s] section, but a server id in [global] points to it: add the section, '
                'or remove the id. Exiting.',
                error.section,
            )
        sys.exit(1)

    def report_defaults(self) -> None:
        """Name the settings varken.ini doesn't have, whose values came from varken.example.ini.

        Names only: a value could be a secret.
        """
        if not self.config.defaulted:
            return
        self.logger.info(
            'varken.ini has no %s: using the values in varken.example.ini. varken.ini is left as it is; add the '
            'settings to it to change them.',
            '; '.join(f'[{section}] {", ".join(keys)}' for section, keys in self.config.defaulted.items()),
        )

    def parse_opts(self) -> None:  # noqa: C901, PLR0912, PLR0915 - one block of settings for each service
        """Read every setting: [prometheus], then a server for each id of each enabled service."""
        for service in self.services:
            setattr(self, f'{service}_servers', [])

        self.config = self.read_file()
        self.config_blacklist()
        # Parse Prometheus options
        try:
            bind = env.get('VRKN_PROMETHEUS_BIND', self.config.get('prometheus', 'bind'))
            prometheus_port = int(env.get('VRKN_PROMETHEUS_PORT', self.config.get('prometheus', 'port')))
            stream_details = boolcheck(
                env.get('VRKN_PROMETHEUS_STREAM_DETAILS', self.config.get('prometheus', 'stream_details'))
            )
        except ValueError as e:
            self.logger.error('Invalid configuration value in prometheus. Error: %s', e)
            sys.exit(1)
        try:
            ip_address(bind)
        except ValueError:
            self.logger.error('[prometheus] bind must be an IP address such as 0.0.0.0 or 127.0.0.1, not %s', bind)
            sys.exit(1)
        if not 0 < prometheus_port <= MAX_PORT:
            self.logger.error('[prometheus] port must be between 1 and 65535, not %s', prometheus_port)
            sys.exit(1)

        self.prometheus_server = PrometheusServer(bind=bind, port=prometheus_port, stream_details=stream_details)

        # Check for all enabled services
        for service in self.services:
            setattr(self, f'{service}_enabled', self.enable_check(f'{service}_server_ids'))
            service_enabled = getattr(self, f'{service}_enabled')

            if service_enabled:
                for server_id in service_enabled:
                    server = None
                    section = f'{service}-{server_id}'
                    envsection = f'{service}_{server_id}'.upper()
                    try:
                        url = self.url_check(
                            env.get(f'VRKN_{envsection}_URL', self.config.get(section, 'url')), section=section
                        )

                        apikey = None
                        if service != 'unifi':
                            apikey = env.get(f'VRKN_{envsection}_APIKEY', self.config.get(section, 'apikey'))
                        ssl_scheme = boolcheck(env.get(f'VRKN_{envsection}_SSL', self.config.get(section, 'ssl')))
                        scheme = 'https://' if ssl_scheme else 'http://'
                        verify_ssl = boolcheck(
                            env.get(f'VRKN_{envsection}_VERIFY_SSL', self.config.get(section, 'verify_ssl'))
                        )

                        if scheme != 'https://':
                            verify_ssl = False
                        elif not verify_ssl:
                            # The insecure-request warning is silenced per request, so say it once here.
                            self.logger.warning(
                                '[%s] uses HTTPS without checking the certificate (verify_ssl = '
                                'false): anyone on the network path can read and change the '
                                'traffic, API key included',
                                section,
                            )

                        if service in ['sonarr', 'radarr', 'lidarr']:
                            queue = boolcheck(env.get(f'VRKN_{envsection}_QUEUE', self.config.get(section, 'queue')))
                            queue_run_seconds = int(
                                env.get(
                                    f'VRKN_{envsection}_QUEUE_RUN_SECONDS',
                                    self.config.getint(section, 'queue_run_seconds'),
                                )
                            )

                        if service in ['sonarr', 'lidarr']:
                            missing_days = int(
                                env.get(f'VRKN_{envsection}_MISSING_DAYS', self.config.getint(section, 'missing_days'))
                            )
                            future_days = int(
                                env.get(f'VRKN_{envsection}_FUTURE_DAYS', self.config.getint(section, 'future_days'))
                            )

                            missing_days_run_seconds = int(
                                env.get(
                                    f'VRKN_{envsection}_MISSING_DAYS_RUN_SECONDS',
                                    self.config.getint(section, 'missing_days_run_seconds'),
                                )
                            )

                            future_days_run_seconds = int(
                                env.get(
                                    f'VRKN_{envsection}_FUTURE_DAYS_RUN_SECONDS',
                                    self.config.getint(section, 'future_days_run_seconds'),
                                )
                            )

                            server = SonarrServer(
                                id=server_id,
                                url=scheme + url,
                                api_key=apikey,
                                verify_ssl=verify_ssl,
                                missing_days=missing_days,
                                future_days=future_days,
                                missing_days_run_seconds=missing_days_run_seconds,
                                future_days_run_seconds=future_days_run_seconds,
                                queue=queue,
                                queue_run_seconds=queue_run_seconds,
                            )

                        if service == 'radarr':
                            get_missing = boolcheck(
                                env.get(f'VRKN_{envsection}_GET_MISSING', self.config.get(section, 'get_missing'))
                            )
                            get_missing_run_seconds = int(
                                env.get(
                                    f'VRKN_{envsection}_GET_MISSING_RUN_SECONDS',
                                    self.config.getint(section, 'get_missing_run_seconds'),
                                )
                            )

                            server = RadarrServer(
                                id=server_id,
                                url=scheme + url,
                                api_key=apikey,
                                verify_ssl=verify_ssl,
                                queue_run_seconds=queue_run_seconds,
                                get_missing=get_missing,
                                queue=queue,
                                get_missing_run_seconds=get_missing_run_seconds,
                            )

                        if service == 'tautulli':
                            fallback_ip = env.get(
                                f'VRKN_{envsection}_FALLBACK_IP', self.config.get(section, 'fallback_ip')
                            )

                            get_stats = boolcheck(
                                env.get(f'VRKN_{envsection}_GET_STATS', self.config.get(section, 'get_stats'))
                            )

                            get_activity = boolcheck(
                                env.get(f'VRKN_{envsection}_GET_ACTIVITY', self.config.get(section, 'get_activity'))
                            )

                            get_activity_run_seconds = int(
                                env.get(
                                    f'VRKN_{envsection}_GET_ACTIVITY_RUN_SECONDS',
                                    self.config.getint(section, 'get_activity_run_seconds'),
                                )
                            )

                            get_stats_run_seconds = int(
                                env.get(
                                    f'VRKN_{envsection}_GET_STATS_RUN_SECONDS',
                                    self.config.getint(section, 'get_stats_run_seconds'),
                                )
                            )

                            invalid_wan_ip = rfc1918_ip_check(fallback_ip)

                            if invalid_wan_ip:
                                self.logger.error(
                                    'Invalid fallback_ip [%s] set for %s-%s!', fallback_ip, service, server_id
                                )
                                sys.exit(1)

                            maxmind_license_key = env.get(
                                'VRKN_GLOBAL_MAXMIND_LICENSE_KEY', self.config.get('global', 'maxmind_license_key')
                            )
                            maxmind_account_id = env.get(
                                'VRKN_GLOBAL_MAXMIND_ACCOUNT_ID', self.config.get('global', 'maxmind_account_id')
                            )

                            server = TautulliServer(
                                id=server_id,
                                url=scheme + url,
                                api_key=apikey,
                                verify_ssl=verify_ssl,
                                get_activity=get_activity,
                                fallback_ip=fallback_ip,
                                get_stats=get_stats,
                                get_activity_run_seconds=get_activity_run_seconds,
                                get_stats_run_seconds=get_stats_run_seconds,
                                maxmind_license_key=maxmind_license_key,
                                maxmind_account_id=maxmind_account_id.strip() or None,
                            )

                        if service == 'ombi':
                            issue_status_counts = boolcheck(
                                env.get(
                                    f'VRKN_{envsection}_GET_ISSUE_STATUS_COUNTS',
                                    self.config.get(section, 'get_issue_status_counts'),
                                )
                            )
                            request_type_counts = boolcheck(
                                env.get(
                                    f'VRKN_{envsection}_GET_REQUEST_TYPE_COUNTS',
                                    self.config.get(section, 'get_request_type_counts'),
                                )
                            )
                            request_total_counts = boolcheck(
                                env.get(
                                    f'VRKN_{envsection}_GET_REQUEST_TOTAL_COUNTS',
                                    self.config.get(section, 'get_request_total_counts'),
                                )
                            )

                            issue_status_run_seconds = int(
                                env.get(
                                    f'VRKN_{envsection}_ISSUE_STATUS_RUN_SECONDS',
                                    self.config.getint(section, 'issue_status_run_seconds'),
                                )
                            )
                            request_type_run_seconds = int(
                                env.get(
                                    f'VRKN_{envsection}_REQUEST_TYPE_RUN_SECONDS',
                                    self.config.getint(section, 'request_type_run_seconds'),
                                )
                            )
                            request_total_run_seconds = int(
                                env.get(
                                    f'VRKN_{envsection}_REQUEST_TOTAL_RUN_SECONDS',
                                    self.config.getint(section, 'request_total_run_seconds'),
                                )
                            )

                            server = OmbiServer(
                                id=server_id,
                                url=scheme + url,
                                api_key=apikey,
                                verify_ssl=verify_ssl,
                                request_type_counts=request_type_counts,
                                request_type_run_seconds=request_type_run_seconds,
                                request_total_counts=request_total_counts,
                                request_total_run_seconds=request_total_run_seconds,
                                issue_status_counts=issue_status_counts,
                                issue_status_run_seconds=issue_status_run_seconds,
                            )

                        if service == 'seerr':
                            jobs = {}
                            for job in ('get_request_counts', 'get_issue_counts', 'get_requests'):
                                jobs[job] = boolcheck(
                                    env.get(f'VRKN_{envsection}_{job.upper()}', self.config.get(section, job))
                                )
                                jobs[f'{job}_run_seconds'] = int(
                                    env.get(
                                        f'VRKN_{envsection}_{job.upper()}_RUN_SECONDS',
                                        self.config.getint(section, f'{job}_run_seconds'),
                                    )
                                )
                            server = SeerrServer(
                                id=server_id, url=scheme + url, api_key=apikey, verify_ssl=verify_ssl, **jobs
                            )

                        if service == 'sickchill':
                            get_missing = boolcheck(
                                env.get(f'VRKN_{envsection}_GET_MISSING', self.config.get(section, 'get_missing'))
                            )
                            get_missing_run_seconds = int(
                                env.get(
                                    f'VRKN_{envsection}_GET_MISSING_RUN_SECONDS',
                                    self.config.getint(section, 'get_missing_run_seconds'),
                                )
                            )

                            server = SickChillServer(
                                id=server_id,
                                url=scheme + url,
                                api_key=apikey,
                                verify_ssl=verify_ssl,
                                get_missing=get_missing,
                                get_missing_run_seconds=get_missing_run_seconds,
                            )

                        if service == 'unifi':
                            username = env.get(f'VRKN_{envsection}_USERNAME', self.config.get(section, 'username'))
                            password = env.get(f'VRKN_{envsection}_PASSWORD', self.config.get(section, 'password'))
                            site = env.get(f'VRKN_{envsection}_SITE', self.config.get(section, 'site')).lower()
                            usg_name = env.get(f'VRKN_{envsection}_USG_NAME', self.config.get(section, 'usg_name'))
                            get_usg_stats_run_seconds = int(
                                env.get(
                                    f'VRKN_{envsection}_GET_USG_STATS_RUN_SECONDS',
                                    self.config.getint(section, 'get_usg_stats_run_seconds'),
                                )
                            )

                            server = UniFiServer(
                                id=server_id,
                                url=scheme + url,
                                verify_ssl=verify_ssl,
                                site=site,
                                username=username,
                                password=password,
                                usg_name=usg_name,
                                get_usg_stats_run_seconds=get_usg_stats_run_seconds,
                            )

                        getattr(self, f'{service}_servers').append(server)
                    except ValueError as e:
                        self.logger.error('Invalid configuration value in %s. Error: %s', section, e)
