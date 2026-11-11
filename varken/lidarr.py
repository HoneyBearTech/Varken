# SPDX-FileCopyrightText: 2018 Boerderij
# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
"""Lidarr: its download queue, and the albums that are missing tracks or coming out soon."""

from datetime import UTC, datetime, timedelta
from logging import getLogger
from typing import TYPE_CHECKING

from requests import Request, Session

from varken.helpers import connection_handler, hashit

if TYPE_CHECKING:
    from varken.metrics import Metrics
    from varken.structures import SonarrServer

ALL_TRACKS = 100  # percentOfTracks of an album with a file for every track


class LidarrAPI:
    """Lidarr through its v1 API (Lidarr 1 and 2)."""

    def __init__(self, server: SonarrServer, output: Metrics) -> None:
        """Set up a session for the server; `output` takes the points.

        A [lidarr-N] section has the settings of a [sonarr-N] one, hence the server's type.
        """
        self.output = output
        self.server = server
        # Create session to reduce server web thread load, and globally define pageSize for all requests
        self.session = Session()
        self.session.headers = {'X-Api-Key': self.server.api_key}
        self.logger = getLogger()

    def __repr__(self) -> str:
        """Name the server as the log does."""
        return f'<lidarr-{self.server.id}>'

    def get_calendar(self, query: str = 'Missing') -> None:
        """Write a point for each album missing tracks (query 'Missing'), or for each one coming out soon."""
        endpoint = '/api/v1/calendar'
        local_date = datetime.now(UTC).astimezone().date()
        today = str(local_date)
        last_days = str(local_date - timedelta(days=self.server.missing_days))
        future = str(local_date + timedelta(days=self.server.future_days))
        now = datetime.now(UTC).astimezone().isoformat()
        if query == 'Missing':
            params = {'start': last_days, 'end': today, 'includeArtist': 'true'}
        else:
            params = {'start': today, 'end': future, 'includeArtist': 'true'}
        points = []

        req = self.session.prepare_request(Request('GET', self.server.url + endpoint, params=params))
        get = connection_handler(self.session, req, verify=self.server.verify_ssl)

        if get is False:
            return
        if not isinstance(get, list):
            self.logger.error("Unexpected reply from Lidarr's calendar: %s", get)
            return

        for album in get:
            if not isinstance(album, dict):
                self.logger.error('Skipping a Lidarr entry that is not an object: %s', album)

                continue
            try:
                title = album['title']
                artist_name = album['artist']['artistName']
            except (KeyError, TypeError) as e:
                self.logger.error('Skipping a Lidarr calendar entry without a title or artist (%s): %s', e, album)
                continue
            statistics = album.get('statistics') or {}
            percent_of_tracks = statistics.get('percentOfTracks', 0)
            # Missing: monitored albums that came out in the last missing_days without every track.
            if query == 'Missing' and (not album.get('monitored') or percent_of_tracks == ALL_TRACKS):
                continue
            hash_id = hashit(f'{self.server.id}{title}{album.get("id")}')
            points.append(
                {
                    'measurement': 'Lidarr',
                    'tags': {
                        'type': query,
                        'sonarrId': album.get('id'),
                        'server': self.server.id,
                        'albumName': title,
                        'artistName': artist_name,
                        'percentComplete': percent_of_tracks,
                        'completeCount': f'{statistics.get("trackFileCount", 0)}/{statistics.get("trackCount", 0)}',
                        'releaseDate': album.get('releaseDate', ''),
                    },
                    'time': now,
                    'fields': {'hash': hash_id},
                }
            )

        self.output.write_points(points)

    def get_queue(self) -> None:
        """Write a point for each release in the download queue."""
        endpoint = '/api/v1/queue'
        now = datetime.now(UTC).astimezone().isoformat()
        points = []
        params = {'pageSize': 1000, 'includeArtist': 'true', 'includeAlbum': 'true'}

        req = self.session.prepare_request(Request('GET', self.server.url + endpoint, params=params))
        get = connection_handler(self.session, req, verify=self.server.verify_ssl)

        if get is False:
            return
        if not isinstance(get, dict) or not isinstance(get.get('records'), list):
            self.logger.error("Unexpected reply from Lidarr's queue: %s", get)
            return

        for item in get['records']:
            if not isinstance(item, dict):
                self.logger.error('Skipping a Lidarr entry that is not an object: %s', item)

                continue
            try:
                quality = item['quality']['quality']['name']
            except KeyError, TypeError:
                quality = ''
            protocol = str(item.get('protocol', ''))
            title = item.get('title', '')
            # The artist and album (with includeArtist/includeAlbum); a download Lidarr hasn't matched has neither.
            artist = (item.get('artist') or {}).get('artistName', '')
            album = (item.get('album') or {}).get('title', '')
            hash_id = hashit(f'{self.server.id}{title}{item.get("artistId")}')
            points.append(
                {
                    'measurement': 'Lidarr',
                    'tags': {
                        'type': 'Queue',
                        'id': item.get('id'),
                        'server': self.server.id,
                        'title': title,
                        'artistName': artist,
                        'albumName': album,
                        'quality': quality,
                        'protocol': protocol,
                        'protocol_id': 1 if protocol.upper() == 'USENET' else 0,
                        'indexer': item.get('indexer', ''),
                    },
                    'time': now,
                    'fields': {'hash': hash_id},
                }
            )

        self.output.write_points(points)
