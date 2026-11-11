# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
"""UniFi: signing in, finding the site, and the gateway's traffic and load."""

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from tests.fakes import answer_by_path
from tests.tautulli_data import FakeOutput
from varken import unifi
from varken.structures import UniFiServer
from varken.unifi import UniFiAPI

if TYPE_CHECKING:
    import pytest

UNIFI = UniFiServer(
    id=1,
    url='https://unifi.example.com:8443',
    username='varken',
    password='unifi-secret-password',
    site='home',
    usg_name='gateway',
    verify_ssl=True,
)
LOGIN = '/api/login'
SITES = '/api/self/sites'
DEVICES = '/api/s/default/stat/device'
GATEWAY = {
    'name': 'gateway',
    'model': 'UGW3',
    'wan1': {'bytes-r': 1500, 'rx_bytes': 9000, 'rx_bytes-r': 1000, 'tx_bytes': 4000, 'tx_bytes-r': 500},
    'sys_stats': {'loadavg_1': '0.10', 'loadavg_5': '0.20', 'loadavg_15': '0.30'},
    'system-stats': {'cpu': '4.5', 'mem': '31.2'},
}


def controller(**replies: object) -> dict[str, Any]:
    """A controller's reply for each path: a login that works, one site and one gateway, unless told otherwise."""
    return {
        LOGIN: SimpleNamespace(cookies={'unifises': 'session-cookie'}),
        SITES: {'data': [{'name': 'default', 'desc': 'Home'}]},
        DEVICES: {'data': [{'model': 'US8', 'name': 'switch'}, {'model': 'UAP'}, GATEWAY]},
        **replies,
    }


def test_it_signs_in_and_finds_the_site_by_its_description(monkeypatch: pytest.MonkeyPatch) -> None:
    made = answer_by_path(monkeypatch, unifi, controller())

    api = UniFiAPI(UNIFI, FakeOutput())

    login, sites = made
    assert (login.method, login.url) == ('POST', 'https://unifi.example.com:8443/api/login')
    assert json.loads(login.body) == {'username': 'varken', 'password': 'unifi-secret-password', 'remember': True}
    assert sites.url == 'https://unifi.example.com:8443/api/self/sites'
    assert api.session.cookies.get('unifises') == 'session-cookie'
    assert api.site == 'default'


def test_a_site_the_controller_does_not_have_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    answer_by_path(monkeypatch, unifi, controller(**{SITES: {'data': [{'name': 'default', 'desc': 'Office'}]}}))

    api = UniFiAPI(UNIFI, FakeOutput())

    assert 'Could not map site home to a site id/alias' in caplog.text
    assert api.site == 'home'


def test_a_login_without_a_session_cookie_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    answer_by_path(monkeypatch, unifi, controller(**{LOGIN: SimpleNamespace(cookies={})}))

    UniFiAPI(UNIFI, FakeOutput())

    assert 'Could not retrieve session cookie from UniFi Controller' in caplog.text


def test_usg_stats_writes_the_gateways_traffic_and_load(monkeypatch: pytest.MonkeyPatch) -> None:
    made = answer_by_path(monkeypatch, unifi, controller())
    output = FakeOutput()

    UniFiAPI(UNIFI, output).get_usg_stats()

    assert made[-1].url == 'https://unifi.example.com:8443/api/s/default/stat/device'
    (point,) = output.points
    assert point['tags'] == {'model': 'UGW3', 'name': 'gateway'}
    assert point['fields'] == {
        'bytes_current': 1500,
        'rx_bytes_total': 9000,
        'rx_bytes_current': 1000,
        'tx_bytes_total': 4000,
        'tx_bytes_current': 500,
        'cpu_loadavg_1': 0.1,
        'cpu_loadavg_5': 0.2,
        'cpu_loadavg_15': 0.3,
        'cpu_util': 4.5,
        'mem_util': 31.2,
    }


def test_a_failed_request_signs_in_again_and_tries_once_more(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    made = answer_by_path(monkeypatch, unifi, controller(**{DEVICES: False}))
    output = FakeOutput()
    api = UniFiAPI(UNIFI, output)

    api.get_usg_stats()

    paths = [request.path_url for request in made]
    assert paths == [LOGIN, SITES, DEVICES, LOGIN, DEVICES]
    assert 'Attempting to reauthenticate for unifi-1' in caplog.text
    assert 'Disregarding Job get_usg_stats for unifi-1' in caplog.text
    assert output.points == []
    assert api.get_retry is True


def test_a_gateway_the_controller_does_not_have_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    answer_by_path(monkeypatch, unifi, controller(**{DEVICES: {'data': [{'model': 'US8', 'name': 'switch'}]}}))
    output = FakeOutput()

    UniFiAPI(UNIFI, output).get_usg_stats()

    assert 'Could not find a USG named gateway from your UniFi Controller' in caplog.text
    assert output.points == []


def test_a_gateway_without_a_statistic_is_logged_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    gateway = {key: stat for key, stat in GATEWAY.items() if key != 'sys_stats'}
    answer_by_path(monkeypatch, unifi, controller(**{DEVICES: {'data': [gateway]}}))
    output = FakeOutput()

    UniFiAPI(UNIFI, output).get_usg_stats()

    assert "Error building payload for unifi. Discarding. Error: 'sys_stats'" in caplog.text
    assert output.points == []
