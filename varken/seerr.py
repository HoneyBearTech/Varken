# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
"""Seerr: how many requests and issues it has, and each request still waiting."""

from datetime import UTC, datetime
from logging import getLogger
from typing import TYPE_CHECKING, Any

from requests import Request, Session

from varken.helpers import connection_handler, request_state

if TYPE_CHECKING:
    from varken.metrics import Metrics, Point
    from varken.structures import SeerrServer

# MediaRequestStatus and MediaStatus in Seerr's server/constants/media.ts (its OpenAPI spec is out of date).
REQUEST_STATUS = {1: 'pending', 2: 'approved', 3: 'declined', 4: 'failed', 5: 'completed'}
MEDIA_AVAILABLE = 5
# The most recent requests read per run: one page, so one call (Seerr also asks every Sonarr and Radarr it knows
# for their quality profiles on each page).
REQUESTS_PER_RUN = 100


class SeerrAPI:
    """Seerr (the successor of Overseerr and Jellyseerr) through its v1 API.

    Its API key acts as Seerr's admin: Varken only reads.
    """

    def __init__(self, server: SeerrServer, output: Metrics) -> None:
        """Set up a session for the server; `output` takes the points."""
        self.output = output
        self.server = server
        self.session = Session()
        self.session.headers = {'X-Api-Key': self.server.api_key}
        self.logger = getLogger()
        # (movie|tv, TMDB id) -> title, kept across runs: a title costs a request to Seerr (and Seerr's to TMDB).
        self.titles: dict[tuple[str, int], str] = {}

    def __repr__(self) -> str:
        """Name the server as the log does."""
        return f'<seerr-{self.server.id}>'

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:  # noqa: ANN401 - any JSON value, or False
        """Ask Seerr for the endpoint: the reply's JSON, or False when the request failed."""
        request = self.session.prepare_request(Request('GET', self.server.url + endpoint, params=params))
        return connection_handler(self.session, request, verify=self.server.verify_ssl)

    def counts(self, endpoint: str, kind: str) -> Point | None:
        """Turn a counts endpoint's reply into one point; None (logged) when it isn't one."""
        get = self.get(endpoint)
        if get is False:
            return None
        if not isinstance(get, dict) or not all(isinstance(value, int) for value in get.values()):
            self.logger.error("Unexpected reply from Seerr's %s: %s", endpoint, get)
            return None
        return {
            'measurement': 'Seerr',
            'tags': {'type': kind, 'server': self.server.id},
            'time': datetime.now(UTC).astimezone().isoformat(),
            'fields': get,
        }

    def get_request_counts(self) -> None:
        """Write the number of requests by status and by media type."""
        point = self.counts('/api/v1/request/count', 'Request_Counts')
        if point:
            self.output.write_points([point])

    def get_issue_counts(self) -> None:
        """Write the number of issues by status and by type."""
        point = self.counts('/api/v1/issue/count', 'Issue_Counts')
        if point:
            self.output.write_points([point])

    def title(self, media_type: str, tmdb_id: int) -> str:
        """Look up the movie's or show's title, with its year, through Seerr's TMDB lookup.

        A failed lookup doesn't fail the run: the request is listed under its TMDB id instead, and the title is
        tried again next run.
        """
        key = (media_type, tmdb_id)
        if key in self.titles:
            return self.titles[key]
        failed_before = getattr(request_state, 'failed', False)
        details = self.get(f'/api/v1/{media_type}/{tmdb_id}')
        request_state.failed = failed_before
        if not isinstance(details, dict):
            return f'TMDB {tmdb_id}'
        name = details.get('title') if media_type == 'movie' else details.get('name')
        date = details.get('releaseDate') if media_type == 'movie' else details.get('firstAirDate')
        if not name:
            return f'TMDB {tmdb_id}'
        title = f'{name} ({date[:4]})' if date else name
        self.titles[key] = title
        return title

    def get_requests(self) -> None:
        """Write a point for each request still waiting.

        That is one pending approval, or approved and not available yet (Seerr's "processing").
        """
        params = {'take': REQUESTS_PER_RUN, 'skip': 0, 'filter': 'all', 'sort': 'added'}
        get = self.get('/api/v1/request', params)
        if get is False:
            return
        if not isinstance(get, dict) or not isinstance(get.get('results'), list):
            self.logger.error("Unexpected reply from Seerr's request list: %s", get)
            return

        now = datetime.now(UTC).astimezone().isoformat()
        points = []
        for request in get['results']:
            if not isinstance(request, dict):
                self.logger.error('Skipping a Seerr entry that is not an object: %s', request)
                continue
            try:
                media = request['media']
                status = REQUEST_STATUS.get(request['status'])
                is4k = bool(request.get('is4k'))
                media_type = request.get('type') or media['mediaType']
                tmdb_id = media['tmdbId']
            except (KeyError, TypeError) as e:
                self.logger.error('Skipping a Seerr request without its media (%s): %s', e, request.get('id'))
                continue
            media_status = media.get('status4k') if is4k else media.get('status')
            if status == 'pending':
                state = 'pending'
            elif status == 'approved' and media_status != MEDIA_AVAILABLE:
                state = 'processing'
            else:
                continue
            requested_by = request.get('requestedBy') or {}
            points.append(
                {
                    'measurement': 'Seerr',
                    'tags': {
                        'type': 'Requests',
                        'server': self.server.id,
                        'request_type': media_type,
                        'title': self.title(media_type, tmdb_id),
                        'status': state,
                        'is4k': is4k,
                        'requested_date': request.get('createdAt', ''),
                        # A display name only: the user object also holds the requester's email address.
                        'requested_user': (
                            requested_by.get('displayName')
                            or requested_by.get('plexUsername')
                            or requested_by.get('username')
                            or ''
                        ),
                    },
                    'time': now,
                    'fields': {'tmdb_id': tmdb_id},
                }
            )
        self.output.write_points(points)
