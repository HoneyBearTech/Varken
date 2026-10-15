from logging import getLogger
from requests import Session, Request
from datetime import datetime, timezone, date, timedelta

from varken.helpers import hashit, connection_handler


def episode_code(season, episode):
    return f'S{season:0>2}E{episode:0>2}'


class SonarrAPI(object):
    """Sonarr through its v3 API (Sonarr 3 and 4)."""

    def __init__(self, server, output):
        self.output = output
        self.server = server
        # Create session to reduce server web thread load, and globally define pageSize for all requests
        self.session = Session()
        self.session.headers = {'X-Api-Key': self.server.api_key}
        self.session.params = {'pageSize': 1000}
        self.logger = getLogger()

    def __repr__(self):
        return f"<sonarr-{self.server.id}>"

    def get_calendar(self, query="Missing"):
        endpoint = '/api/v3/calendar'
        today = str(date.today())
        last_days = str(date.today() - timedelta(days=self.server.missing_days))
        future = str(date.today() + timedelta(days=self.server.future_days))
        now = datetime.now(timezone.utc).astimezone().isoformat()
        if query == "Missing":
            params = {'start': last_days, 'end': today, 'includeSeries': 'true'}
        else:
            params = {'start': today, 'end': future, 'includeSeries': 'true'}
        points = []

        req = self.session.prepare_request(Request('GET', self.server.url + endpoint, params=params))
        get = connection_handler(self.session, req, self.server.verify_ssl)

        if get is False:
            return
        if not isinstance(get, list):
            self.logger.error('Unexpected reply from Sonarr\'s calendar (is it Sonarr 3 or later?): %s', get)
            return

        for show in get:
            try:
                series_title = show['series']['title']
                sxe = episode_code(show['seasonNumber'], show['episodeNumber'])
            except (KeyError, TypeError) as e:
                self.logger.error('Skipping a Sonarr calendar entry without series or episode numbers (%s): %s', e,
                                  show)
                continue
            downloaded = 1 if show.get('hasFile') else 0
            if query == "Missing" and (not show.get('monitored') or downloaded):
                continue
            hash_id = hashit(f'{self.server.id}{series_title}{sxe}')
            points.append(
                {
                    "measurement": "Sonarr",
                    "tags": {
                        "type": query,
                        "sonarrId": show.get('id'),
                        "server": self.server.id,
                        "name": series_title,
                        "epname": show.get('title', ''),
                        "sxe": sxe,
                        "airsUTC": show.get('airDateUtc', ''),
                        "downloaded": downloaded
                    },
                    "time": now,
                    "fields": {
                        "hash": hash_id
                    }
                }
            )

        self.output.write_points(points)

    def get_queue(self):
        points = []
        endpoint = '/api/v3/queue'
        params = {'includeSeries': 'true', 'includeEpisode': 'true'}
        now = datetime.now(timezone.utc).astimezone().isoformat()

        req = self.session.prepare_request(Request('GET', self.server.url + endpoint, params=params))
        get = connection_handler(self.session, req, self.server.verify_ssl)

        if get is False:
            return
        if not isinstance(get, dict) or not isinstance(get.get('records'), list):
            self.logger.error('Unexpected reply from Sonarr\'s queue (is it Sonarr 3 or later?): %s', get)
            return

        for item in get['records']:
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
                    "measurement": "Sonarr",
                    "tags": {
                        "type": "Queue",
                        "sonarrId": item.get('id'),
                        "server": self.server.id,
                        "name": series_title,
                        "epname": episode.get('title', ''),
                        "sxe": sxe,
                        "protocol": protocol,
                        "protocol_id": 1 if protocol == 'USENET' else 0,
                        "quality": quality
                    },
                    "time": now,
                    "fields": {
                        "hash": hash_id
                    }
                }
            )
        if not points:
            self.logger.debug("No queue items for sonarr instance.")
        self.output.write_points(points)
