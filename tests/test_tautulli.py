from types import SimpleNamespace

import pytest
from geoip2.errors import AddressNotFoundError

from varken import tautulli
from varken.structures import TautulliServer
from varken.tautulli import PUBLIC_IP_URL, TautulliAPI

SERVER = TautulliServer(api_key='tautulli-secret-key', fallback_ip='1.1.1.1', get_activity=True, get_stats=True,
                        id=1, url='http://tautulli.example.com:8181', verify_ssl=False)

SESSION = {
    'session_id': 'abc', 'session_key': '12', 'username': 'viewer', 'friendly_name': 'Viewer',
    'full_title': 'Some Show - Pilot', 'ip_address_public': '203.0.113.5', 'transcode_decision': 'copy',
    'stream_video_decision': 'transcode', 'stream_video_resolution': '1080', 'stream_video_full_resolution': '',
    'container': 'mkv', 'state': 'paused', 'product': 'Plex Web', 'product_version': '4.1-abc',
    'platform': 'windows', 'transcode_hw_decoding': 0, 'transcode_hw_encoding': 1, 'media_type': 'episode',
    'audio_codec': 'aac', 'audio_profile': 'lc', 'stream_audio_codec': 'aac', 'quality_profile': 'Original',
    'progress_percent': '42', 'relayed': 0, 'secure': 1,
}

ACTIVITY = {'response': {'data': {
    'sessions': [SESSION], 'stream_count': '1', 'total_bandwidth': '8000', 'wan_bandwidth': '0',
    'lan_bandwidth': '8000', 'stream_count_transcode': '0', 'stream_count_direct_play': '0',
    'stream_count_direct_stream': '1',
}}}

LIBRARIES = {'response': {'data': [
    {'section_name': 'Movies', 'section_type': 'movie', 'count': '10'},
    {'section_name': 'TV', 'section_type': 'show', 'count': '3', 'parent_count': '5', 'child_count': '40'},
    {'section_name': 'Music', 'section_type': 'artist', 'count': '2', 'parent_count': '4', 'child_count': '30'},
]}}


def place(city='Springfield'):
    return SimpleNamespace(location=SimpleNamespace(latitude=39.8, longitude=-89.6), city=SimpleNamespace(name=city),
                           subdivisions=SimpleNamespace(most_specific=SimpleNamespace(iso_code='IL', name='Illinois')))


class FakeDB:
    def __init__(self):
        self.points = []

    def write_points(self, points):
        self.points.extend(points)


class FakeGeoIP:
    def __init__(self, known):
        self.known = known
        self.lookups = []

    def lookup(self, ip):
        self.lookups.append(ip)
        if ip not in self.known:
            raise AddressNotFoundError(f'{ip} not in the database')
        return self.known[ip]


@pytest.fixture
def api_with(monkeypatch):
    def make(reply, known=None):
        monkeypatch.setattr(tautulli, 'connection_handler', lambda session, request, verify: reply)
        db = FakeDB()
        geoip = FakeGeoIP(known if known is not None else {'203.0.113.5': place()})
        return TautulliAPI(SERVER, db, geoip), db, geoip
    return make


def test_activity_writes_each_session_and_the_totals(api_with):
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
    assert totals['fields'] == {'stream_count': 1, 'total_bandwidth': 8000, 'wan_bandwidth': 0, 'lan_bandwidth': 8000,
                                'transcode_streams': 0, 'direct_play_streams': 0, 'direct_streams': 1}


def test_activity_uses_the_fallback_ip_for_unknown_addresses(api_with):
    api, db, geoip = api_with(ACTIVITY, known={'1.1.1.1': place('Fallback City')})

    api.get_activity()

    assert geoip.lookups == ['203.0.113.5', '1.1.1.1']
    assert db.points[0]['tags']['location'] == 'Fallback City'


def test_public_ip_lookup_never_carries_the_api_key(api_with, monkeypatch):
    # Regression: the lookup went through the Tautulli session, which adds apikey= to every request, over plain HTTP.
    calls = []

    def fake_get(url, **kwargs):
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


def test_activity_writes_nothing_when_tautulli_is_unreachable(api_with):
    api, db, _ = api_with(False)

    api.get_activity()

    assert db.points == []


def test_stats_write_one_point_per_library(api_with):
    api, db, _ = api_with(LIBRARIES)

    api.get_stats()

    movies, shows, music = db.points
    assert movies['fields'] == {'total': 10}
    assert shows['fields'] == {'total': 3, 'seasons': 5, 'episodes': 40}
    assert music['fields'] == {'total': 2, 'artists': 2, 'albums': 4, 'tracks': 30}
    assert music['tags']['section_name'] == 'Music'
