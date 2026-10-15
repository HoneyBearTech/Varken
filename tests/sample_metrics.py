"""Print a /metrics scrape with every Varken metric in it, for CI's `promtool check metrics`.

Run from the repository root:  python -m tests.sample_metrics
"""
from prometheus_client import generate_latest

from tests.tautulli_data import ACTIVITY, LIBRARIES, SERVER, FakeGeoIP, place
from varken import tautulli
from varken.metrics import Metrics
from varken.structures import PrometheusServer
from varken.tautulli import TautulliAPI


def sample():
    metrics = Metrics(PrometheusServer(stream_details=True))
    api = TautulliAPI(SERVER, metrics, FakeGeoIP({'203.0.113.5': place()}))
    for reply, job in ((ACTIVITY, api.get_activity), (LIBRARIES, api.get_stats)):
        tautulli.connection_handler = lambda session, request, verify, reply=reply: reply
        metrics.run(job)
    return generate_latest(metrics.registry).decode()


if __name__ == '__main__':
    print(sample(), end='')
