# SPDX-FileCopyrightText: 2018 Boerderij
# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
"""What the service modules share: GeoIP lookups, the request handler and small conversions."""

import re
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from http import HTTPStatus
from ipaddress import IPv4Address
from json.decoder import JSONDecodeError
from logging import getLogger
from pathlib import Path
from tarfile import open as taropen
from threading import local
from time import monotonic, sleep
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlsplit

from maxminddb import Reader, open_database
from requests import PreparedRequest, Session
from requests import get as requests_get
from requests.exceptions import (
    ChunkedEncodingError,
    HTTPError,
    InvalidSchema,
    RequestException,
    SSLError,
    Timeout,
)
from requests.exceptions import ConnectionError as RequestsConnectionError
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

logger = getLogger()

# Per thread (every scheduled job runs in its own): set when a request in connection_handler fails, so the Prometheus
# output can tell a job that found nothing from one that couldn't reach its service.
request_state = local()

# Every request to a service: seconds to connect, and to wait for each read. Without them a service that accepts a
# connection but never answers held its job's thread for good, and the scheduler started another every run.
REQUEST_TIMEOUT = (10, 30)


# MaxMind's documented download: Basic auth with the account ID and license key; it redirects to a presigned URL on
# Cloudflare R2, where requests drops the Authorization header. (The legacy URL, with the key as a query parameter,
# was dropped in 3.0.0.)
MAXMIND_URL = 'https://download.maxmind.com/geoip/databases/GeoLite2-City/download'
MAXMIND_TIMEOUT = 60
MAXMIND_ATTEMPTS = 3
# After a failed download, wait this long before the update job tries again (MaxMind rate-limits failures).
MAXMIND_RETRY_AFTER = 3600


class AddressNotFoundError(LookupError):
    """The GeoLite2 database has no record for the address."""


def place_from_record(record: dict[str, Any]) -> SimpleNamespace:
    """Take the parts of a GeoLite2-City record that Varken uses, in the shape its Tautulli module reads.

    They are the latitude and longitude, the city's English name and the most specific subdivision's ISO code and
    English name. Anything the record lacks is None.
    """
    location = record.get('location') or {}
    subdivisions = record.get('subdivisions') or []
    most_specific = subdivisions[-1] if subdivisions else {}
    return SimpleNamespace(
        location=SimpleNamespace(latitude=location.get('latitude'), longitude=location.get('longitude')),
        city=SimpleNamespace(name=((record.get('city') or {}).get('names') or {}).get('en')),
        subdivisions=SimpleNamespace(
            most_specific=SimpleNamespace(
                iso_code=most_specific.get('iso_code'), name=(most_specific.get('names') or {}).get('en')
            )
        ),
    )


class GeoIPHandler:
    """GeoLite2-City lookups for Tautulli's streams.

    The database lives in the data folder and is downloaded when missing or over 30 days old. A failed download
    leaves Varken running: until a later update succeeds, streams have no location.
    """

    def __init__(self, data_folder: str, maxmind_license_key: str, maxmind_account_id: str) -> None:
        """Open the database in the data folder, downloading it first when it isn't there."""
        self.data_folder = data_folder
        self.maxmind_license_key = maxmind_license_key
        self.maxmind_account_id = maxmind_account_id
        self.dbfile = Path(self.data_folder, 'GeoLite2-City.mmdb').absolute()
        self.logger = getLogger()
        self.reader: Reader | None = None
        self.last_failure: float | None = None
        self.reader_manager(action='open')

    def reader_manager(self, action: str | None = None) -> None:
        """Open the database ('open'), downloading it when it is missing; anything else closes it."""
        if action == 'open':
            try:
                self.reader = open_database(self.dbfile)
            except FileNotFoundError:
                self.logger.info('No MaxMind DB in the data folder yet: downloading it')
            else:
                return
            if self.download():
                self.reader = open_database(self.dbfile)
            else:
                self.logger.error(
                    'Could not download the MaxMind DB: streams have no location until the next '
                    'update (every 12 to 24 hours) succeeds.'
                )
        elif self.reader is not None:
            self.reader.close()
            self.reader = None

    def lookup(self, ipaddress: str) -> SimpleNamespace:
        """Find where the address is; every address is unknown while there is no database.

        Raises AddressNotFoundError for an address the database doesn't have, and ValueError for text that isn't
        an address.
        """
        if self.reader is None:
            return NoGeoIP.unknown
        self.logger.debug(
            'Getting lat/long for Tautulli stream using ip with last octet ending in %s', ipaddress.split('.')[-1:][0]
        )
        record = self.reader.get(ipaddress)
        if record is None:
            msg = f'The address {ipaddress} is not in the database'
            raise AddressNotFoundError(msg)
        return place_from_record(record)

    def update(self) -> None:
        """Download the database again once it is over 30 days old, or missing."""
        if self.last_failure is not None and monotonic() - self.last_failure < MAXMIND_RETRY_AFTER:
            self.logger.debug('The last MaxMind download failed less than an hour ago: not retrying yet')
            return
        # Both dates are local ones.
        try:
            dbdate = datetime.fromtimestamp(self.dbfile.stat().st_mtime, UTC).astimezone().date()
        except FileNotFoundError:
            self.reader_manager(action='close')
            self.reader_manager(action='open')
            return
        db_next_update = dbdate + timedelta(days=30)
        today = datetime.now(UTC).astimezone().date()
        self.logger.debug('MaxMind DB date %s, DB updates after: %s, Today: %s', dbdate, db_next_update, today)
        if self.reader is None or db_next_update < today:
            self.logger.info('Updating the MaxMind DB...')
            # download() swaps the new file in atomically, so the open reader keeps working until it's reopened.
            if self.download():
                self.reader_manager(action='close')
                self.reader = open_database(self.dbfile)

    def download(self) -> bool:  # noqa: C901, PLR0912 - one branch for each way a download fails, each with its log line
        """Download and install the database; True if it worked.

        Errors are logged by type, never with the request.
        """
        self.last_failure = monotonic()  # cleared below once the new database is in place
        tar_dbfile = Path(self.data_folder, 'GeoLite2-City.tar.gz').absolute()
        auth = (str(self.maxmind_account_id), self.maxmind_license_key)
        for attempt in range(1, MAXMIND_ATTEMPTS + 1):
            self.logger.info('Downloading GeoLite2 DB from MaxMind...')
            try:
                # MaxMind publishes each archive's SHA-256 beside it: the archive is installed only if it matches.
                with requests_get(
                    MAXMIND_URL, params={'suffix': 'tar.gz.sha256'}, auth=auth, timeout=MAXMIND_TIMEOUT
                ) as reply:
                    if reply.status_code == HTTPStatus.UNAUTHORIZED:
                        self.logger.error(
                            'MaxMind refused the account ID and license key (HTTP 401): check '
                            'maxmind_account_id and maxmind_license_key.'
                        )
                        return False
                    reply.raise_for_status()
                    published = reply.text.split()[0].lower() if reply.text.split() else ''
                if not re.fullmatch(r'[0-9a-f]{64}', published):
                    self.logger.error(
                        "MaxMind's SHA-256 for the database is unreadable (attempt %s of %s)", attempt, MAXMIND_ATTEMPTS
                    )
                else:
                    digest = sha256()
                    with requests_get(
                        MAXMIND_URL, params={'suffix': 'tar.gz'}, auth=auth, timeout=MAXMIND_TIMEOUT, stream=True
                    ) as reply:
                        reply.raise_for_status()
                        with tar_dbfile.open('wb') as archive:
                            for chunk in reply.iter_content(chunk_size=1 << 20):
                                archive.write(chunk)
                                digest.update(chunk)
                    if digest.hexdigest() == published:
                        break
                    tar_dbfile.unlink()
                    self.logger.error(
                        "The GeoLite2 download doesn't match MaxMind's SHA-256 (attempt %s of %s)",
                        attempt,
                        MAXMIND_ATTEMPTS,
                    )
            except HTTPError as e:
                self.logger.error(
                    'MaxMind answered HTTP %s (attempt %s of %s)', e.response.status_code, attempt, MAXMIND_ATTEMPTS
                )
            except RequestException as e:
                self.logger.error(
                    'Could not reach MaxMind: %s (attempt %s of %s)', type(e).__name__, attempt, MAXMIND_ATTEMPTS
                )
            if attempt < MAXMIND_ATTEMPTS:
                sleep(2)
        else:
            self.logger.error('Gave up downloading the MaxMind DB after %s attempts.', MAXMIND_ATTEMPTS)
            return False

        new_dbfile = self.dbfile.with_name(self.dbfile.name + '.new')
        self.logger.debug('Opening MaxMind tar file : %s', tar_dbfile)
        try:
            with taropen(tar_dbfile, 'r:gz') as tar:
                for member in tar.getmembers():
                    if member.name.rpartition('/')[2] == 'GeoLite2-City.mmdb':
                        member.name = new_dbfile.name
                        # The "data" filter refuses links, devices and anything that would land outside the data
                        # folder, so a tampered archive can't write elsewhere.
                        tar.extract(member, self.data_folder, filter='data')
                        self.logger.debug('Extracted %s to %s', member.name, self.data_folder)
                        break
                else:
                    self.logger.error('The MaxMind download has no GeoLite2-City.mmdb in it.')
                    return False
        finally:
            tar_dbfile.unlink(missing_ok=True)
        new_dbfile.replace(self.dbfile)
        self.last_failure = None
        self.logger.info('Installed a new GeoLite2 DB (%.1f MB)', self.dbfile.stat().st_size / 1e6)
        return True


class NoGeoIP:
    """Stand in for GeoIPHandler when there is no MaxMind license key: every address has an unknown location."""

    unknown = SimpleNamespace(
        location=SimpleNamespace(latitude=None, longitude=None),
        city=SimpleNamespace(name=None),
        subdivisions=SimpleNamespace(most_specific=SimpleNamespace(iso_code=None, name=None)),
    )

    def lookup(self, ipaddress: str) -> SimpleNamespace:  # noqa: ARG002 - GeoIPHandler's signature
        """Answer with the unknown location, whatever the address."""
        return self.unknown

    def update(self) -> None:
        """Do nothing: there is no database to update."""


def geoip_handler(data_folder: str, license_key: str | None, account_id: str | None = None) -> GeoIPHandler | NoGeoIP:
    """GeoIP for Tautulli's streams, or none without a license key or an account ID.

    A license key that is empty, or the example's xxxx placeholder, counts as none.
    """
    if not (license_key and license_key.strip('x')):
        logger.info('No MaxMind license key: GeoIP is off and Tautulli streams have no location.')
        return NoGeoIP()
    if not account_id:
        logger.error(
            'GeoIP needs your MaxMind account ID as well as the license key (maxmind_account_id or '
            'VRKN_GLOBAL_MAXMIND_ACCOUNT_ID, since 3.0.0): GeoIP is off until it is set.'
        )
        return NoGeoIP()
    return GeoIPHandler(data_folder, license_key, account_id)


def hashit(string: str) -> str:
    """Hash the text into a stable id for a point: the modules' de-duplication key, which isn't exported."""
    encoded = string.encode()
    # SHA-256, so scanners needn't ask.
    return sha256(encoded).hexdigest()


def rfc1918_ip_check(ip: str) -> bool:
    """Whether the IPv4 address is a private one (RFC 1918, and the other ranges that aren't public)."""
    return IPv4Address(ip).is_private


def connection_handler(  # noqa: C901, PLR0912 - one branch for each way a request fails, each with its own log line
    session: Session, request: PreparedRequest, *, verify: bool, as_is_reply: bool = False
) -> Any:  # noqa: ANN401 - any JSON value, False when there is none, or (as_is_reply) the reply itself
    """Send the request and return the JSON of a 200 reply, or False; a failure is logged and marks the job.

    With as_is_reply the reply itself is returned, whatever its status.
    """
    air = as_is_reply
    s = session
    r = request
    v = verify
    return_json = False

    disable_warnings(InsecureRequestWarning)

    try:
        get = s.send(r, verify=v, timeout=REQUEST_TIMEOUT)
        if get.status_code == HTTPStatus.UNAUTHORIZED:
            if 'NoSiteContext' in str(get.content):
                logger.info('Your Site is incorrect for %s', r.url)
            elif 'LoginRequired' in str(get.content):
                logger.info('Your login credentials are incorrect for %s', r.url)
            else:
                logger.info('Your api key is incorrect for %s', r.url)
        elif get.status_code == HTTPStatus.NOT_FOUND:
            logger.info('This url doesnt even resolve: %s', r.url)
        elif get.status_code == HTTPStatus.OK:
            try:
                return_json = get.json()
            except JSONDecodeError:
                logger.error('No JSON response. Response is: %s', get.text)
        if air:
            if get.status_code != HTTPStatus.OK:
                request_state.failed = True
            return get
    except InvalidSchema:
        logger.error("You added http(s):// in the config file. Don't do that.")
    except SSLError as e:
        logger.error('Either your host is unreachable or you have an SSL issue. : %s', e)
    # Before ConnectionError: a connect timeout is both.
    except Timeout:
        logger.error(
            '%s did not answer within %s seconds (connect) or %s seconds (read)',
            urlsplit(r.url).netloc,
            *REQUEST_TIMEOUT,
        )
    except RequestsConnectionError as e:
        logger.error('Cannot resolve the url/ip/port. Check connectivity. Error: %s', e)
    except ChunkedEncodingError as e:
        logger.error('Broken connection during request... oops? Error: %s', e)

    if return_json is False:
        request_state.failed = True
    return return_json


def mkdir_p(path: str) -> None:
    """Create the folder, and its parents, unless it is there; a failure is logged, not raised."""
    templogger = getLogger('temp')
    try:
        if not Path(path).is_dir():
            templogger.info('Creating folder %s ', path)
            Path(path).mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001 - whatever stops it is logged, and the start goes on
        templogger.error('Could not create folder %s : %s ', path, e)


def clean_sid_check(server_id_list: str, server_type: str | None = None) -> list[int] | Literal[False]:
    """Read a comma-separated list of server ids; False when none of them is a number."""
    t = server_type
    sid_list = server_id_list
    cleaned_list = sid_list.replace(' ', '').split(',')
    valid_sids = []
    for sid in cleaned_list:
        try:
            valid_sids.append(int(sid))
        except ValueError:
            logger.error('%s is not a valid server id number', sid)
    if valid_sids:
        logger.info('%s : %s', t.upper(), valid_sids)
        return valid_sids
    logger.error('No valid %s', t.upper())
    return False


def boolcheck(var: str) -> bool:
    """Whether a setting's text means yes: "true" or "yes", in any case."""
    return var.lower() in ['true', 'yes']


def itemgetter_with_default(**defaults: object) -> Callable[[Mapping[str, Any]], tuple[Any, ...]]:
    """Make a function that reads the named keys from a mapping, in order, with a default for each one missing."""
    return lambda obj: tuple(obj.get(k, v) for k, v in defaults.items())
