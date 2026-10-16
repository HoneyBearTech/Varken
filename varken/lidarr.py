from logging import getLogger
from requests import Session, Request
from datetime import datetime, timezone, date, timedelta

from varken.helpers import hashit, connection_handler


class LidarrAPI(object):
    """Lidarr through its v1 API (Lidarr 1 and 2)."""

    def __init__(self, server, output):
        self.output = output
        self.server = server
        # Create session to reduce server web thread load, and globally define pageSize for all requests
        self.session = Session()
        self.session.headers = {'X-Api-Key': self.server.api_key}
        self.logger = getLogger()

    def __repr__(self):
        return f"<lidarr-{self.server.id}>"

    def get_calendar(self, query="Missing"):
        endpoint = '/api/v1/calendar'
        today = str(date.today())
        last_days = str(date.today() - timedelta(days=self.server.missing_days))
        future = str(date.today() + timedelta(days=self.server.future_days))
        now = datetime.now(timezone.utc).astimezone().isoformat()
        if query == "Missing":
            params = {'start': last_days, 'end': today, 'includeArtist': 'true'}
        else:
            params = {'start': today, 'end': future, 'includeArtist': 'true'}
        points = []

        req = self.session.prepare_request(Request('GET', self.server.url + endpoint, params=params))
        get = connection_handler(self.session, req, self.server.verify_ssl)

        if get is False:
            return
        if not isinstance(get, list):
            self.logger.error('Unexpected reply from Lidarr\'s calendar: %s', get)
            return

        for album in get:
            try:
                title = album['title']
                artist_name = album['artist']['artistName']
            except (KeyError, TypeError) as e:
                self.logger.error('Skipping a Lidarr calendar entry without a title or artist (%s): %s', e, album)
                continue
            statistics = album.get('statistics') or {}
            percent_of_tracks = statistics.get('percentOfTracks', 0)
            # Missing: monitored albums that came out in the last missing_days without every track.
            if query == "Missing" and (not album.get('monitored') or percent_of_tracks == 100):
                continue
            hash_id = hashit(f'{self.server.id}{title}{album.get("id")}')
            points.append(
                {
                    "measurement": "Lidarr",
                    "tags": {
                        "type": query,
                        "sonarrId": album.get('id'),
                        "server": self.server.id,
                        "albumName": title,
                        "artistName": artist_name,
                        "percentComplete": percent_of_tracks,
                        "completeCount": f"{statistics.get('trackFileCount', 0)}/{statistics.get('trackCount', 0)}",
                        "releaseDate": album.get('releaseDate', '')
                    },
                    "time": now,
                    "fields": {
                        "hash": hash_id
                    }
                }
            )

        self.output.write_points(points)

    def get_queue(self):
        endpoint = '/api/v1/queue'
        now = datetime.now(timezone.utc).astimezone().isoformat()
        points = []
        params = {'pageSize': 1000, 'includeArtist': 'true', 'includeAlbum': 'true'}

        req = self.session.prepare_request(Request('GET', self.server.url + endpoint, params=params))
        get = connection_handler(self.session, req, self.server.verify_ssl)

        if get is False:
            return
        if not isinstance(get, dict) or not isinstance(get.get('records'), list):
            self.logger.error('Unexpected reply from Lidarr\'s queue: %s', get)
            return

        for item in get['records']:
            try:
                quality = item['quality']['quality']['name']
            except (KeyError, TypeError):
                quality = ''
            protocol = str(item.get('protocol', ''))
            title = item.get('title', '')
            # The artist and album (with includeArtist/includeAlbum); a download Lidarr hasn't matched has neither.
            artist = (item.get('artist') or {}).get('artistName', '')
            album = (item.get('album') or {}).get('title', '')
            hash_id = hashit(f'{self.server.id}{title}{item.get("artistId")}')
            points.append(
                {
                    "measurement": "Lidarr",
                    "tags": {
                        "type": "Queue",
                        "id": item.get('id'),
                        "server": self.server.id,
                        "title": title,
                        "artistName": artist,
                        "albumName": album,
                        "quality": quality,
                        "protocol": protocol,
                        "protocol_id": 1 if protocol.upper() == 'USENET' else 0,
                        "indexer": item.get('indexer', '')
                    },
                    "time": now,
                    "fields": {
                        "hash": hash_id
                    }
                }
            )

        self.output.write_points(points)
