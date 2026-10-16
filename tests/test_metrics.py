# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
import socket
from logging import getLogger
from types import SimpleNamespace
from urllib.request import urlopen

import pytest
from prometheus_client import generate_latest
from prometheus_client.parser import text_string_to_metric_families

from tests.tautulli_data import ACTIVITY, LIBRARIES, SERVER, FakeGeoIP, place
from varken import helpers, tautulli
from varken.helpers import GeoIPHandler
from varken.metrics import Metrics, job_key
from varken.structures import PrometheusServer
from varken.tautulli import TautulliAPI


class SonarrAPI:
    def __init__(self, output, points=(), fail=False):
        self.server = SimpleNamespace(id=2)
        self.output = output
        self.points = list(points)
        self.fail = fail

    def get_calendar(self, query='Missing'):
        if self.fail:
            helpers.request_state.failed = True
            return
        self.output.write_points(self.points)

    def get_queue(self):
        raise RuntimeError('the job broke')


def samples(metrics):
    """{(name, frozenset(labels)): value} from a scrape, the way Prometheus would parse it."""
    text = generate_latest(metrics.registry).decode()
    return {(sample.name, frozenset(sample.labels.items())): sample.value
            for family in text_string_to_metric_families(text) for sample in family.samples}


def value(metrics, name, **labels):
    return samples(metrics).get((name, frozenset(labels.items())))


def names(metrics):
    return {name for name, _ in samples(metrics)}


@pytest.fixture
def metrics():
    return Metrics(PrometheusServer())


def test_job_key_names_the_service_server_and_job(metrics):
    api = SonarrAPI(None)
    assert job_key(api.get_calendar, {'query': 'Missing'}) == ('sonarr', '2', 'missing')
    assert job_key(api.get_queue, {}) == ('sonarr', '2', 'queue')
    assert job_key(GeoIPHandler.__new__(GeoIPHandler).update, {}) is None


def test_a_successful_job_is_up_and_counts_its_points(metrics):
    api = SonarrAPI(metrics, points=[{'measurement': 'Sonarr'}] * 3)

    metrics.run(api.get_calendar, query='Missing')

    job = {'service': 'sonarr', 'server': '2', 'job': 'missing'}
    assert value(metrics, 'varken_job_up', **job) == 1
    assert value(metrics, 'varken_job_points', **job) == 3
    assert value(metrics, 'varken_job_last_success_timestamp_seconds', **job) > 0


def test_a_job_that_finds_nothing_reports_zero_items(metrics):
    metrics.run(SonarrAPI(metrics).get_calendar, query='Future')

    assert value(metrics, 'varken_job_points', service='sonarr', server='2', job='future') == 0


def test_a_failed_request_marks_the_job_down_and_drops_its_data(metrics):
    metrics.run(SonarrAPI(metrics, points=[{}]).get_calendar, query='Missing')
    last_success = value(metrics, 'varken_job_last_success_timestamp_seconds', service='sonarr', server='2',
                         job='missing')

    metrics.run(SonarrAPI(metrics, fail=True).get_calendar, query='Missing')

    job = {'service': 'sonarr', 'server': '2', 'job': 'missing'}
    assert value(metrics, 'varken_job_up', **job) == 0
    assert value(metrics, 'varken_job_points', **job) is None
    assert value(metrics, 'varken_job_last_success_timestamp_seconds', **job) == last_success


def test_a_job_that_raises_is_marked_down(metrics):
    with pytest.raises(RuntimeError):
        metrics.run(SonarrAPI(metrics).get_queue)

    assert value(metrics, 'varken_job_up', service='sonarr', server='2', job='queue') == 0


def test_points_written_outside_a_job_are_ignored(metrics):
    metrics.write_points([{'measurement': 'Tautulli'}])

    assert value(metrics, 'varken_job_up', service='tautulli', server='1', job='activity') is None


def test_jobs_that_are_not_module_jobs_run_without_being_recorded(metrics):
    ran = []
    metrics.run(lambda: ran.append(True))

    assert ran == [True]
    assert metrics.snapshot() == {}


def test_build_info(metrics):
    assert value(metrics, 'varken_build_info', version='0.0.0', branch='develop') == 1


def run_tautulli(metrics, monkeypatch, reply, job):
    monkeypatch.setattr(tautulli, 'connection_handler', lambda session, request, verify: reply)
    api = TautulliAPI(SERVER, metrics, FakeGeoIP({'203.0.113.5': place()}))
    metrics.run(getattr(api, job))


def test_tautulli_activity(metrics, monkeypatch):
    run_tautulli(metrics, monkeypatch, ACTIVITY, 'get_activity')

    assert value(metrics, 'varken_tautulli_streams', server='1') == 1
    assert value(metrics, 'varken_tautulli_streams_by_decision', server='1', decision='direct_stream') == 1
    assert value(metrics, 'varken_tautulli_streams_by_decision', server='1', decision='transcode') == 0
    assert value(metrics, 'varken_tautulli_bandwidth_bytes_per_second', server='1', network='total') == 1_000_000
    assert value(metrics, 'varken_tautulli_bandwidth_bytes_per_second', server='1', network='wan') == 0
    assert value(metrics, 'varken_tautulli_sessions', server='1', state='paused', media_type='episode',
                 transcode_decision='direct_stream', video_decision='transcode', quality='1080p',
                 platform='Windows') == 1
    assert value(metrics, 'varken_job_points', service='tautulli', server='1', job='activity') == 2


def test_tautulli_activity_keeps_viewers_out_by_default(metrics, monkeypatch):
    run_tautulli(metrics, monkeypatch, ACTIVITY, 'get_activity')

    text = generate_latest(metrics.registry).decode()
    assert 'varken_tautulli_session_info' not in text
    assert 'viewer' not in text
    assert 'Springfield' not in text
    assert 'Pilot' not in text


def test_tautulli_stream_details_when_enabled(monkeypatch):
    metrics = Metrics(PrometheusServer(stream_details=True))

    run_tautulli(metrics, monkeypatch, ACTIVITY, 'get_activity')

    assert value(metrics, 'varken_tautulli_session_info', server='1', session_id='abc', user='viewer',
                 friendly_name='Viewer', title='Some Show - Pilot', product='Plex Web', product_version='4.1',
                 platform='Windows', quality='1080p', quality_profile='Original',
                 transcode_decision='direct_stream', video_decision='transcode', state='paused',
                 location='Springfield', full_location='Illinois - Springfield', region_code='IL',
                 latitude='39.8', longitude='-89.6') == 1
    assert value(metrics, 'varken_tautulli_session_progress_ratio', server='1', session_id='abc') == 0.42
    assert '203.0.113.5' not in generate_latest(metrics.registry).decode()


def test_tautulli_streams_disappear_when_tautulli_is_unreachable(metrics, monkeypatch):
    run_tautulli(metrics, monkeypatch, ACTIVITY, 'get_activity')

    def unreachable(session, request, verify):
        helpers.request_state.failed = True
        return False
    monkeypatch.setattr(tautulli, 'connection_handler', unreachable)
    api = TautulliAPI(SERVER, metrics, FakeGeoIP({}))
    metrics.run(api.get_activity)

    assert 'varken_tautulli_streams' not in names(metrics)
    assert value(metrics, 'varken_job_up', service='tautulli', server='1', job='activity') == 0


def test_tautulli_libraries(metrics, monkeypatch):
    run_tautulli(metrics, monkeypatch, LIBRARIES, 'get_stats')

    assert value(metrics, 'varken_tautulli_library_items', server='1', library='Movies', type='movie',
                 item='total') == 10
    assert value(metrics, 'varken_tautulli_library_items', server='1', library='TV', type='show',
                 item='episodes') == 40
    assert value(metrics, 'varken_tautulli_library_items', server='1', library='Music', type='artist',
                 item='tracks') == 30


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def test_serves_metrics_over_http():
    port = free_port()
    metrics = Metrics(PrometheusServer(bind='127.0.0.1', port=port))

    metrics.start()

    with urlopen(f'http://127.0.0.1:{port}/metrics', timeout=5) as response:  # noqa: S310 -- the test's own server
        assert b'varken_build_info' in response.read()


def test_a_job_that_logs_an_error_is_marked_down(metrics):
    # Regression: a reply the module couldn't parse was only logged, so the job looked healthy.
    class RadarrAPI:
        server = SimpleNamespace(id=1)

        def get_queue(self):
            getLogger().error('TypeError has occurred while creating the Queue structure')

    metrics.run(RadarrAPI().get_queue)

    assert value(metrics, 'varken_job_up', service='radarr', server='1', job='queue') == 0


def test_errors_logged_outside_a_job_change_nothing(metrics):
    getLogger().error('the GeoIP update failed')

    assert metrics.snapshot() == {}


def test_the_ci_sample_has_every_metric():
    from tests.sample_metrics import sample

    text = sample()
    for name in ('varken_build_info', 'varken_job_up', 'varken_job_last_success_timestamp_seconds',
                 'varken_job_points', 'varken_tautulli_streams', 'varken_tautulli_streams_by_decision',
                 'varken_tautulli_bandwidth_bytes_per_second', 'varken_tautulli_sessions',
                 'varken_tautulli_library_items', 'varken_tautulli_session_info',
                 'varken_tautulli_session_progress_ratio', 'varken_sonarr_queue_item_info',
                 'varken_sonarr_episode_info', 'varken_radarr_queue_item_info', 'varken_radarr_missing_info',
                 'varken_sickchill_episode_info',
                 'varken_lidarr_queue_item_info', 'varken_lidarr_album_info', 'varken_ombi_requests',
                 'varken_ombi_issues',
                 'varken_ombi_request_info', 'varken_seerr_requests', 'varken_seerr_requests_by_type',
                 'varken_seerr_issues', 'varken_seerr_issues_by_type', 'varken_seerr_request_info'):
        assert f'\n{name}{{' in text, name
    for job in ('activity', 'stats', 'queue', 'missing', 'future', 'request_counts', 'issue_counts',
                'all_requests', 'requests'):
        assert f'job="{job}"' in text, job
    up = [line for line in text.splitlines() if line.startswith('varken_job_up{')]
    assert len(up) == 17 and all(line.endswith(' 1.0') for line in up), up


def test_a_port_in_use_exits_cleanly():
    with socket.socket() as taken:
        taken.bind(('127.0.0.1', 0))
        taken.listen()
        port = taken.getsockname()[1]
        with pytest.raises(SystemExit):
            Metrics(PrometheusServer(bind='127.0.0.1', port=port)).start()


def test_an_unlocated_viewer_has_no_place_on_the_map(monkeypatch):
    # The Tautulli module records an alien and Area 51 for viewers it can't place; the metrics leave them empty.
    from varken.helpers import NoGeoIP
    metrics = Metrics(PrometheusServer(stream_details=True))
    monkeypatch.setattr(tautulli, 'connection_handler', lambda session, request, verify: ACTIVITY)
    metrics.run(TautulliAPI(SERVER, metrics, NoGeoIP()).get_activity)

    (labels,) = [dict(labels) for name, labels in samples(metrics) if name == 'varken_tautulli_session_info']
    assert (labels['location'], labels['latitude'], labels['longitude'], labels['full_location']) == ('', '', '', '')

