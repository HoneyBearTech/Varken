# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from tests.tautulli_data import ACTIVITY, LIBRARIES, SERVER, FakeGeoIP, FakeOutput, place
from varken import tautulli
from varken.helpers import NoGeoIP
from varken.tautulli import PUBLIC_IP_URL, TautulliAPI

if TYPE_CHECKING:
    from collections.abc import Callable

# The api_with fixture: it makes an API whose Tautulli answers with a reply, and hands back its output and GeoIP.
type ApiWith = Callable[..., tuple[TautulliAPI, FakeOutput, FakeGeoIP]]


@pytest.fixture
def api_with(monkeypatch: pytest.MonkeyPatch) -> ApiWith:
    def make(
        reply: object, known: dict[str, SimpleNamespace] | None = None
    ) -> tuple[TautulliAPI, FakeOutput, FakeGeoIP]:
        monkeypatch.setattr(tautulli, 'connection_handler', lambda session, request, verify: reply)
        db = FakeOutput()
        geoip = FakeGeoIP(known if known is not None else {'203.0.113.5': place()})
        return TautulliAPI(SERVER, db, geoip), db, geoip

    return make


def test_activity_writes_each_session_and_the_totals(api_with: ApiWith) -> None:
    api, db, _ = api_with(ACTIVITY)

    api.get_activity()

    session, totals = db.points
    assert session['tags']['type'] == 'Session'
    assert session['tags']['transcode_decision'] == 'Direct Stream'
    assert session['tags']['video_decision'] == 'Transcode'
    assert session['tags']['quality'] == '1080p'
    assert session['tags']['player_state'] == 1
    assert session['tags']['platform'] == 'Windows'
    assert session['tags']['product_version'] == '4.1'
    assert session['tags']['location'] == 'Springfield'
    assert session['tags']['full_location'] == 'Illinois - Springfield'
    assert totals['tags']['type'] == 'current_stream_stats'
    assert totals['fields'] == {
        'stream_count': 1,
        'total_bandwidth': 8000,
        'wan_bandwidth': 0,
        'lan_bandwidth': 8000,
        'transcode_streams': 0,
        'direct_play_streams': 0,
        'direct_streams': 1,
    }


def test_activity_uses_the_fallback_ip_for_unknown_addresses(api_with: ApiWith) -> None:
    api, db, geoip = api_with(ACTIVITY, known={'1.1.1.1': place('Fallback City')})

    api.get_activity()

    assert geoip.lookups == ['203.0.113.5', '1.1.1.1']
    assert db.points[0]['tags']['location'] == 'Fallback City'


def test_public_ip_lookup_never_carries_the_api_key(api_with: ApiWith, monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: the lookup went through the Tautulli session, which adds apikey= to every request, over plain HTTP.
    calls = []

    def fake_get(url: str, **kwargs: object) -> SimpleNamespace:
        calls.append((url, kwargs))
        return SimpleNamespace(text='198.51.100.9\n')

    monkeypatch.setattr(tautulli, 'requests_get', fake_get)
    api, db, _ = api_with(ACTIVITY, known={'198.51.100.9': place('Home')})
    monkeypatch.setattr(api.session, 'get', lambda *args, **kwargs: pytest.fail('used the Tautulli session'))

    api.get_activity()

    assert calls == [(PUBLIC_IP_URL, {'timeout': 10})]
    assert PUBLIC_IP_URL.startswith('https://')
    assert 'tautulli-secret-key' not in str(calls)
    assert api.my_ip == '198.51.100.9'
    assert db.points[0]['tags']['location'] == 'Home'


def test_activity_writes_nothing_when_tautulli_is_unreachable(api_with: ApiWith) -> None:
    api, db, _ = api_with(reply=False)

    api.get_activity()

    assert db.points == []


def test_stats_write_one_point_per_library(api_with: ApiWith) -> None:
    api, db, _ = api_with(LIBRARIES)

    api.get_stats()

    movies, shows, music = db.points
    assert movies['fields'] == {'total': 10}
    assert shows['fields'] == {'total': 3, 'seasons': 5, 'episodes': 40}
    assert music['fields'] == {'total': 2, 'artists': 2, 'albums': 4, 'tracks': 30}
    assert music['tags']['section_name'] == 'Music'


def test_activity_without_geoip_has_no_location(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tautulli, 'connection_handler', lambda session, request, verify: ACTIVITY)
    monkeypatch.setattr(tautulli, 'requests_get', lambda *args, **kwargs: pytest.fail('looked up the public IP'))
    db = FakeOutput()

    TautulliAPI(SERVER, db, NoGeoIP()).get_activity()

    tags = db.points[0]['tags']
    assert tags['location'] == '👽'
    assert tags['full_location'] == ''
    assert tags['region_code'] is None
    assert (tags['latitude'], tags['longitude']) == (37.234332396, -115.80666344)
