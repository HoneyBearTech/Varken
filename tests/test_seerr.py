"""Seerr: request and issue counts, and the requests still waiting."""
from urllib.parse import urlsplit

import pytest

from tests.seerr_data import SEERR, replies
from tests.test_metrics import samples, value
from varken import seerr
from varken.metrics import Metrics
from varken.seerr import SeerrAPI
from varken.structures import PrometheusServer


@pytest.fixture
def metrics():
    return Metrics(PrometheusServer())


def answer(monkeypatch, routes):
    """Make Seerr answer each request by its path; return the requests made."""
    made = []

    def fake(session, request, verify):
        made.append(request)
        reply = routes.get(urlsplit(request.url).path, False)
        if reply is False:
            seerr.request_state.failed = True
        return reply
    monkeypatch.setattr(seerr, 'connection_handler', fake)
    return made


def test_request_counts(metrics, monkeypatch):
    made = answer(monkeypatch, replies())

    metrics.run(SeerrAPI(SEERR, metrics).get_request_counts)

    assert made[0].url == 'http://seerr.example.com:5055/api/v1/request/count'
    assert made[0].headers['X-Api-Key'] == 'seerr-key'
    assert value(metrics, 'varken_seerr_requests', server='1', status='pending') == 2
    assert value(metrics, 'varken_seerr_requests', server='1', status='processing') == 3
    assert value(metrics, 'varken_seerr_requests', server='1', status='completed') == 0
    assert value(metrics, 'varken_seerr_requests_by_type', server='1', type='tv') == 4
    assert value(metrics, 'varken_job_up', service='seerr', server='1', job='request_counts') == 1


def test_issue_counts(metrics, monkeypatch):
    answer(monkeypatch, replies())

    metrics.run(SeerrAPI(SEERR, metrics).get_issue_counts)

    assert value(metrics, 'varken_seerr_issues', server='1', status='open') == 3
    assert value(metrics, 'varken_seerr_issues', server='1', status='closed') == 2
    assert value(metrics, 'varken_seerr_issues_by_type', server='1', type='other') == 1


def waiting(metrics):
    return sorted((dict(labels) for name, labels in samples(metrics) if name == 'varken_seerr_request_info'),
                  key=lambda labels: labels['title'])


def test_requests_lists_the_ones_still_waiting_without_the_requester(metrics, monkeypatch):
    made = answer(monkeypatch, replies())

    metrics.run(SeerrAPI(SEERR, metrics).get_requests)

    assert made[0].url.startswith('http://seerr.example.com:5055/api/v1/request?')
    assert 'take=100' in made[0].url
    assert waiting(metrics) == [
        {'server': '1', 'type': 'tv', 'title': 'Game of Thrones (2011)', 'status': 'processing', 'is4k': 'true',
         'requested': '2026-10-14T08:00:00.000Z', 'user': ''},
        {'server': '1', 'type': 'movie', 'title': 'The Matrix (1999)', 'status': 'pending', 'is4k': 'false',
         'requested': '2026-10-15T20:00:00.000Z', 'user': ''},
    ]
    assert value(metrics, 'varken_job_up', service='seerr', server='1', job='requests') == 1


def test_requests_name_the_requester_with_stream_details_and_never_their_email(monkeypatch):
    metrics = Metrics(PrometheusServer(stream_details=True))
    answer(monkeypatch, replies())

    metrics.run(SeerrAPI(SEERR, metrics).get_requests)

    assert [labels['user'] for labels in waiting(metrics)] == ['Bob', 'Alice']
    assert 'example.com' not in repr(metrics.snapshot())


def test_titles_are_looked_up_once(metrics, monkeypatch):
    made = answer(monkeypatch, replies())
    api = SeerrAPI(SEERR, metrics)

    metrics.run(api.get_requests)
    metrics.run(api.get_requests)

    lookups = [r.url for r in made if '/movie/' in r.url or '/tv/' in r.url]
    assert sorted(lookups) == ['http://seerr.example.com:5055/api/v1/movie/603',
                               'http://seerr.example.com:5055/api/v1/tv/1399']


def test_a_failed_title_lookup_lists_the_tmdb_id_and_keeps_the_run_up(metrics, monkeypatch):
    routes = replies()
    del routes['/api/v1/movie/603']
    answer(monkeypatch, routes)

    metrics.run(SeerrAPI(SEERR, metrics).get_requests)

    assert [labels['title'] for labels in waiting(metrics)] == ['Game of Thrones (2011)', 'TMDB 603']
    assert value(metrics, 'varken_job_up', service='seerr', server='1', job='requests') == 1


@pytest.mark.parametrize(('job', 'path', 'reply'), [
    ('get_request_counts', '/api/v1/request/count', ['not', 'counts']),
    ('get_issue_counts', '/api/v1/issue/count', {'open': 'three'}),
    ('get_requests', '/api/v1/request', {'results': 'none'}),
])
def test_an_unexpected_reply_marks_the_job_down(metrics, monkeypatch, job, path, reply):
    answer(monkeypatch, replies({path: reply}))

    metrics.run(getattr(SeerrAPI(SEERR, metrics), job))

    assert value(metrics, 'varken_job_up', service='seerr', server='1', job=job.removeprefix('get_')) == 0


def test_seerr_unreachable_marks_the_job_down(metrics, monkeypatch):
    answer(monkeypatch, {})

    metrics.run(SeerrAPI(SEERR, metrics).get_request_counts)

    assert value(metrics, 'varken_job_up', service='seerr', server='1', job='request_counts') == 0
