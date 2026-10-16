"""Replies from Sonarr 4 and Radarr 5 (API v3), and stand-ins that write the points the SickChill and Ombi
modules write. Shared by the tests and the CI sample scrape."""
from types import SimpleNamespace

from varken.structures import RadarrServer, SonarrServer

SONARR = SonarrServer(api_key='sonarr-key', id=1, url='http://sonarr.example.com:8989', missing_days=7,
                      future_days=1, queue=True)
RADARR = RadarrServer(api_key='radarr-key', id=1, url='http://radarr.example.com:7878', queue=True,
                      get_missing=True)

# Shapes of Sonarr 4's /api/v3/calendar?includeSeries=true and /api/v3/queue?includeSeries&includeEpisode
# (trimmed to the fields Varken reads, plus a few it ignores).
CALENDAR = [
    {'id': 11, 'seriesId': 1, 'seasonNumber': 2, 'episodeNumber': 3, 'title': 'An Episode',
     'airDateUtc': '2026-10-14T01:00:00Z', 'hasFile': False, 'monitored': True, 'runtime': 42,
     'series': {'title': 'A Show', 'year': 2024}},
    {'id': 12, 'seriesId': 1, 'seasonNumber': 2, 'episodeNumber': 4, 'title': 'Got It',
     'airDateUtc': '2026-10-13T01:00:00Z', 'hasFile': True, 'monitored': True, 'series': {'title': 'A Show'}},
    {'id': 13, 'seriesId': 2, 'seasonNumber': 1, 'episodeNumber': 1, 'title': 'Unmonitored',
     'airDateUtc': '2026-10-12T01:00:00Z', 'hasFile': False, 'monitored': False, 'series': {'title': 'Other'}},
]
SONARR_QUEUE = {'page': 1, 'pageSize': 1000, 'totalRecords': 2, 'records': [
    {'id': 21, 'protocol': 'usenet', 'status': 'downloading', 'quality': {'quality': {'name': 'WEBDL-1080p'}},
     'series': {'title': 'A Show'}, 'episode': {'seasonNumber': 2, 'episodeNumber': 5, 'title': 'Next One'}},
    # A download Sonarr couldn't match to an episode: skipped, not an error.
    {'id': 22, 'protocol': 'torrent', 'status': 'warning', 'quality': {'quality': {'name': 'Unknown'}}},
]}
MOVIES = [
    {'id': 1, 'title': 'Released Film', 'year': 2025, 'tmdbId': 101, 'titleSlug': 'released-film-2025',
     'monitored': True, 'hasFile': False, 'isAvailable': True},
    {'id': 2, 'title': 'Future Film', 'year': 2027, 'tmdbId': 102, 'titleSlug': 'future-film-2027',
     'monitored': True, 'hasFile': False, 'isAvailable': False},
    {'id': 3, 'title': 'Have It', 'year': 2020, 'tmdbId': 103, 'monitored': True, 'hasFile': True},
    {'id': 4, 'title': 'Not Wanted', 'year': 2019, 'tmdbId': 104, 'monitored': False, 'hasFile': False},
]
# Shapes of Lidarr 2's /api/v1/calendar?includeArtist=true and /api/v1/queue.
LIDARR = SonarrServer(api_key='lidarr-key', id=1, url='http://lidarr.example.com:8686', missing_days=30,
                      future_days=7, queue=True)
ALBUMS = [
    {'id': 41, 'title': 'Half There', 'releaseDate': '2026-10-01T00:00:00Z', 'monitored': True,
     'artist': {'artistName': 'A Band'}, 'statistics': {'trackFileCount': 5, 'trackCount': 10, 'percentOfTracks': 50},
     'albumType': 'Album', 'ratings': {'votes': 0}},
    {'id': 42, 'title': 'All There', 'releaseDate': '2026-09-20T00:00:00Z', 'monitored': True,
     'artist': {'artistName': 'A Band'}, 'statistics': {'trackFileCount': 8, 'trackCount': 8, 'percentOfTracks': 100}},
    {'id': 43, 'title': 'Not Yet', 'releaseDate': '2026-10-18T00:00:00Z', 'monitored': True,
     'artist': {'artistName': 'B Band'}},
]
LIDARR_QUEUE = {'page': 1, 'totalRecords': 2, 'records': [
    {'id': 51, 'artistId': 7, 'albumId': 41, 'title': 'A.Band-Half.There-FLAC', 'protocol': 'torrent',
     'indexer': 'Some Indexer', 'quality': {'quality': {'name': 'FLAC'}}, 'status': 'downloading',
     'artist': {'artistName': 'A Band'}, 'album': {'title': 'Half There'}},
    # A download Lidarr hasn't matched to an album: listed under its release name only.
    {'id': 52, 'title': 'Unknown.Release-MP3', 'protocol': 'usenet', 'quality': {'quality': {'name': 'MP3-320'}}},
]}
RADARR_QUEUE = {'page': 1, 'totalRecords': 1, 'records': [
    {'id': 31, 'protocol': 'torrent', 'quality': {'quality': {'name': 'Bluray-2160p'}},
     'movie': {'title': 'Released Film', 'year': 2025, 'titleSlug': 'released-film-2025'}},
]}


class SickChillAPI:
    """Writes the points the real SickChill module writes."""
    server = SimpleNamespace(id=1)

    def __init__(self, output):
        self.output = output

    def get_missing(self):
        self.output.write_points([
            {'measurement': 'SickChill', 'tags': {'type': 3, 'name': 'A Show', 'epname': 'Tonight', 'sxe': 'S01E02',
                                                  'airdate': '2026-10-15', 'server': 1}, 'fields': {}},
            {'measurement': 'SickChill', 'tags': {'type': 4, 'name': 'B Show', 'epname': 'Gone', 'sxe': 'S03E01',
                                                  'airdate': '2026-10-01', 'server': 1}, 'fields': {}},
        ])


class OmbiAPI:
    """Writes the points the real Ombi module writes."""
    server = SimpleNamespace(id=1)

    def __init__(self, output):
        self.output = output

    def get_request_counts(self):
        self.output.write_points([{'measurement': 'Ombi', 'tags': {'type': 'Request_Counts'},
                                   'fields': {'pending': 3, 'approved': 2, 'available': 40}}])

    def get_issue_counts(self):
        self.output.write_points([{'measurement': 'Ombi', 'tags': {'type': 'Issues_Counts'},
                                   'fields': {'pending': 1, 'in_progress': 0, 'resolved': 9}}])

    def get_all_requests(self):
        self.output.write_points([
            {'measurement': 'Ombi', 'tags': {'type': 'Request_Total', 'server': 1},
             'fields': {'total': 2, 'movies': 1, 'tv_shows': 1}},
            {'measurement': 'Ombi', 'tags': {'type': 'Requests', 'server': 1, 'request_type': 1, 'status': 3,
                                             'title': 'A Film', 'requested_user': 'someone',
                                             'requested_date': '2026-10-10T12:00:00'}, 'fields': {}},
            {'measurement': 'Ombi', 'tags': {'type': 'Requests', 'server': 1, 'request_type': 0, 'status': 2,
                                             'title': 'A Show', 'requested_user': 'someone',
                                             'requested_date': '2026-10-01T08:00:00'}, 'fields': {}},
        ])
