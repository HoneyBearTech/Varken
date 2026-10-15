from hashlib import sha256
from datetime import date, timedelta
from time import sleep, monotonic
from logging import getLogger
from threading import local
from ipaddress import IPv4Address
from types import SimpleNamespace
from geoip2.database import Reader
from tarfile import open as taropen
from urllib3 import disable_warnings
from os import stat, remove, replace, makedirs
from json.decoder import JSONDecodeError
from os.path import abspath, join, basename, isdir
from urllib3.exceptions import InsecureRequestWarning
from requests import get as requests_get
from requests.exceptions import (InvalidSchema, SSLError, ConnectionError, ChunkedEncodingError, HTTPError,
                                 RequestException)

logger = getLogger()

# Per thread (every scheduled job runs in its own): set when a request in connection_handler fails, so the Prometheus
# output can tell a job that found nothing from one that couldn't reach its service.
request_state = local()


# MaxMind's documented download: Basic auth with the account ID and license key; it redirects to a presigned URL on
# Cloudflare R2, where requests drops the Authorization header. The legacy URL takes the key as a query parameter.
MAXMIND_URL = 'https://download.maxmind.com/geoip/databases/GeoLite2-City/download'
MAXMIND_LEGACY_URL = 'https://download.maxmind.com/app/geoip_download'
MAXMIND_TIMEOUT = 60
# After a failed download, wait this long before the update job tries again (MaxMind rate-limits failures).
MAXMIND_RETRY_AFTER = 3600


class GeoIPHandler(object):
    """GeoLite2-City lookups for Tautulli's streams. The database lives in the data folder and is downloaded when
    missing or over 30 days old. A failed download leaves Varken running: until a later update succeeds, streams
    have no location."""

    def __init__(self, data_folder, maxmind_license_key, maxmind_account_id=None):
        self.data_folder = data_folder
        self.maxmind_license_key = maxmind_license_key
        self.maxmind_account_id = maxmind_account_id
        self.dbfile = abspath(join(self.data_folder, 'GeoLite2-City.mmdb'))
        self.logger = getLogger()
        self.reader = None
        self.last_failure = None
        self.reader_manager(action='open')

    def reader_manager(self, action=None):
        if action == 'open':
            try:
                self.reader = Reader(self.dbfile)
                return
            except FileNotFoundError:
                self.logger.info('No MaxMind DB in the data folder yet: downloading it')
            if self.download():
                self.reader = Reader(self.dbfile)
            else:
                self.logger.error('Could not download the MaxMind DB: streams have no location until the next '
                                  'update (every 12 to 24 hours) succeeds.')
        elif self.reader is not None:
            self.reader.close()
            self.reader = None

    def lookup(self, ipaddress):
        if self.reader is None:
            return NoGeoIP.unknown
        self.logger.debug('Getting lat/long for Tautulli stream using ip with last octet ending in %s',
                          ipaddress.split('.')[-1:][0])
        return self.reader.city(ipaddress)

    def update(self):
        if self.last_failure is not None and monotonic() - self.last_failure < MAXMIND_RETRY_AFTER:
            self.logger.debug('The last MaxMind download failed less than an hour ago: not retrying yet')
            return
        try:
            dbdate = date.fromtimestamp(stat(self.dbfile).st_mtime)
        except FileNotFoundError:
            self.reader_manager(action='close')
            self.reader_manager(action='open')
            return
        db_next_update = dbdate + timedelta(days=30)
        self.logger.debug('MaxMind DB date %s, DB updates after: %s, Today: %s', dbdate, db_next_update,
                          date.today())
        if self.reader is None or db_next_update < date.today():
            self.logger.info('Updating the MaxMind DB...')
            # download() swaps the new file in atomically, so the open reader keeps working until it's reopened.
            if self.download():
                self.reader_manager(action='close')
                self.reader = Reader(self.dbfile)

    def request(self):
        """The URL, query and credentials to download with: Basic auth with the account ID, or the legacy URL."""
        if self.maxmind_account_id:
            return MAXMIND_URL, {'suffix': 'tar.gz'}, (str(self.maxmind_account_id), self.maxmind_license_key)
        self.logger.warning('No MaxMind account ID (maxmind_account_id): downloading with the license key in the '
                            'URL, which MaxMind no longer documents. Add your account ID to use its Basic auth.')
        return (MAXMIND_LEGACY_URL,
                {'edition_id': 'GeoLite2-City', 'suffix': 'tar.gz', 'license_key': self.maxmind_license_key}, None)

    def download(self):
        """Download and install the database; True if it worked. Errors are logged without the URL, which can
        hold the license key."""
        self.last_failure = monotonic()  # cleared below once the new database is in place
        tar_dbfile = abspath(join(self.data_folder, 'GeoLite2-City.tar.gz'))
        url, params, auth = self.request()
        for attempt in range(1, 4):
            self.logger.info('Downloading GeoLite2 DB from MaxMind...')
            try:
                with requests_get(url, params=params, auth=auth, timeout=MAXMIND_TIMEOUT, stream=True) as reply:
                    if reply.status_code == 401:
                        self.logger.error('MaxMind refused the account ID and license key (HTTP 401): check '
                                          'maxmind_account_id and maxmind_license_key.')
                        return False
                    reply.raise_for_status()
                    with open(tar_dbfile, 'wb') as archive:
                        for chunk in reply.iter_content(chunk_size=1 << 20):
                            archive.write(chunk)
                break
            except HTTPError as e:
                self.logger.error('MaxMind answered HTTP %s (attempt %s of 3)', e.response.status_code, attempt)
            except RequestException as e:
                self.logger.error('Could not reach MaxMind: %s (attempt %s of 3)', type(e).__name__, attempt)
            if attempt < 3:
                sleep(2)
        else:
            self.logger.error('Gave up downloading the MaxMind DB after 3 attempts.')
            return False

        new_dbfile = self.dbfile + '.new'
        self.logger.debug('Opening MaxMind tar file : %s', tar_dbfile)
        try:
            with taropen(tar_dbfile, 'r:gz') as tar:
                for member in tar.getmembers():
                    if basename(member.name) == 'GeoLite2-City.mmdb':
                        member.name = basename(new_dbfile)
                        # The "data" filter refuses links, devices and anything that would land outside the data
                        # folder, so a tampered archive can't write elsewhere.
                        tar.extract(member, self.data_folder, filter='data')
                        self.logger.debug('Extracted %s to %s', member.name, self.data_folder)
                        break
                else:
                    self.logger.error('The MaxMind download has no GeoLite2-City.mmdb in it.')
                    return False
        finally:
            try:
                remove(tar_dbfile)
            except FileNotFoundError:
                pass
        replace(new_dbfile, self.dbfile)
        self.last_failure = None
        return True


class NoGeoIP(object):
    """Stands in for GeoIPHandler when there is no MaxMind license key: every address has an unknown location."""
    unknown = SimpleNamespace(location=SimpleNamespace(latitude=None, longitude=None), city=SimpleNamespace(name=None),
                              subdivisions=SimpleNamespace(most_specific=SimpleNamespace(iso_code=None, name=None)))

    def lookup(self, ipaddress):
        return self.unknown

    def update(self):
        pass


def geoip_handler(data_folder, license_key, account_id=None):
    """GeoIP for Tautulli's streams, or none when no license key is set (empty, or the example's xxxx placeholder)."""
    if license_key and license_key.strip('x'):
        return GeoIPHandler(data_folder, license_key, account_id or None)
    logger.info('No MaxMind license key: GeoIP is off and Tautulli streams have no location.')
    return NoGeoIP()


def hashit(string):
    encoded = string.encode()
    # A stable id for a point (the modules' de-duplication key; it isn't exported). SHA-256, so scanners needn't ask.
    hashed = sha256(encoded).hexdigest()

    return hashed


def rfc1918_ip_check(ip):
    rfc1918_ip = IPv4Address(ip).is_private

    return rfc1918_ip


def connection_handler(session, request, verify, as_is_reply=False):
    air = as_is_reply
    s = session
    r = request
    v = verify
    return_json = False

    disable_warnings(InsecureRequestWarning)

    try:
        get = s.send(r, verify=v)
        if get.status_code == 401:
            if 'NoSiteContext' in str(get.content):
                logger.info('Your Site is incorrect for %s', r.url)
            elif 'LoginRequired' in str(get.content):
                logger.info('Your login credentials are incorrect for %s', r.url)
            else:
                logger.info('Your api key is incorrect for %s', r.url)
        elif get.status_code == 404:
            logger.info('This url doesnt even resolve: %s', r.url)
        elif get.status_code == 200:
            try:
                return_json = get.json()
            except JSONDecodeError:
                logger.error('No JSON response. Response is: %s', get.text)
        if air:
            if get.status_code != 200:
                request_state.failed = True
            return get
    except InvalidSchema:
        logger.error("You added http(s):// in the config file. Don't do that.")
    except SSLError as e:
        logger.error('Either your host is unreachable or you have an SSL issue. : %s', e)
    except ConnectionError as e:
        logger.error('Cannot resolve the url/ip/port. Check connectivity. Error: %s', e)
    except ChunkedEncodingError as e:
        logger.error('Broken connection during request... oops? Error: %s', e)

    if return_json is False:
        request_state.failed = True
    return return_json


def mkdir_p(path):
    templogger = getLogger('temp')
    try:
        if not isdir(path):
            templogger.info('Creating folder %s ', path)
            makedirs(path, exist_ok=True)
    except Exception as e:
        templogger.error('Could not create folder %s : %s ', path, e)


def clean_sid_check(server_id_list, server_type=None):
    t = server_type
    sid_list = server_id_list
    cleaned_list = sid_list.replace(' ', '').split(',')
    valid_sids = []
    for sid in cleaned_list:
        try:
            valid_sids.append(int(sid))
        except ValueError:
            logger.error("%s is not a valid server id number", sid)
    if valid_sids:
        logger.info('%s : %s', t.upper(), valid_sids)
        return valid_sids
    else:
        logger.error('No valid %s', t.upper())
        return False


def boolcheck(var):
    if var.lower() in ['true', 'yes']:
        return True
    else:
        return False


def itemgetter_with_default(**defaults):
    return lambda obj: tuple(obj.get(k, v) for k, v in defaults.items())
