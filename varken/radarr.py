from logging import getLogger
from requests import Session, Request
from datetime import datetime, timezone

from varken.helpers import hashit, connection_handler


def movie_name(movie):
    return f"{movie.get('title', '')} ({movie.get('year', '')})"


class RadarrAPI(object):
    """Radarr through its v3 API (Radarr 3 and later)."""

    def __init__(self, server, output):
        self.output = output
        self.server = server
        # Create session to reduce server web thread load, and globally define pageSize for all requests
        self.session = Session()
        self.session.headers = {'X-Api-Key': self.server.api_key}
        self.logger = getLogger()

    def __repr__(self):
        return f"<radarr-{self.server.id}>"

    def get_missing(self):
        endpoint = '/api/v3/movie'
        now = datetime.now(timezone.utc).astimezone().isoformat()
        points = []

        req = self.session.prepare_request(Request('GET', self.server.url + endpoint))
        get = connection_handler(self.session, req, self.server.verify_ssl)

        if get is False:
            return
        if not isinstance(get, list):
            self.logger.error('Unexpected reply from Radarr\'s movie list (is it Radarr 3 or later?): %s', get)
            return

        for movie in get:
            if not movie.get('monitored') or movie.get('hasFile'):
                continue
            # Missing_Available: 0 once Radarr considers the movie released (available), 1 before that.
            ma = 0 if movie.get('isAvailable') else 1
            name = movie_name(movie)
            hash_id = hashit(f"{self.server.id}{name}{movie.get('tmdbId')}")
            points.append(
                {
                    "measurement": "Radarr",
                    "tags": {
                        "Missing": True,
                        "Missing_Available": ma,
                        "tmdbId": movie.get('tmdbId'),
                        "server": self.server.id,
                        "name": name,
                        "titleSlug": movie.get('titleSlug', '')
                    },
                    "time": now,
                    "fields": {
                        "hash": hash_id
                    }
                }
            )

        self.output.write_points(points)

    def get_queue(self):
        endpoint = '/api/v3/queue'
        params = {'includeMovie': 'true', 'pageSize': 1000}
        now = datetime.now(timezone.utc).astimezone().isoformat()
        points = []

        req = self.session.prepare_request(Request('GET', self.server.url + endpoint, params=params))
        get = connection_handler(self.session, req, self.server.verify_ssl)

        if get is False:
            return
        if not isinstance(get, dict) or not isinstance(get.get('records'), list):
            self.logger.error('Unexpected reply from Radarr\'s queue (is it Radarr 3 or later?): %s', get)
            return

        for item in get['records']:
            try:
                movie = item['movie']
                quality = item['quality']['quality']['name']
            except (KeyError, TypeError) as e:
                # A queue entry Radarr hasn't matched to a movie.
                self.logger.debug('Skipping a Radarr queue entry without a movie (%s): %s', e, item)
                continue
            protocol = str(item.get('protocol', '')).upper()
            name = movie_name(movie)
            hash_id = hashit(f'{self.server.id}{name}{quality}')
            points.append(
                {
                    "measurement": "Radarr",
                    "tags": {
                        "type": "Queue",
                        "tmdbId": item.get('id'),
                        "server": self.server.id,
                        "name": name,
                        "quality": quality,
                        "protocol": protocol,
                        "protocol_id": 1 if protocol == 'USENET' else 0,
                        "titleSlug": movie.get('titleSlug', '')
                    },
                    "time": now,
                    "fields": {
                        "hash": hash_id
                    }
                }
            )

        self.output.write_points(points)
