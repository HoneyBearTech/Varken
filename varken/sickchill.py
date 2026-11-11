# SPDX-FileCopyrightText: 2018 Boerderij
# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
"""SickChill: the episodes on its coming-episodes list."""

from datetime import UTC, datetime
from logging import getLogger
from typing import TYPE_CHECKING

from requests import Request, Session

from varken.helpers import connection_handler, hashit
from varken.structures import SickChillServer, SickChillTVShow

if TYPE_CHECKING:
    from varken.metrics import Metrics


class SickChillAPI:
    """SickChill through its API, which takes the API key in the URL's path."""

    def __init__(self, server: SickChillServer, output: Metrics) -> None:
        """Set up a session for the server; `output` takes the points."""
        self.output = output
        self.server = server
        # Create session to reduce server web thread load, and globally define pageSize for all requests
        self.session = Session()
        self.session.params = {'limit': 1000}
        self.endpoint = f'/api/{self.server.api_key}'
        self.logger = getLogger()

    def __repr__(self) -> str:
        """Name the server as the log does."""
        return f'<sickchill-{self.server.id}>'

    def get_missing(self) -> None:
        """Write a point for each episode on the coming-episodes list: missed, today, soon or later."""
        now = datetime.now(UTC).astimezone().isoformat()
        points = []
        params = {'cmd': 'future', 'paused': 1, 'type': 'missed|today|soon|later|snatched'}

        req = self.session.prepare_request(Request('GET', self.server.url + self.endpoint, params=params))
        get = connection_handler(self.session, req, verify=self.server.verify_ssl)

        if not get:
            return

        try:
            for key, section in get['data'].items():
                get['data'][key] = [SickChillTVShow(**show) for show in section]
        except TypeError as e:
            self.logger.error('TypeError has occurred : %s while creating SickChillTVShow structure', e)
            return

        for key, section in get['data'].items():
            for show in section:
                sxe = f'S{show.season:0>2}E{show.episode:0>2}'
                hash_id = hashit(f'{self.server.id}{show.show_name}{sxe}')
                missing_types = [(0, 'future'), (1, 'later'), (2, 'soon'), (3, 'today'), (4, 'missed')]
                try:
                    points.append(
                        {
                            'measurement': 'SickChill',
                            'tags': {
                                # A section that is none of these raises the IndexError reported below.
                                'type': [item[0] for item in missing_types if key in item][0],  # noqa: RUF015
                                'indexerid': show.indexerid,
                                'server': self.server.id,
                                'name': show.show_name,
                                'epname': show.ep_name,
                                'sxe': sxe,
                                'airdate': show.airdate,
                            },
                            'time': now,
                            'fields': {'hash': hash_id},
                        }
                    )
                except IndexError as e:
                    self.logger.error('Error building payload for sickchill. Discarding. Error: %s', e)

        if points:
            self.output.write_points(points)
