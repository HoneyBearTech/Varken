"""Print a /metrics scrape with every Varken metric in it, for CI's `promtool check metrics`.

Run from the repository root:  python -m tests.sample_metrics
"""
from urllib.parse import urlsplit

from prometheus_client import generate_latest

from tests.arrs_data import (ALBUMS, CALENDAR, LIDARR, LIDARR_QUEUE, MOVIES, RADARR, RADARR_QUEUE, SONARR,
                             SONARR_QUEUE, OmbiAPI, SickChillAPI)
from tests.seerr_data import SEERR, replies as seerr_replies
from tests.tautulli_data import ACTIVITY, LIBRARIES, SERVER, FakeGeoIP, place
from varken import lidarr, radarr, seerr, sonarr, tautulli
from varken.metrics import Metrics
from varken.lidarr import LidarrAPI
from varken.radarr import RadarrAPI
from varken.seerr import SeerrAPI
from varken.sonarr import SonarrAPI
from varken.structures import PrometheusServer
from varken.tautulli import TautulliAPI


def sample():
    metrics = Metrics(PrometheusServer(stream_details=True))
    api = TautulliAPI(SERVER, metrics, FakeGeoIP({'203.0.113.5': place()}))
    sonarr_api, radarr_api = SonarrAPI(SONARR, metrics), RadarrAPI(RADARR, metrics)
    lidarr_api = LidarrAPI(LIDARR, metrics)
    ombi = OmbiAPI(metrics)
    handlers = {module: module.connection_handler for module in (tautulli, sonarr, radarr, lidarr, seerr)}
    try:
        for module, reply, job, kwargs in (
                (tautulli, ACTIVITY, api.get_activity, {}),
                (tautulli, LIBRARIES, api.get_stats, {}),
                (sonarr, SONARR_QUEUE, sonarr_api.get_queue, {}),
                (sonarr, CALENDAR, sonarr_api.get_calendar, {'query': 'Missing'}),
                (sonarr, CALENDAR, sonarr_api.get_calendar, {'query': 'Future'}),
                (radarr, RADARR_QUEUE, radarr_api.get_queue, {}),
                (radarr, MOVIES, radarr_api.get_missing, {}),
                (lidarr, LIDARR_QUEUE, lidarr_api.get_queue, {}),
                (lidarr, ALBUMS, lidarr_api.get_calendar, {'query': 'Missing'}),
                (lidarr, ALBUMS, lidarr_api.get_calendar, {'query': 'Future'})):
            module.connection_handler = lambda session, request, verify, reply=reply: reply
            metrics.run(job, **kwargs)
        routes = seerr_replies()
        seerr.connection_handler = lambda session, request, verify: routes[urlsplit(request.url).path]
        seerr_api = SeerrAPI(SEERR, metrics)
        for job in (seerr_api.get_request_counts, seerr_api.get_issue_counts, seerr_api.get_requests):
            metrics.run(job)
    finally:
        for module, handler in handlers.items():
            module.connection_handler = handler
    for job in (SickChillAPI(metrics).get_missing, ombi.get_request_counts, ombi.get_issue_counts,
                ombi.get_all_requests):
        metrics.run(job)
    return generate_latest(metrics.registry).decode()


if __name__ == '__main__':
    print(sample(), end='')
