# SPDX-FileCopyrightText: 2018 Boerderij
# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
"""Sonarr: its download queue, and the episodes that are missing or airing soon."""

from datetime import UTC, datetime, timedelta
from logging import getLogger
from typing import TYPE_CHECKING

from requests import Request, Session

from varken.helpers import connection_handler, hashit

if TYPE_CHECKING:
    from varken.metrics import Metrics
    from varken.structures import SonarrServer


def episode_code(season: int, episode: int) -> str:
    """Name an episode the usual way: S01E02."""
    return f'S{season:0>2}E{episode:0>2}'


class SonarrAPI:
    """Sonarr through its v3 API (Sonarr 4; Sonarr 3 serves the same API)."""

    def __init__(self, server: SonarrServer, output: Metrics) -> None:
        """Set up a session for the server; `output` takes the points."""
        self.output = output
        self.server = server
        # Create session to reduce server web thread load, and globally define pageSize for all requests
        self.session = Session()
        self.session.headers = {'X-Api-Key': self.server.api_key}
        self.session.params = {'pageSize': 1000}
        self.logger = getLogger()

    def __repr__(self) -> str:
        """Name the server as the log does."""
        return f'<sonarr-{self.server.id}>'

    def get_calendar(self, query: str = 'Missing') -> None:
        """Write a point for each missing episode (query 'Missing'), or for each one airing soon (any other query)."""
        endpoint = '/api/v3/calendar'
        local_date = datetime.now(UTC).astimezone().date()
        today = str(local_date)
        last_days = str(local_date - timedelta(days=self.server.missing_days))
        future = str(local_date + timedelta(days=self.server.future_days))
        now = datetime.now(UTC).astimezone().isoformat()
        if query == 'Missing':
            params = {'start': last_days, 'end': today, 'includeSeries': 'true'}
        else:
            params = {'start': today, 'end': future, 'includeSeries': 'true'}
        points = []

        req = self.session.prepare_request(Request('GET', self.server.url + endpoint, params=params))
        get = connection_handler(self.session, req, verify=self.server.verify_ssl)

        if get is False:
            return
        if not isinstance(get, list):
            self.logger.error("Unexpected reply from Sonarr's calendar (is it Sonarr 3 or later?): %s", get)
            return

        for show in get:
            if not isinstance(show, dict):
                self.logger.error('Skipping a Sonarr entry that is not an object: %s', show)

                continue
            try:
                series_title = show['series']['title']
                sxe = episode_code(show['seasonNumber'], show['episodeNumber'])
            except (KeyError, TypeError) as e:
                self.logger.error(
                    'Skipping a Sonarr calendar entry without series or episode numbers (%s): %s', e, show
                )
                continue
            downloaded = 1 if show.get('hasFile') else 0
            if query == 'Missing' and (not show.get('monitored') or downloaded):
                continue
            hash_id = hashit(f'{self.server.id}{series_title}{sxe}')
            points.append(
                {
                    'measurement': 'Sonarr',
                    'tags': {
                        'type': query,
                        'sonarrId': show.get('id'),
                        'server': self.server.id,
                        'name': series_title,
                        'epname': show.get('title', ''),
                        'sxe': sxe,
                        'airsUTC': show.get('airDateUtc', ''),
                        'downloaded': downloaded,
                    },
                    'time': now,
                    'fields': {'hash': hash_id},
                }
            )

        self.output.write_points(points)

    def get_queue(self) -> None:
        """Write a point for each episode in the download queue."""
        points = []
        endpoint = '/api/v3/queue'
        params = {'includeSeries': 'true', 'includeEpisode': 'true'}
        now = datetime.now(UTC).astimezone().isoformat()

        req = self.session.prepare_request(Request('GET', self.server.url + endpoint, params=params))
        get = connection_handler(self.session, req, verify=self.server.verify_ssl)

        if get is False:
            return
        if not isinstance(get, dict) or not isinstance(get.get('records'), list):
            self.logger.error("Unexpected reply from Sonarr's queue (is it Sonarr 3 or later?): %s", get)
            return

        for item in get['records']:
            if not isinstance(item, dict):
                self.logger.error('Skipping a Sonarr entry that is not an object: %s', item)

                continue
            try:
                series_title = item['series']['title']
                episode = item['episode']
                sxe = episode_code(episode['seasonNumber'], episode['episodeNumber'])
                quality = item['quality']['quality']['name']
            except (KeyError, TypeError) as e:
                # A queue entry Sonarr hasn't matched to an episode (an unknown download, say).
                self.logger.debug('Skipping a Sonarr queue entry without a series or episode (%s): %s', e, item)
                continue
            protocol = str(item.get('protocol', '')).upper()
            hash_id = hashit(f'{self.server.id}{series_title}{sxe}')
            points.append(
                {
                    'measurement': 'Sonarr',
                    'tags': {
                        'type': 'Queue',
                        'sonarrId': item.get('id'),
                        'server': self.server.id,
                        'name': series_title,
                        'epname': episode.get('title', ''),
                        'sxe': sxe,
                        'protocol': protocol,
                        'protocol_id': 1 if protocol == 'USENET' else 0,
                        'quality': quality,
                    },
                    'time': now,
                    'fields': {'hash': hash_id},
                }
            )
        if not points:
            self.logger.debug('No queue items for sonarr instance.')
        self.output.write_points(points)
