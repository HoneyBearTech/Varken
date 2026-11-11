# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
"""Ombi: the request and issue counts, and each request."""

from typing import Any

import pytest

from tests.fakes import answer_by_path
from tests.tautulli_data import FakeOutput
from tests.test_metrics import samples, value
from varken import ombi
from varken.metrics import Metrics
from varken.ombi import OmbiAPI
from varken.structures import OmbiServer, PrometheusServer

OMBI = OmbiServer(api_key='ombi-key', id=1, url='http://ombi.example.com:5000')
TV = '/api/v1/Request/tv'
MOVIE = '/api/v1/Request/movie'


def movie(title: str, **state: bool) -> dict[str, Any]:
    return {
        'id': len(title),
        'theMovieDbId': 603,
        'title': title,
        'approved': False,
        'available': False,
        'denied': False,
        'requestedUser': {'userAlias': 'ann'},
        'requestedDate': '2026-10-01T10:00:00',
        **state,
    }


MOVIES = [
    movie('Pending Film'),
    movie('Approved Film', approved=True),
    movie('Available Film', approved=True, available=True),
    movie('Denied Film', denied=True),
]
SHOWS = [
    {
        'id': 9,
        'tvDbId': 121361,
        'title': 'Available Show',
        'childRequests': [
            {
                'approved': True,
                'available': True,
                'denied': False,
                'requestedUser': {'userAlias': 'bob'},
                'requestedDate': '2026-10-02T10:00:00',
            }
        ],
    }
]


def requests_in(metrics: Metrics) -> dict[str, dict[str, str]]:
    """Each request's labels, by its title."""
    return {
        dict(labels)['title']: dict(labels) for name, labels in samples(metrics) if name == 'varken_ombi_request_info'
    }


def test_all_requests_lists_each_request_with_its_status(monkeypatch: pytest.MonkeyPatch) -> None:
    made = answer_by_path(monkeypatch, ombi, {TV: SHOWS, MOVIE: MOVIES})
    metrics = Metrics(PrometheusServer(stream_details=True))

    metrics.run(OmbiAPI(OMBI, metrics).get_all_requests)

    assert [request.url for request in made] == [
        f'http://ombi.example.com:5000{TV}',
        f'http://ombi.example.com:5000{MOVIE}',
    ]
    assert all(request.headers['Apikey'] == 'ombi-key' for request in made)
    assert value(metrics, 'varken_job_up', service='ombi', server='1', job='all_requests') == 1
    requests = requests_in(metrics)
    assert {title: labels['status'] for title, labels in requests.items()} == {
        'Pending Film': 'pending',
        'Approved Film': 'approved',
        'Available Film': 'available',
        'Denied Film': 'denied',
        'Available Show': 'available',
    }
    assert requests['Approved Film'] == {
        'server': '1',
        'type': 'movie',
        'title': 'Approved Film',
        'status': 'approved',
        'requested': '2026-10-01T10:00:00',
        'user': 'ann',
    }
    assert requests['Available Show']['type'] == 'tv'
    assert requests['Available Show']['user'] == 'bob'


def test_the_requester_is_left_out_without_stream_details(monkeypatch: pytest.MonkeyPatch) -> None:
    answer_by_path(monkeypatch, ombi, {TV: SHOWS, MOVIE: MOVIES})
    metrics = Metrics(PrometheusServer())

    metrics.run(OmbiAPI(OMBI, metrics).get_all_requests)

    assert {labels['user'] for labels in requests_in(metrics).values()} == {''}


@pytest.mark.parametrize(
    ('routes', 'totals'),
    [
        ({TV: SHOWS, MOVIE: MOVIES}, {'total': 5, 'movies': 4, 'tv_shows': 1}),
        ({TV: SHOWS}, {'total': 1, 'movies': 0, 'tv_shows': 1}),
        ({MOVIE: MOVIES}, {'total': 4, 'movies': 4, 'tv_shows': 0}),
    ],
)
def test_all_requests_counts_the_lists_it_got(
    monkeypatch: pytest.MonkeyPatch, routes: dict[str, object], totals: dict[str, int]
) -> None:
    # A list whose request failed counts as empty; the failed request itself marks the job down.
    answer_by_path(monkeypatch, ombi, routes)
    output = FakeOutput()

    OmbiAPI(OMBI, output).get_all_requests()

    assert output.points[0]['tags'] == {'type': 'Request_Total', 'server': 1}
    assert output.points[0]['fields'] == totals
    assert len(output.points) == 1 + totals['total']


def test_all_requests_writes_nothing_when_ombi_does_not_answer(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    answer_by_path(monkeypatch, ombi, {})
    output = FakeOutput()

    OmbiAPI(OMBI, output).get_all_requests()

    assert output.points == []
    assert 'No json replies. Discarding job' in caplog.text


def test_a_request_with_a_field_varken_does_not_know_is_logged_and_left_out(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    answer_by_path(monkeypatch, ombi, {MOVIE: [*MOVIES, {**movie('New Film'), 'aFieldOfANewerOmbi': 1}]})
    output = FakeOutput()

    OmbiAPI(OMBI, output).get_all_requests()

    assert 'while creating OmbiMovieRequest structure' in caplog.text
    assert [point['tags']['title'] for point in output.points[1:]] == [film['title'] for film in MOVIES]


def test_request_and_issue_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    made = answer_by_path(
        monkeypatch,
        ombi,
        {
            '/api/v1/Request/count': {'pending': 3, 'approved': 2, 'available': 40},
            '/api/v1/Issues/count': {'pending': 1, 'inProgress': 2, 'resolved': 5},
        },
    )
    metrics = Metrics(PrometheusServer())
    api = OmbiAPI(OMBI, metrics)

    metrics.run(api.get_request_counts)
    metrics.run(api.get_issue_counts)

    assert [request.url for request in made] == [
        'http://ombi.example.com:5000/api/v1/Request/count',
        'http://ombi.example.com:5000/api/v1/Issues/count',
    ]
    assert value(metrics, 'varken_ombi_requests', server='1', status='pending') == 3
    assert value(metrics, 'varken_ombi_requests', server='1', status='available') == 40
    assert value(metrics, 'varken_ombi_issues', server='1', status='in_progress') == 2
    assert value(metrics, 'varken_ombi_issues', server='1', status='resolved') == 5


@pytest.mark.parametrize('job', ['get_request_counts', 'get_issue_counts'])
def test_counts_write_nothing_and_mark_the_job_down_when_ombi_does_not_answer(
    monkeypatch: pytest.MonkeyPatch, job: str
) -> None:
    answer_by_path(monkeypatch, ombi, {})
    metrics = Metrics(PrometheusServer())

    metrics.run(getattr(OmbiAPI(OMBI, metrics), job))

    assert value(metrics, 'varken_job_up', service='ombi', server='1', job=job.removeprefix('get_')) == 0
    assert not [name for name, _ in samples(metrics) if name in ('varken_ombi_requests', 'varken_ombi_issues')]
