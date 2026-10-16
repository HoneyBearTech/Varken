# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
"""Replies from Seerr 3.5's API, shared by the tests and the CI sample scrape. The counts are the fields a live
Seerr 3.5.0 returns; the requests follow its MediaRequest and Media entities (server/entity/*.ts)."""
from varken.structures import SeerrServer

SEERR = SeerrServer(api_key='seerr-key', id=1, url='http://seerr.example.com:5055', get_request_counts=True,
                    get_issue_counts=True, get_requests=True)

REQUEST_COUNTS = {'total': 12, 'movie': 8, 'tv': 4, 'pending': 2, 'approved': 9, 'declined': 1, 'processing': 3,
                  'available': 6, 'completed': 0}
ISSUE_COUNTS = {'total': 5, 'video': 2, 'audio': 1, 'subtitles': 1, 'others': 1, 'open': 3, 'closed': 2}


def user(name):
    # The user object also carries the requester's email (and more); Varken must only ever read the display name.
    return {'id': 7, 'displayName': name, 'email': f'{name.lower()}@example.com', 'plexUsername': name,
            'userType': 1, 'permissions': 32}


REQUESTS = {'pageInfo': {'pages': 1, 'pageSize': 100, 'results': 4, 'page': 1}, 'serviceErrors': {'radarr': [],
            'sonarr': []}, 'results': [
    # Pending approval.
    {'id': 41, 'status': 1, 'type': 'movie', 'is4k': False, 'createdAt': '2026-10-15T20:00:00.000Z',
     'requestedBy': user('Alice'), 'media': {'id': 1, 'mediaType': 'movie', 'tmdbId': 603, 'status': 2,
                                             'status4k': 1}},
    # Approved, 4K, not in the 4K library yet ("processing"), though the HD copy is available.
    {'id': 42, 'status': 2, 'type': 'tv', 'is4k': True, 'createdAt': '2026-10-14T08:00:00.000Z',
     'requestedBy': user('Bob'), 'media': {'id': 2, 'mediaType': 'tv', 'tmdbId': 1399, 'status': 5, 'status4k': 3}},
    # Approved and available: done, not listed.
    {'id': 43, 'status': 2, 'type': 'movie', 'is4k': False, 'createdAt': '2026-10-01T08:00:00.000Z',
     'requestedBy': user('Alice'), 'media': {'id': 3, 'mediaType': 'movie', 'tmdbId': 550, 'status': 5,
                                             'status4k': 1}},
    # Declined: not listed.
    {'id': 44, 'status': 3, 'type': 'movie', 'is4k': False, 'createdAt': '2026-10-02T08:00:00.000Z',
     'requestedBy': user('Bob'), 'media': {'id': 4, 'mediaType': 'movie', 'tmdbId': 680, 'status': 1,
                                           'status4k': 1}},
]}

DETAILS = {
    '/api/v1/movie/603': {'id': 603, 'title': 'The Matrix', 'releaseDate': '1999-03-31'},
    '/api/v1/tv/1399': {'id': 1399, 'name': 'Game of Thrones', 'firstAirDate': '2011-04-17'},
}


def replies(extra=None):
    """Seerr's reply for each endpoint path."""
    return {'/api/v1/request/count': REQUEST_COUNTS, '/api/v1/issue/count': ISSUE_COUNTS,
            '/api/v1/request': REQUESTS, **DETAILS, **(extra or {})}
