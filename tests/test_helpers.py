import io
import tarfile
from urllib.error import HTTPError, URLError

import pytest
from requests.exceptions import ChunkedEncodingError, ConnectionError, InvalidSchema, SSLError

from varken import helpers
from varken.helpers import (GeoIPHandler, boolcheck, clean_sid_check, connection_handler, hashit,
                            itemgetter_with_default, rfc1918_ip_check)


def test_boolcheck():
    assert boolcheck('true') and boolcheck('Yes')
    assert not boolcheck('false') and not boolcheck('1')


def test_clean_sid_check_keeps_valid_ids():
    assert clean_sid_check('1, 2,x', 'sonarr') == [1, 2]
    assert clean_sid_check('x', 'sonarr') is False


def test_hashit_is_a_stable_sha256():
    assert hashit('abc') == 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'


def test_rfc1918_ip_check():
    assert rfc1918_ip_check('10.1.2.3')
    assert not rfc1918_ip_check('1.1.1.1')


def test_itemgetter_with_default():
    getter = itemgetter_with_default(a=1, b=None)
    assert getter({'a': 5}) == (5, None)


class FakeResponse:
    def __init__(self, status_code, payload=None, content=b''):
        self.status_code = status_code
        self.payload = payload
        self.content = content
        self.text = content.decode()

    def json(self):
        if self.payload is None:
            raise helpers.JSONDecodeError('no JSON', '', 0)
        return self.payload


class FakeSession:
    def __init__(self, result):
        self.result = result

    def send(self, request, verify):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeRequest:
    url = 'http://app.example.com/api'


def test_connection_handler_returns_json():
    assert connection_handler(FakeSession(FakeResponse(200, {'ok': True})), FakeRequest(), False) == {'ok': True}


def test_connection_handler_returns_the_response_as_is():
    response = FakeResponse(200, {'ok': True})
    assert connection_handler(FakeSession(response), FakeRequest(), False, as_is_reply=True) is response


@pytest.mark.parametrize('response', [
    FakeResponse(200, None, b'<html>'),
    FakeResponse(401, content=b'NoSiteContext'),
    FakeResponse(401, content=b'LoginRequired'),
    FakeResponse(401),
    FakeResponse(404),
])
def test_connection_handler_returns_false_without_usable_json(response):
    assert connection_handler(FakeSession(response), FakeRequest(), False) is False


@pytest.mark.parametrize('error', [InvalidSchema(), SSLError(), ConnectionError(), ChunkedEncodingError()])
def test_connection_handler_survives_connection_errors(error):
    assert connection_handler(FakeSession(error), FakeRequest(), False) is False


def geoip_handler(folder):
    """A handler without the __init__ that opens the database."""
    handler = GeoIPHandler.__new__(GeoIPHandler)
    handler.data_folder = str(folder)
    handler.maxmind_license_key = 'license'
    handler.dbfile = str(folder / 'GeoLite2-City.mmdb')
    handler.logger = helpers.getLogger()
    return handler


def tar_with(*members):
    """Write a .tar.gz whose members are (TarInfo, bytes or None)."""
    def fake_urlretrieve(url, filename):
        with tarfile.open(filename, 'w:gz') as tar:
            for info, data in members:
                tar.addfile(info, io.BytesIO(data) if data is not None else None)
    return fake_urlretrieve


def file_member(name, data):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    return info, data


def test_download_extracts_the_database(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, 'urlretrieve', tar_with(
        file_member('GeoLite2-City_20261013/README.txt', b'readme'),
        file_member('GeoLite2-City_20261013/GeoLite2-City.mmdb', b'database'),
    ))

    geoip_handler(tmp_path).download()

    assert (tmp_path / 'GeoLite2-City.mmdb').read_bytes() == b'database'
    assert not (tmp_path / 'GeoLite2-City.tar.gz').exists()
    assert not (tmp_path / 'README.txt').exists()


def test_download_refuses_a_link_in_the_archive(tmp_path, monkeypatch):
    # Regression: members were extracted without a filter, so a link could point anywhere on the host.
    link = tarfile.TarInfo('GeoLite2-City_20261013/GeoLite2-City.mmdb')
    link.type = tarfile.SYMTYPE
    link.linkname = '/etc/passwd'
    monkeypatch.setattr(helpers, 'urlretrieve', tar_with((link, None)))

    with pytest.raises(tarfile.FilterError):
        geoip_handler(tmp_path).download()

    assert not (tmp_path / 'GeoLite2-City.mmdb').is_symlink()


@pytest.fixture
def http_error():
    """HTTPErrors that are closed after the test (each holds a response body)."""
    errors = []

    def make(code, reason):
        error = HTTPError('https://download.maxmind.com/', code, reason, {}, io.BytesIO())
        errors.append(error)
        return error

    yield make
    for error in errors:
        error.close()


def raise_error(error):
    def fake_urlretrieve(url, filename):
        raise error
    return fake_urlretrieve


def test_download_stops_on_a_wrong_license_key(tmp_path, monkeypatch, http_error):
    # Regression: HTTPError was caught as URLError first, so this branch never ran.
    monkeypatch.setattr(helpers, 'urlretrieve', raise_error(http_error(401, 'Unauthorized')))
    messages = []
    handler = geoip_handler(tmp_path)
    monkeypatch.setattr(handler.logger, 'error', lambda msg, *args: messages.append(msg))

    assert handler.download() == 1
    assert 'license key' in messages[0]


def test_download_retries_server_errors_three_times(tmp_path, monkeypatch, http_error):
    calls = []

    def failing(url, filename):
        calls.append(url)
        raise http_error(503, 'Unavailable')

    monkeypatch.setattr(helpers, 'urlretrieve', failing)
    monkeypatch.setattr(helpers, 'sleep', lambda seconds: None)

    assert geoip_handler(tmp_path).download() == 1
    assert len(calls) == 3


def test_download_stops_when_maxmind_is_unreachable(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, 'urlretrieve', raise_error(URLError('no route')))

    assert geoip_handler(tmp_path).download() == 1


def run_in_thread(function):
    """Run function in a new thread, as the scheduler runs jobs, and return the thread's request state."""
    from threading import Thread
    result = {}

    def target():
        function()
        result['failed'] = getattr(helpers.request_state, 'failed', False)
    worker = Thread(target=target)
    worker.start()
    worker.join()
    return result['failed']


def test_a_successful_request_is_not_a_failure():
    assert run_in_thread(lambda: connection_handler(FakeSession(FakeResponse(200, [])), FakeRequest(), False)) is False


@pytest.mark.parametrize('result', [FakeResponse(500), FakeResponse(404), FakeResponse(200, None, b'<html>'),
                                    ConnectionError()])
def test_a_failed_request_is_recorded_for_the_thread(result):
    assert run_in_thread(lambda: connection_handler(FakeSession(result), FakeRequest(), False)) is True


def test_a_failed_as_is_request_is_recorded_for_the_thread():
    assert run_in_thread(lambda: connection_handler(FakeSession(FakeResponse(401)), FakeRequest(), False,
                                                    as_is_reply=True)) is True


@pytest.mark.parametrize('key', ['', None, 'xxxxxxxxxxxxxxxx'])
def test_geoip_is_off_without_a_license_key(tmp_path, key):
    assert isinstance(helpers.geoip_handler(str(tmp_path), key), helpers.NoGeoIP)


def test_geoip_is_on_with_a_license_key(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, 'GeoIPHandler', lambda folder, key: ('handler', folder, key))

    assert helpers.geoip_handler(str(tmp_path), 'real-key') == ('handler', str(tmp_path), 'real-key')


def test_no_geoip_knows_no_location():
    no_geoip = helpers.NoGeoIP()
    no_geoip.update()

    place = no_geoip.lookup('203.0.113.5')
    assert place.city.name is None
    assert place.location.latitude is None
