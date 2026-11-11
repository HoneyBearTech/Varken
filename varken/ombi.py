# SPDX-FileCopyrightText: 2018 Boerderij
# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
"""Ombi: how many requests and issues it has, and each request."""

from datetime import UTC, datetime
from logging import getLogger
from typing import TYPE_CHECKING

from requests import Request, Session

from varken.helpers import connection_handler, hashit
from varken.structures import OmbiIssuesCounts, OmbiMovieRequest, OmbiRequestCounts, OmbiServer, OmbiTVRequest

if TYPE_CHECKING:
    from varken.metrics import Metrics


class OmbiAPI:
    """Ombi through its v1 API."""

    def __init__(self, server: OmbiServer, output: Metrics) -> None:
        """Set up a session for the server; `output` takes the points."""
        self.output = output
        self.server = server
        # Create session to reduce server web thread load, and globally define pageSize for all requests
        self.session = Session()
        self.session.headers = {'Apikey': self.server.api_key}
        self.logger = getLogger()

    def __repr__(self) -> str:
        """Name the server as the log does."""
        return f'<ombi-{self.server.id}>'

    def get_all_requests(self) -> None:  # noqa: C901, PLR0912 - a status branch for each kind of request
        """Write the number of movie and TV requests, and a point for each request."""
        now = datetime.now(UTC).astimezone().isoformat()
        tv_endpoint = '/api/v1/Request/tv'
        movie_endpoint = '/api/v1/Request/movie'

        tv_req = self.session.prepare_request(Request('GET', self.server.url + tv_endpoint))
        movie_req = self.session.prepare_request(Request('GET', self.server.url + movie_endpoint))
        get_tv = connection_handler(self.session, tv_req, verify=self.server.verify_ssl) or []
        get_movie = connection_handler(self.session, movie_req, verify=self.server.verify_ssl) or []

        if not any([get_tv, get_movie]):
            self.logger.error('No json replies. Discarding job')
            return

        # Either is a list by now: an empty one when its request failed.
        movie_request_count = len(get_movie)
        tv_request_count = len(get_tv)

        tv_show_requests = []
        for show in get_tv:
            try:
                tv_show_requests.append(OmbiTVRequest(**show))
            except TypeError as e:
                self.logger.error(
                    'TypeError has occurred : %s while creating OmbiTVRequest structure for show. '
                    'data attempted is: %s',
                    e,
                    show,
                )

        movie_requests = []
        for movie in get_movie:
            try:
                movie_requests.append(OmbiMovieRequest(**movie))
            except TypeError as e:
                self.logger.error(
                    'TypeError has occurred : %s while creating OmbiMovieRequest structure for movie. '
                    'data attempted is: %s',
                    e,
                    movie,
                )

        points = [
            {
                'measurement': 'Ombi',
                'tags': {'type': 'Request_Total', 'server': self.server.id},
                'time': now,
                'fields': {
                    'total': movie_request_count + tv_request_count,
                    'movies': movie_request_count,
                    'tv_shows': tv_request_count,
                },
            }
        ]
        # Request Type: Movie = 1, TV Show = 0
        for movie in movie_requests:
            hash_id = hashit(f'{movie.id}{movie.theMovieDbId}{movie.title}')

            # Denied = 0, Approved = 1, Completed = 2, Pending = 3
            if movie.denied:
                status = 0

            elif movie.approved and movie.available:
                status = 2

            elif movie.approved:
                status = 1

            else:
                status = 3

            points.append(
                {
                    'measurement': 'Ombi',
                    'tags': {
                        'type': 'Requests',
                        'server': self.server.id,
                        'request_type': 1,
                        'status': status,
                        'title': movie.title,
                        'requested_user': movie.requestedUser['userAlias'],
                        'requested_date': movie.requestedDate,
                    },
                    'time': now,
                    'fields': {'hash': hash_id},
                }
            )

        for show in tv_show_requests:
            hash_id = hashit(f'{show.id}{show.tvDbId}{show.title}')

            # Denied = 0, Approved = 1, Completed = 2, Pending = 3
            if show.childRequests[0].get('denied'):
                status = 0

            elif show.childRequests[0].get('approved') and show.childRequests[0].get('available'):
                status = 2

            elif show.childRequests[0].get('approved'):
                status = 1

            else:
                status = 3

            points.append(
                {
                    'measurement': 'Ombi',
                    'tags': {
                        'type': 'Requests',
                        'server': self.server.id,
                        'request_type': 0,
                        'status': status,
                        'title': show.title,
                        'requested_user': show.childRequests[0]['requestedUser']['userAlias'],
                        'requested_date': show.childRequests[0]['requestedDate'],
                    },
                    'time': now,
                    'fields': {'hash': hash_id},
                }
            )

        if points:
            self.output.write_points(points)
        else:
            self.logger.debug('Empty dataset for ombi module. Discarding...')

    def get_request_counts(self) -> None:
        """Write the number of pending, approved and available requests."""
        now = datetime.now(UTC).astimezone().isoformat()
        endpoint = '/api/v1/Request/count'

        req = self.session.prepare_request(Request('GET', self.server.url + endpoint))
        get = connection_handler(self.session, req, verify=self.server.verify_ssl)

        if not get:
            return

        requests = OmbiRequestCounts(**get)
        points = [
            {
                'measurement': 'Ombi',
                'tags': {'type': 'Request_Counts'},
                'time': now,
                'fields': {'pending': requests.pending, 'approved': requests.approved, 'available': requests.available},
            }
        ]

        self.output.write_points(points)

    def get_issue_counts(self) -> None:
        """Write the number of pending, in-progress and resolved issues."""
        now = datetime.now(UTC).astimezone().isoformat()
        endpoint = '/api/v1/Issues/count'

        req = self.session.prepare_request(Request('GET', self.server.url + endpoint))
        get = connection_handler(self.session, req, verify=self.server.verify_ssl)

        if not get:
            return

        requests = OmbiIssuesCounts(**get)
        points = [
            {
                'measurement': 'Ombi',
                'tags': {'type': 'Issues_Counts'},
                'time': now,
                'fields': {
                    'pending': requests.pending,
                    'in_progress': requests.inProgress,
                    'resolved': requests.resolved,
                },
            }
        ]

        self.output.write_points(points)
