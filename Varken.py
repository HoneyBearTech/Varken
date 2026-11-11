# SPDX-FileCopyrightText: 2018 Boerderij
# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
"""Start Varken: read the configuration, schedule the jobs of every enabled service and serve /metrics."""

import platform
import sys
from argparse import ArgumentParser, RawTextHelpFormatter
from logging import DEBUG, Formatter, StreamHandler, getLogger
from os import R_OK, access, getenv
from os import environ as env
from pathlib import Path
from queue import Queue
from threading import Thread
from time import sleep
from typing import TYPE_CHECKING

import schedule
from distro import name as distro_name

from varken import BRANCH, BUILD_DATE, VERSION
from varken.helpers import geoip_handler
from varken.iniparser import INIParser
from varken.lidarr import LidarrAPI
from varken.metrics import Metrics
from varken.ombi import OmbiAPI
from varken.radarr import RadarrAPI
from varken.seerr import SeerrAPI
from varken.sickchill import SickChillAPI
from varken.sonarr import SonarrAPI
from varken.tautulli import TautulliAPI
from varken.unifi import UniFiAPI
from varken.varkenlogger import VarkenLogger

if TYPE_CHECKING:
    from collections.abc import Callable

PLATFORM_LINUX_DISTRO = distro_name(pretty=True)

# The Prometheus output; it runs every job and records its outcome and points.
METRICS = None


def thread(job: Callable[..., object], **kwargs: object) -> None:
    """Run the job in a thread of its own, through the Prometheus output."""
    worker = Thread(target=METRICS.run, args=(job,), kwargs=dict(**kwargs))
    worker.start()


if __name__ == '__main__':
    parser = ArgumentParser(
        prog='varken',
        description='Collects data from the Plex ecosystem and serves it as Prometheus metrics',
        formatter_class=RawTextHelpFormatter,
    )

    parser.add_argument('-d', '--data-folder', help='Define an alternate data folder location')
    parser.add_argument('-D', '--debug', action='store_true', help='Log at DEBUG instead of INFO')
    parser.add_argument(
        '-ND',
        '--no_debug',
        action='store_true',
        help='Log at INFO (the default since 2.3.0; kept so existing scripts still work)',
    )

    opts = parser.parse_args()

    templogger = getLogger('temp')
    templogger.setLevel(DEBUG)
    tempch = StreamHandler()
    tempformatter = Formatter('%(asctime)s : %(levelname)s : %(module)s : %(message)s', '%Y-%m-%d %H:%M:%S')
    tempch.setFormatter(tempformatter)
    templogger.addHandler(tempch)

    DATA_FOLDER = env.get(
        'DATA_FOLDER', vars(opts).get('data_folder') or str(Path(__file__).absolute().parent / 'data')
    )

    if Path(DATA_FOLDER).is_dir():
        if not access(DATA_FOLDER, R_OK):
            templogger.error('Read permission error for %s', DATA_FOLDER)
            sys.exit(1)
    else:
        templogger.error('%s does not exist', DATA_FOLDER)
        sys.exit(1)

    # INFO by default; DEBUG with -D, or with DEBUG=true in the environment (which wins over the flags).
    enable_opts = ['True', 'true', 'yes']
    debug_opts = ['debug', 'Debug', 'DEBUG']

    opts.debug = opts.debug and not opts.no_debug

    if getenv('DEBUG') is not None:
        opts.debug = any(getenv(name) in enable_opts for name in debug_opts)

    # Initiate the logger
    # LOG_TO_FILE=false logs to stdout only, for containers whose logs are collected anyway.
    log_to_file = getenv('LOG_TO_FILE', 'true').lower() not in ['false', 'no']
    vl = VarkenLogger(data_folder=DATA_FOLDER, debug=opts.debug, log_to_file=log_to_file)
    vl.logger.info('Starting Varken...')

    vl.logger.info('Data folder is "%s"', DATA_FOLDER)

    vl.logger.info(
        '%s %s (%s%s)',
        platform.system(),
        platform.release(),
        platform.version(),
        ' - ' + PLATFORM_LINUX_DISTRO if PLATFORM_LINUX_DISTRO else '',
    )

    vl.logger.info('Python %s', sys.version)

    vl.logger.info('Varken v%s-%s %s', VERSION, BRANCH, BUILD_DATE)

    CONFIG = INIParser(DATA_FOLDER)
    METRICS = Metrics(CONFIG.prometheus_server)
    METRICS.start()
    QUEUE = Queue()

    if CONFIG.sonarr_enabled:
        for server in CONFIG.sonarr_servers:
            SONARR = SonarrAPI(server, METRICS)
            if server.queue:
                at_time = schedule.every(server.queue_run_seconds).seconds
                at_time.do(thread, SONARR.get_queue).tag(f'sonarr-{server.id}-get_queue')
            if server.missing_days > 0:
                at_time = schedule.every(server.missing_days_run_seconds).seconds
                at_time.do(thread, SONARR.get_calendar, query='Missing').tag(f'sonarr-{server.id}-get_missing')
            if server.future_days > 0:
                at_time = schedule.every(server.future_days_run_seconds).seconds
                at_time.do(thread, SONARR.get_calendar, query='Future').tag(f'sonarr-{server.id}-get_future')

    if CONFIG.tautulli_enabled:
        GEOIPHANDLER = geoip_handler(
            DATA_FOLDER, CONFIG.tautulli_servers[0].maxmind_license_key, CONFIG.tautulli_servers[0].maxmind_account_id
        )
        schedule.every(12).to(24).hours.do(thread, GEOIPHANDLER.update)
        for server in CONFIG.tautulli_servers:
            TAUTULLI = TautulliAPI(server, METRICS, GEOIPHANDLER)
            if server.get_activity:
                at_time = schedule.every(server.get_activity_run_seconds).seconds
                at_time.do(thread, TAUTULLI.get_activity).tag(f'tautulli-{server.id}-get_activity')
            if server.get_stats:
                at_time = schedule.every(server.get_stats_run_seconds).seconds
                at_time.do(thread, TAUTULLI.get_stats).tag(f'tautulli-{server.id}-get_stats')

    if CONFIG.radarr_enabled:
        for server in CONFIG.radarr_servers:
            RADARR = RadarrAPI(server, METRICS)
            if server.get_missing:
                at_time = schedule.every(server.get_missing_run_seconds).seconds
                at_time.do(thread, RADARR.get_missing).tag(f'radarr-{server.id}-get_missing')
            if server.queue:
                at_time = schedule.every(server.queue_run_seconds).seconds
                at_time.do(thread, RADARR.get_queue).tag(f'radarr-{server.id}-get_queue')

    if CONFIG.lidarr_enabled:
        for server in CONFIG.lidarr_servers:
            LIDARR = LidarrAPI(server, METRICS)
            if server.queue:
                at_time = schedule.every(server.queue_run_seconds).seconds
                at_time.do(thread, LIDARR.get_queue).tag(f'lidarr-{server.id}-get_queue')
            if server.missing_days > 0:
                at_time = schedule.every(server.missing_days_run_seconds).seconds
                at_time.do(thread, LIDARR.get_calendar, query='Missing').tag(f'lidarr-{server.id}-get_missing')
            if server.future_days > 0:
                at_time = schedule.every(server.future_days_run_seconds).seconds
                at_time.do(thread, LIDARR.get_calendar, query='Future').tag(f'lidarr-{server.id}-get_future')

    if CONFIG.ombi_enabled:
        for server in CONFIG.ombi_servers:
            OMBI = OmbiAPI(server, METRICS)
            if server.request_type_counts:
                at_time = schedule.every(server.request_type_run_seconds).seconds
                at_time.do(thread, OMBI.get_request_counts).tag(f'ombi-{server.id}-get_request_counts')
            if server.request_total_counts:
                at_time = schedule.every(server.request_total_run_seconds).seconds
                at_time.do(thread, OMBI.get_all_requests).tag(f'ombi-{server.id}-get_all_requests')
            if server.issue_status_counts:
                at_time = schedule.every(server.issue_status_run_seconds).seconds
                at_time.do(thread, OMBI.get_issue_counts).tag(f'ombi-{server.id}-get_issue_counts')

    if CONFIG.seerr_enabled:
        for server in CONFIG.seerr_servers:
            SEERR = SeerrAPI(server, METRICS)
            for job in ('get_request_counts', 'get_issue_counts', 'get_requests'):
                if getattr(server, job):
                    at_time = schedule.every(getattr(server, f'{job}_run_seconds')).seconds
                    at_time.do(thread, getattr(SEERR, job)).tag(f'seerr-{server.id}-{job}')

    if CONFIG.sickchill_enabled:
        for server in CONFIG.sickchill_servers:
            SICKCHILL = SickChillAPI(server, METRICS)
            if server.get_missing:
                at_time = schedule.every(server.get_missing_run_seconds).seconds
                at_time.do(thread, SICKCHILL.get_missing).tag(f'sickchill-{server.id}-get_missing')

    if CONFIG.unifi_enabled:
        for server in CONFIG.unifi_servers:
            UNIFI = UniFiAPI(server, METRICS)
            at_time = schedule.every(server.get_usg_stats_run_seconds).seconds
            at_time.do(thread, UNIFI.get_usg_stats).tag(f'unifi-{server.id}-get_usg_stats')

    # Run all on startup
    SERVICES_ENABLED = [
        CONFIG.ombi_enabled,
        CONFIG.radarr_enabled,
        CONFIG.tautulli_enabled,
        CONFIG.unifi_enabled,
        CONFIG.sonarr_enabled,
        CONFIG.sickchill_enabled,
        CONFIG.lidarr_enabled,
        CONFIG.seerr_enabled,
    ]
    if not [enabled for enabled in SERVICES_ENABLED if enabled]:
        vl.logger.error('All services disabled. Exiting')
        sys.exit(1)

    schedule.run_all()

    while schedule.jobs:
        schedule.run_pending()
        sleep(1)
