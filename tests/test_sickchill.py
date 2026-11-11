# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
"""SickChill: the episodes on its coming-episodes list."""

from typing import TYPE_CHECKING, Any

from tests.fakes import answer_by_path
from tests.test_metrics import samples, value
from varken import sickchill
from varken.metrics import Metrics
from varken.sickchill import SickChillAPI
from varken.structures import PrometheusServer, SickChillServer

if TYPE_CHECKING:
    import pytest

SICKCHILL = SickChillServer(api_key='sickchill-key', id=1, url='http://sickchill.example.com:8081')
PATH = '/api/sickchill-key'


def episode(show: str, name: str, number: int, airdate: str) -> dict[str, Any]:
    return {
        'airdate': airdate,
        'airs': 'Thursday 9:00 PM',
        'episode': number,
        'ep_name': name,
        'ep_plot': '',
        'indexerid': 121361,
        'network': 'A Network',
        'paused': 0,
        'quality': 'HD1080p',
        'season': 1,
        'show_name': show,
        'show_status': 'Continuing',
        'tvdbid': 121361,
        'weekday': 4,
    }


def coming(**sections: list[dict[str, Any]]) -> dict[str, Any]:
    """SickChill's reply: a new one each time, since the module turns its episodes into structures in place."""
    return {
        'data': {
            'missed': [episode('B Show', 'Gone', 1, '2026-10-01')],
            'today': [episode('A Show', 'Tonight', 2, '2026-10-15')],
            'soon': [],
            'later': [episode('A Show', 'Next', 12, '2026-11-15')],
            **sections,
        }
    }


def episodes(metrics: Metrics) -> list[dict[str, str]]:
    return sorted(
        (dict(labels) for name, labels in samples(metrics) if name == 'varken_sickchill_episode_info'),
        key=lambda labels: labels['airdate'],
    )


def test_missing_lists_each_coming_episode_with_its_status(monkeypatch: pytest.MonkeyPatch) -> None:
    made = answer_by_path(monkeypatch, sickchill, {PATH: coming()})
    metrics = Metrics(PrometheusServer())

    metrics.run(SickChillAPI(SICKCHILL, metrics).get_missing)

    assert made[0].url.startswith(f'http://sickchill.example.com:8081{PATH}?')
    assert 'cmd=future' in made[0].url
    assert value(metrics, 'varken_job_up', service='sickchill', server='1', job='missing') == 1
    assert episodes(metrics) == [
        {
            'server': '1',
            'show': 'B Show',
            'episode': 'S01E01',
            'title': 'Gone',
            'airdate': '2026-10-01',
            'status': 'missed',
        },
        {
            'server': '1',
            'show': 'A Show',
            'episode': 'S01E02',
            'title': 'Tonight',
            'airdate': '2026-10-15',
            'status': 'today',
        },
        {
            'server': '1',
            'show': 'A Show',
            'episode': 'S01E12',
            'title': 'Next',
            'airdate': '2026-11-15',
            'status': 'later',
        },
    ]


def test_a_section_varken_does_not_know_is_logged_and_marks_the_job_down(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # SickChill answers with a "snatched" section when asked for it; the module has no status for one.
    reply = coming(snatched=[episode('C Show', 'Found', 3, '2026-10-10')])
    answer_by_path(monkeypatch, sickchill, {PATH: reply})
    metrics = Metrics(PrometheusServer())

    metrics.run(SickChillAPI(SICKCHILL, metrics).get_missing)

    assert 'Error building payload for sickchill. Discarding. Error: list index out of range' in caplog.text
    assert value(metrics, 'varken_job_up', service='sickchill', server='1', job='missing') == 0
    assert episodes(metrics) == []


def test_an_episode_with_a_field_varken_does_not_know_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    reply = {'data': {'today': [{**episode('A Show', 'Tonight', 2, '2026-10-15'), 'a_field_of_a_newer_sickchill': 1}]}}
    answer_by_path(monkeypatch, sickchill, {PATH: reply})
    metrics = Metrics(PrometheusServer())

    metrics.run(SickChillAPI(SICKCHILL, metrics).get_missing)

    assert 'while creating SickChillTVShow structure' in caplog.text
    assert episodes(metrics) == []


def test_missing_writes_nothing_and_marks_the_job_down_when_sickchill_does_not_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answer_by_path(monkeypatch, sickchill, {})
    metrics = Metrics(PrometheusServer())

    metrics.run(SickChillAPI(SICKCHILL, metrics).get_missing)

    assert value(metrics, 'varken_job_up', service='sickchill', server='1', job='missing') == 0
    assert episodes(metrics) == []
