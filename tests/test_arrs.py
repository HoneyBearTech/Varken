"""Sonarr and Radarr (API v3), Lidarr (v1), and the item metrics for Sonarr, Radarr, SickChill and Ombi."""
import pytest

from tests.arrs_data import (ALBUMS, CALENDAR, LIDARR, LIDARR_QUEUE, MOVIES, RADARR, RADARR_QUEUE, SONARR,
                             SONARR_QUEUE, OmbiAPI, SickChillAPI)
from tests.test_metrics import samples, value
from varken import lidarr, radarr, sonarr
from varken.lidarr import LidarrAPI
from varken.metrics import Metrics
from varken.radarr import RadarrAPI
from varken.sonarr import SonarrAPI
from varken.structures import PrometheusServer


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


def test_lidarr_missing_keeps_monitored_albums_without_every_track(metrics, monkeypatch):
    requests = []
    reply_with(monkeypatch, lidarr, ALBUMS, requests)

    # Upstream's loop appended to the list it was walking and crashed on the first incomplete album.
    metrics.run(LidarrAPI(LIDARR, metrics).get_calendar, query='Missing')

    assert requests[0].url.startswith('http://lidarr.example.com:8686/api/v1/calendar?')
    assert 'includeArtist=true' in requests[0].url
    assert value(metrics, 'varken_job_up', service='lidarr', server='1', job='missing') == 1
    tags = [point['tags'] for point in metrics.snapshot()[('lidarr', '1', 'missing')][2]]
    assert [(t['albumName'], t['percentComplete'], t['completeCount']) for t in tags] == [
        ('Half There', 50, '5/10'), ('Not Yet', 0, '0/0')]
    assert value(metrics, 'varken_lidarr_album_info', server='1', kind='missing', artist='A Band', album='Half There',
                 released='2026-10-01T00:00:00Z', tracks='5/10') == 1


def test_lidarr_future_lists_every_album(metrics, monkeypatch):
    reply_with(monkeypatch, lidarr, ALBUMS, [])

    metrics.run(LidarrAPI(LIDARR, metrics).get_calendar, query='Future')

    assert value(metrics, 'varken_job_points', service='lidarr', server='1', job='future') == 3
    assert value(metrics, 'varken_lidarr_album_info', server='1', kind='future', artist='B Band', album='Not Yet',
                 released='2026-10-18T00:00:00Z', tracks='0/0') == 1


def test_lidarr_queue_uses_api_v1_records(metrics, monkeypatch):
    requests = []
    reply_with(monkeypatch, lidarr, LIDARR_QUEUE, requests)

    metrics.run(LidarrAPI(LIDARR, metrics).get_queue)

    assert '/api/v1/queue?' in requests[0].url
    assert 'includeArtist=true' in requests[0].url and 'includeAlbum=true' in requests[0].url
    assert value(metrics, 'varken_job_up', service='lidarr', server='1', job='queue') == 1
    assert value(metrics, 'varken_job_points', service='lidarr', server='1', job='queue') == 2
    assert value(metrics, 'varken_lidarr_queue_item_info', server='1', artist='A Band', album='Half There',
                 release='A.Band-Half.There-FLAC', quality='FLAC', protocol='torrent') == 1
    assert value(metrics, 'varken_lidarr_queue_item_info', server='1', artist='', album='',
                 release='Unknown.Release-MP3', quality='MP3-320', protocol='usenet') == 1


@pytest.mark.parametrize(('job', 'kwargs', 'reply'), [
    ('get_queue', {}, [{'old': 'list'}]),
    ('get_calendar', {'query': 'Missing'}, {'records': []}),
])
def test_an_unexpected_lidarr_reply_marks_the_job_down(metrics, monkeypatch, job, kwargs, reply):
    reply_with(monkeypatch, lidarr, reply, [])

    metrics.run(getattr(LidarrAPI(LIDARR, metrics), job), **kwargs)

    assert value(metrics, 'varken_job_up', service='lidarr', server='1',
                 job=kwargs.get('query', 'queue').lower()) == 0


def test_sickchill_episodes(metrics):
    metrics.run(SickChillAPI(metrics).get_missing)

    assert value(metrics, 'varken_sickchill_episode_info', server='1', show='A Show', episode='S01E02',
                 title='Tonight', airdate='2026-10-15', status='today') == 1
    assert value(metrics, 'varken_sickchill_episode_info', server='1', show='B Show', episode='S03E01',
                 title='Gone', airdate='2026-10-01', status='missed') == 1


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
