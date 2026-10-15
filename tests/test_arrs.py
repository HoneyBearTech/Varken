"""Sonarr and Radarr through their v3 APIs, and the item metrics for Sonarr, Radarr, SickChill and Ombi."""
from types import SimpleNamespace

import pytest

from tests.test_metrics import samples, value
from varken import radarr, sonarr
from varken.metrics import Metrics
from varken.radarr import RadarrAPI
from varken.sonarr import SonarrAPI
from varken.structures import PrometheusServer, RadarrServer, SonarrServer

SONARR = SonarrServer(api_key='sonarr-key', id=1, url='http://sonarr.example.com:8989', missing_days=7,
                      future_days=1, queue=True)
RADARR = RadarrServer(api_key='radarr-key', id=1, url='http://radarr.example.com:7878', queue=True,
                      get_missing=True)

# Shapes of Sonarr 4's /api/v3/calendar?includeSeries=true and /api/v3/queue?includeSeries&includeEpisode
# (trimmed to the fields Varken reads, plus a few it ignores).
CALENDAR = [
    {'id': 11, 'seriesId': 1, 'seasonNumber': 2, 'episodeNumber': 3, 'title': 'An Episode',
     'airDateUtc': '2026-10-14T01:00:00Z', 'hasFile': False, 'monitored': True, 'runtime': 42,
     'series': {'title': 'A Show', 'year': 2024}},
    {'id': 12, 'seriesId': 1, 'seasonNumber': 2, 'episodeNumber': 4, 'title': 'Got It',
     'airDateUtc': '2026-10-13T01:00:00Z', 'hasFile': True, 'monitored': True, 'series': {'title': 'A Show'}},
    {'id': 13, 'seriesId': 2, 'seasonNumber': 1, 'episodeNumber': 1, 'title': 'Unmonitored',
     'airDateUtc': '2026-10-12T01:00:00Z', 'hasFile': False, 'monitored': False, 'series': {'title': 'Other'}},
]
SONARR_QUEUE = {'page': 1, 'pageSize': 1000, 'totalRecords': 2, 'records': [
    {'id': 21, 'protocol': 'usenet', 'status': 'downloading', 'quality': {'quality': {'name': 'WEBDL-1080p'}},
     'series': {'title': 'A Show'}, 'episode': {'seasonNumber': 2, 'episodeNumber': 5, 'title': 'Next One'}},
    # A download Sonarr couldn't match to an episode: skipped, not an error.
    {'id': 22, 'protocol': 'torrent', 'status': 'warning', 'quality': {'quality': {'name': 'Unknown'}}},
]}
MOVIES = [
    {'id': 1, 'title': 'Released Film', 'year': 2025, 'tmdbId': 101, 'titleSlug': 'released-film-2025',
     'monitored': True, 'hasFile': False, 'isAvailable': True},
    {'id': 2, 'title': 'Future Film', 'year': 2027, 'tmdbId': 102, 'titleSlug': 'future-film-2027',
     'monitored': True, 'hasFile': False, 'isAvailable': False},
    {'id': 3, 'title': 'Have It', 'year': 2020, 'tmdbId': 103, 'monitored': True, 'hasFile': True},
    {'id': 4, 'title': 'Not Wanted', 'year': 2019, 'tmdbId': 104, 'monitored': False, 'hasFile': False},
]
RADARR_QUEUE = {'page': 1, 'totalRecords': 1, 'records': [
    {'id': 31, 'protocol': 'torrent', 'quality': {'quality': {'name': 'Bluray-2160p'}},
     'movie': {'title': 'Released Film', 'year': 2025, 'titleSlug': 'released-film-2025'}},
]}


@pytest.fixture
def metrics():
    return Metrics(PrometheusServer())


def reply_with(monkeypatch, module, reply, requests):
    def fake(session, request, verify):
        requests.append(request)
        return reply
    monkeypatch.setattr(module, 'connection_handler', fake)


def test_sonarr_missing_uses_api_v3_and_keeps_monitored_episodes_without_a_file(metrics, monkeypatch):
    requests = []
    reply_with(monkeypatch, sonarr, CALENDAR, requests)

    metrics.run(SonarrAPI(SONARR, metrics).get_calendar, query='Missing')

    assert requests[0].url.startswith('http://sonarr.example.com:8989/api/v3/calendar?')
    assert 'includeSeries=true' in requests[0].url
    assert requests[0].headers['X-Api-Key'] == 'sonarr-key'
    episodes = [dict(labels) for name, labels in samples(metrics) if name == 'varken_sonarr_episode_info']
    assert episodes == [{'server': '1', 'kind': 'missing', 'series': 'A Show', 'episode': 'S02E03',
                         'title': 'An Episode', 'airs': '2026-10-14T01:00:00Z', 'downloaded': 'false'}]


def test_sonarr_future_lists_every_episode_with_whether_it_is_downloaded(metrics, monkeypatch):
    reply_with(monkeypatch, sonarr, CALENDAR, [])

    metrics.run(SonarrAPI(SONARR, metrics).get_calendar, query='Future')

    assert value(metrics, 'varken_job_points', service='sonarr', server='1', job='future') == 3
    assert value(metrics, 'varken_sonarr_episode_info', server='1', kind='future', series='A Show',
                 episode='S02E04', title='Got It', airs='2026-10-13T01:00:00Z', downloaded='true') == 1


def test_sonarr_queue_uses_api_v3_records(metrics, monkeypatch):
    requests = []
    reply_with(monkeypatch, sonarr, SONARR_QUEUE, requests)

    metrics.run(SonarrAPI(SONARR, metrics).get_queue)

    assert '/api/v3/queue?' in requests[0].url
    assert 'includeEpisode=true' in requests[0].url
    assert value(metrics, 'varken_sonarr_queue_item_info', server='1', series='A Show', episode='S02E05',
                 title='Next One', protocol='usenet', quality='WEBDL-1080p') == 1
    assert value(metrics, 'varken_job_up', service='sonarr', server='1', job='queue') == 1
    assert value(metrics, 'varken_job_points', service='sonarr', server='1', job='queue') == 1


def test_an_empty_sonarr_queue_is_up_with_no_items(metrics, monkeypatch):
    reply_with(monkeypatch, sonarr, {'records': []}, [])

    metrics.run(SonarrAPI(SONARR, metrics).get_queue)

    assert value(metrics, 'varken_job_up', service='sonarr', server='1', job='queue') == 1
    assert value(metrics, 'varken_job_points', service='sonarr', server='1', job='queue') == 0


@pytest.mark.parametrize(('job', 'kwargs', 'reply'), [
    ('get_queue', {}, [{'old': 'v2 list'}]),
    ('get_calendar', {'query': 'Missing'}, {'records': []}),
])
def test_an_old_sonarr_reply_marks_the_job_down(metrics, monkeypatch, job, kwargs, reply):
    reply_with(monkeypatch, sonarr, reply, [])

    metrics.run(getattr(SonarrAPI(SONARR, metrics), job), **kwargs)

    assert value(metrics, 'varken_job_up', service='sonarr', server='1',
                 job=kwargs.get('query', 'queue').lower()) == 0


def test_radarr_missing_uses_api_v3_and_marks_released_movies_available(metrics, monkeypatch):
    requests = []
    reply_with(monkeypatch, radarr, MOVIES, requests)

    metrics.run(RadarrAPI(RADARR, metrics).get_missing)

    assert requests[0].url == 'http://radarr.example.com:7878/api/v3/movie'
    missing = sorted((dict(labels)['movie'], dict(labels)['available']) for name, labels in samples(metrics)
                     if name == 'varken_radarr_missing_info')
    assert missing == [('Future Film (2027)', 'false'), ('Released Film (2025)', 'true')]


def test_radarr_queue_uses_api_v3_records(metrics, monkeypatch):
    requests = []
    reply_with(monkeypatch, radarr, RADARR_QUEUE, requests)

    metrics.run(RadarrAPI(RADARR, metrics).get_queue)

    assert '/api/v3/queue?' in requests[0].url
    assert 'includeMovie=true' in requests[0].url
    assert value(metrics, 'varken_radarr_queue_item_info', server='1', movie='Released Film (2025)',
                 quality='Bluray-2160p', protocol='torrent') == 1


def test_an_old_radarr_reply_marks_the_job_down(metrics, monkeypatch):
    reply_with(monkeypatch, radarr, [{'old': 'v2 list'}], [])

    metrics.run(RadarrAPI(RADARR, metrics).get_queue)

    assert value(metrics, 'varken_job_up', service='radarr', server='1', job='queue') == 0


class SickChillAPI:
    server = SimpleNamespace(id=1)

    def __init__(self, output):
        self.output = output

    def get_missing(self):
        self.output.write_points([
            {'measurement': 'SickChill', 'tags': {'type': 3, 'name': 'A Show', 'epname': 'Tonight', 'sxe': 'S01E02',
                                                  'airdate': '2026-10-15', 'server': 1}, 'fields': {}},
            {'measurement': 'SickChill', 'tags': {'type': 4, 'name': 'B Show', 'epname': 'Gone', 'sxe': 'S03E01',
                                                  'airdate': '2026-10-01', 'server': 1}, 'fields': {}},
        ])


def test_sickchill_episodes(metrics):
    metrics.run(SickChillAPI(metrics).get_missing)

    assert value(metrics, 'varken_sickchill_episode_info', server='1', show='A Show', episode='S01E02',
                 title='Tonight', airdate='2026-10-15', status='today') == 1
    assert value(metrics, 'varken_sickchill_episode_info', server='1', show='B Show', episode='S03E01',
                 title='Gone', airdate='2026-10-01', status='missed') == 1


class OmbiAPI:
    """Writes the points the real Ombi module writes."""
    server = SimpleNamespace(id=1)

    def __init__(self, output):
        self.output = output

    def get_request_counts(self):
        self.output.write_points([{'measurement': 'Ombi', 'tags': {'type': 'Request_Counts'},
                                   'fields': {'pending': 3, 'approved': 2, 'available': 40}}])

    def get_issue_counts(self):
        self.output.write_points([{'measurement': 'Ombi', 'tags': {'type': 'Issues_Counts'},
                                   'fields': {'pending': 1, 'in_progress': 0, 'resolved': 9}}])

    def get_all_requests(self):
        self.output.write_points([
            {'measurement': 'Ombi', 'tags': {'type': 'Request_Total', 'server': 1},
             'fields': {'total': 2, 'movies': 1, 'tv_shows': 1}},
            {'measurement': 'Ombi', 'tags': {'type': 'Requests', 'server': 1, 'request_type': 1, 'status': 3,
                                             'title': 'A Film', 'requested_user': 'someone',
                                             'requested_date': '2026-10-10T12:00:00'}, 'fields': {}},
            {'measurement': 'Ombi', 'tags': {'type': 'Requests', 'server': 1, 'request_type': 0, 'status': 2,
                                             'title': 'A Show', 'requested_user': 'someone',
                                             'requested_date': '2026-10-01T08:00:00'}, 'fields': {}},
        ])


def test_ombi_counts(metrics):
    api = OmbiAPI(metrics)
    metrics.run(api.get_request_counts)
    metrics.run(api.get_issue_counts)

    assert value(metrics, 'varken_ombi_requests', server='1', status='pending') == 3
    assert value(metrics, 'varken_ombi_requests', server='1', status='available') == 40
    assert value(metrics, 'varken_ombi_issues', server='1', status='in_progress') == 0
    assert value(metrics, 'varken_ombi_issues', server='1', status='resolved') == 9


def test_ombi_requests_keep_the_requester_out_by_default(metrics):
    metrics.run(OmbiAPI(metrics).get_all_requests)

    assert value(metrics, 'varken_ombi_request_info', server='1', type='movie', title='A Film', status='pending',
                 requested='2026-10-10T12:00:00', user='') == 1
    assert value(metrics, 'varken_ombi_request_info', server='1', type='tv', title='A Show', status='available',
                 requested='2026-10-01T08:00:00', user='') == 1


def test_ombi_requests_name_the_requester_with_stream_details():
    metrics = Metrics(PrometheusServer(stream_details=True))

    metrics.run(OmbiAPI(metrics).get_all_requests)

    assert value(metrics, 'varken_ombi_request_info', server='1', type='movie', title='A Film', status='pending',
                 requested='2026-10-10T12:00:00', user='someone') == 1
