# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
import io
import tarfile

import pytest
from requests.exceptions import (ChunkedEncodingError, ConnectionError, ConnectTimeout, HTTPError, InvalidSchema,
                                 ReadTimeout, SSLError)

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
        self.timeout = None

    def send(self, request, verify, timeout=None):
        self.timeout = timeout
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeRequest:
    url = 'http://app.example.com/api'


def test_connection_handler_returns_json():
    assert connection_handler(FakeSession(FakeResponse(200, {'ok': True})), FakeRequest(), False) == {'ok': True}


def test_every_service_request_has_a_timeout():
    session = FakeSession(FakeResponse(200, {'ok': True}))

    connection_handler(session, FakeRequest(), False)

    assert session.timeout == helpers.REQUEST_TIMEOUT
    assert all(seconds > 0 for seconds in session.timeout)


@pytest.mark.parametrize('error', [ReadTimeout(), ConnectTimeout()])
def test_a_service_that_does_not_answer_fails_the_run(error, caplog):
    # Regression: requests had no timeout, so a service that accepted the connection and never answered held the
    # job's thread for good.
    assert run_in_thread(lambda: connection_handler(FakeSession(error), FakeRequest(), False)) is True
    assert 'app.example.com did not answer' in caplog.text
    assert '/api' not in caplog.text  # the host only: a URL can hold an API key


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


def geoip_handler(folder, account_id='123456'):
    """A handler without the __init__ that opens the database."""
    handler = GeoIPHandler.__new__(GeoIPHandler)
    handler.data_folder = str(folder)
    handler.maxmind_license_key = 'license'
    handler.maxmind_account_id = account_id
    handler.dbfile = str(folder / 'GeoLite2-City.mmdb')
    handler.logger = helpers.getLogger()
    handler.reader = None
    handler.last_failure = None
    return handler


def tar_gz(*members):
    """A .tar.gz whose members are (TarInfo, bytes or None)."""
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w:gz') as tar:
        for info, content in members:
            tar.addfile(info, io.BytesIO(content) if content is not None else None)
    return data.getvalue()


def file_member(name, data):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    return info, data


DATABASE = tar_gz(file_member('GeoLite2-City_20261013/README.txt', b'readme'),
                  file_member('GeoLite2-City_20261013/GeoLite2-City.mmdb', b'database'))


class FakeDownload:
    """What requests.get returns for the download: a status and a streamed body, or an exception to raise."""

    def __init__(self, status=200, body=b'', text=''):
        self.status_code, self.body, self.text = status, body, text

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise HTTPError(response=self)

    def iter_content(self, chunk_size):
        yield self.body


def maxmind_answers(monkeypatch, *replies, checksum=None):
    """Make MaxMind answer each download attempt with the next reply; return every request made, as (suffix, url,
    keyword arguments). An attempt asks for the archive's SHA-256 first: MaxMind answers with the reply's own hash
    (or `checksum`), and with the reply itself when it is an error, which then ends the attempt."""
    calls, replies = [], list(replies)

    def next_reply():
        return replies.pop(0) if len(replies) > 1 else replies[0]

    def fake_get(url, **kwargs):
        suffix = kwargs['params']['suffix']
        calls.append((suffix, url, kwargs))
        reply = replies[0]
        if suffix == 'tar.gz.sha256' and not isinstance(reply, Exception) and reply.status_code < 400:
            published = checksum if checksum is not None else helpers.sha256(reply.body).hexdigest()
            return FakeDownload(text=f'{published}  GeoLite2-City_20261013.tar.gz\n')
        reply = next_reply()
        if isinstance(reply, Exception):
            raise reply
        return reply
    monkeypatch.setattr(helpers, 'requests_get', fake_get)
    monkeypatch.setattr(helpers, 'sleep', lambda seconds: None)
    return calls


def archives(calls):
    return [call for call in calls if call[0] == 'tar.gz']


def test_download_uses_basic_auth_with_the_account_id(tmp_path, monkeypatch, caplog):
    calls = maxmind_answers(monkeypatch, FakeDownload(body=DATABASE))

    with caplog.at_level('INFO'):
        assert geoip_handler(tmp_path).download() is True
    assert 'Installed a new GeoLite2 DB' in caplog.text

    # First the archive's published SHA-256, then the archive, both with Basic auth: the key is never in the URL.
    assert [suffix for suffix, _, _ in calls] == ['tar.gz.sha256', 'tar.gz']
    for _, url, kwargs in calls:
        assert url == 'https://download.maxmind.com/geoip/databases/GeoLite2-City/download'
        assert kwargs['auth'] == ('123456', 'license') and kwargs['timeout']
    assert calls[1][2]['stream']
    assert (tmp_path / 'GeoLite2-City.mmdb').read_bytes() == b'database'
    assert sorted(path.name for path in tmp_path.iterdir()) == ['GeoLite2-City.mmdb']


def test_without_an_account_id_geoip_is_off_and_maxmind_is_never_contacted(tmp_path, monkeypatch, caplog):
    # 3.0.0 dropped the legacy download, which took the license key alone, in the URL.
    calls = maxmind_answers(monkeypatch, FakeDownload(body=DATABASE))

    handler = helpers.geoip_handler(str(tmp_path), 'license', '')

    assert isinstance(handler, helpers.NoGeoIP)
    assert calls == []
    assert 'needs your MaxMind account ID' in caplog.text


def test_download_replaces_the_database_in_one_step(tmp_path, monkeypatch):
    (tmp_path / 'GeoLite2-City.mmdb').write_bytes(b'old')
    old_inode = (tmp_path / 'GeoLite2-City.mmdb').stat().st_ino
    maxmind_answers(monkeypatch, FakeDownload(body=DATABASE))

    geoip_handler(tmp_path).download()

    # A new file renamed over the old one: a reader still mapping the old file keeps working.
    assert (tmp_path / 'GeoLite2-City.mmdb').read_bytes() == b'database'
    assert (tmp_path / 'GeoLite2-City.mmdb').stat().st_ino != old_inode


def test_download_refuses_a_link_in_the_archive(tmp_path, monkeypatch):
    # Regression: members were extracted without a filter, so a link could point anywhere on the host.
    link = tarfile.TarInfo('GeoLite2-City_20261013/GeoLite2-City.mmdb')
    link.type = tarfile.SYMTYPE
    link.linkname = '/etc/passwd'
    maxmind_answers(monkeypatch, FakeDownload(body=tar_gz((link, None))))

    with pytest.raises(tarfile.FilterError):
        geoip_handler(tmp_path).download()

    assert not (tmp_path / 'GeoLite2-City.mmdb').exists()
    assert not (tmp_path / 'GeoLite2-City.tar.gz').exists()


def test_a_download_that_does_not_match_maxminds_sha256_is_never_installed(tmp_path, monkeypatch, caplog):
    calls = maxmind_answers(monkeypatch, FakeDownload(body=DATABASE), checksum='0' * 64)

    assert geoip_handler(tmp_path).download() is False

    assert len(archives(calls)) == 3  # retried, as for any failed attempt
    assert "doesn't match MaxMind's SHA-256" in caplog.text
    assert list(tmp_path.iterdir()) == []  # nothing extracted, and the archive is gone


def test_an_unreadable_sha256_means_no_install(tmp_path, monkeypatch, caplog):
    calls = maxmind_answers(monkeypatch, FakeDownload(body=DATABASE), checksum='not a checksum')

    assert geoip_handler(tmp_path).download() is False
    assert archives(calls) == []
    assert 'SHA-256 for the database is unreadable' in caplog.text


def test_a_corrupt_download_is_retried_and_the_good_one_installed(tmp_path, monkeypatch):
    corrupt = FakeDownload(body=DATABASE[:-10])
    calls = maxmind_answers(monkeypatch, corrupt, FakeDownload(body=DATABASE),
                            checksum=helpers.sha256(DATABASE).hexdigest())

    assert geoip_handler(tmp_path).download() is True
    assert len(archives(calls)) == 2
    assert (tmp_path / 'GeoLite2-City.mmdb').read_bytes() == b'database'


def test_download_stops_on_wrong_credentials(tmp_path, monkeypatch, caplog):
    calls = maxmind_answers(monkeypatch, FakeDownload(status=401))

    assert geoip_handler(tmp_path).download() is False
    assert len(calls) == 1
    assert 'maxmind_account_id and maxmind_license_key' in caplog.text


def test_download_retries_server_errors_three_times(tmp_path, monkeypatch):
    calls = maxmind_answers(monkeypatch, FakeDownload(status=503))

    assert geoip_handler(tmp_path).download() is False
    assert len(calls) == 3


def test_download_recovers_from_one_failed_attempt(tmp_path, monkeypatch):
    calls = maxmind_answers(monkeypatch, ConnectionError('reset'), FakeDownload(body=DATABASE))

    assert geoip_handler(tmp_path).download() is True
    assert len(archives(calls)) == 1  # the first attempt failed before the archive


def test_download_errors_never_log_the_url(tmp_path, monkeypatch, caplog):
    error = ConnectionError('HTTPSConnectionPool: /app/geoip_download?license_key=license')
    maxmind_answers(monkeypatch, error)

    assert geoip_handler(tmp_path).download() is False
    assert 'license_key' not in caplog.text and 'ConnectionError' in caplog.text


def test_a_failed_first_download_leaves_varken_running_without_locations(tmp_path, monkeypatch):
    # Regression: it called exit(1), so a wrong MaxMind key stopped Varken, Tautulli metrics and all.
    maxmind_answers(monkeypatch, FakeDownload(status=401))

    handler = GeoIPHandler(str(tmp_path), 'license', '123456')

    assert handler.reader is None
    assert handler.lookup('203.0.113.5').city.name is None


class FakeReader:
    opened = []

    def __init__(self, path):
        if not __import__('os').path.exists(path):
            raise FileNotFoundError(path)
        self.closed = False
        FakeReader.opened.append(self)

    def close(self):
        self.closed = True


def test_the_next_update_downloads_a_database_the_first_start_missed(tmp_path, monkeypatch):
    FakeReader.opened = []
    monkeypatch.setattr(helpers, 'Reader', FakeReader)
    maxmind_answers(monkeypatch, FakeDownload(status=503), FakeDownload(status=503), FakeDownload(status=503),
                    FakeDownload(body=DATABASE))
    handler = GeoIPHandler(str(tmp_path), 'license', '123456')
    assert handler.reader is None
    monkeypatch.setattr(helpers, 'monotonic', lambda: handler.last_failure + helpers.MAXMIND_RETRY_AFTER + 1)

    handler.update()

    assert isinstance(handler.reader, FakeReader)
    assert handler.last_failure is None


def test_the_update_job_waits_an_hour_after_a_failed_download(tmp_path, monkeypatch):
    # Varken runs every job once at start-up: the update right after a failed first download mustn't hit MaxMind
    # again (it rate-limits failures).
    calls = maxmind_answers(monkeypatch, FakeDownload(status=401))
    handler = GeoIPHandler(str(tmp_path), 'license', '123456')

    handler.update()
    assert len(calls) == 1

    monkeypatch.setattr(helpers, 'monotonic', lambda: handler.last_failure + helpers.MAXMIND_RETRY_AFTER + 1)
    handler.update()
    assert len(calls) == 2


def test_an_update_swaps_in_a_new_database_when_the_old_one_is_due(tmp_path, monkeypatch):
    FakeReader.opened = []
    monkeypatch.setattr(helpers, 'Reader', FakeReader)
    (tmp_path / 'GeoLite2-City.mmdb').write_bytes(b'old')
    old = 1_700_000_000  # 2023: long past due
    __import__('os').utime(tmp_path / 'GeoLite2-City.mmdb', (old, old))
    maxmind_answers(monkeypatch, FakeDownload(body=DATABASE))
    handler = GeoIPHandler(str(tmp_path), 'license', '123456')
    first = handler.reader

    handler.update()

    assert first.closed and handler.reader is not first
    assert (tmp_path / 'GeoLite2-City.mmdb').read_bytes() == b'database'


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
    monkeypatch.setattr(helpers, 'GeoIPHandler', lambda folder, key, account: ('handler', folder, key, account))

    assert helpers.geoip_handler(str(tmp_path), 'real-key', '123456') == ('handler', str(tmp_path), 'real-key',
                                                                         '123456')
    assert isinstance(helpers.geoip_handler(str(tmp_path), 'real-key', ''), helpers.NoGeoIP)


def test_no_geoip_knows_no_location():
    no_geoip = helpers.NoGeoIP()
    no_geoip.update()

    place = no_geoip.lookup('203.0.113.5')
    assert place.city.name is None
    assert place.location.latitude is None
