# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
"""Tautulli API replies and fakes shared by the Tautulli and Prometheus tests."""
from types import SimpleNamespace

from geoip2.errors import AddressNotFoundError

from varken.structures import TautulliServer

SERVER = TautulliServer(api_key='tautulli-secret-key', fallback_ip='1.1.1.1', get_activity=True, get_stats=True,
                        id=1, url='http://tautulli.example.com:8181', verify_ssl=False)

SESSION = {
    'session_id': 'abc', 'session_key': '12', 'username': 'viewer', 'friendly_name': 'Viewer',
    'full_title': 'Some Show - Pilot', 'ip_address_public': '203.0.113.5', 'transcode_decision': 'copy',
    'stream_video_decision': 'transcode', 'stream_video_resolution': '1080', 'stream_video_full_resolution': '',
    'container': 'mkv', 'state': 'paused', 'product': 'Plex Web', 'product_version': '4.1-abc',
    'platform': 'windows', 'transcode_hw_decoding': 0, 'transcode_hw_encoding': 1, 'media_type': 'episode',
    'audio_codec': 'aac', 'audio_profile': 'lc', 'stream_audio_codec': 'aac', 'quality_profile': 'Original',
    'progress_percent': '42', 'relayed': 0, 'secure': 1,
}

ACTIVITY = {'response': {'data': {
    'sessions': [SESSION], 'stream_count': '1', 'total_bandwidth': '8000', 'wan_bandwidth': '0',
    'lan_bandwidth': '8000', 'stream_count_transcode': '0', 'stream_count_direct_play': '0',
    'stream_count_direct_stream': '1',
}}}

LIBRARIES = {'response': {'data': [
    {'section_name': 'Movies', 'section_type': 'movie', 'count': '10'},
    {'section_name': 'TV', 'section_type': 'show', 'count': '3', 'parent_count': '5', 'child_count': '40'},
    {'section_name': 'Music', 'section_type': 'artist', 'count': '2', 'parent_count': '4', 'child_count': '30'},
]}}


def place(city='Springfield'):
    return SimpleNamespace(location=SimpleNamespace(latitude=39.8, longitude=-89.6), city=SimpleNamespace(name=city),
                           subdivisions=SimpleNamespace(most_specific=SimpleNamespace(iso_code='IL', name='Illinois')))


class FakeOutput:
    def __init__(self):
        self.points = []

    def write_points(self, points):
        self.points.extend(points)


class FakeGeoIP:
    def __init__(self, known):
        self.known = known
        self.lookups = []

    def lookup(self, ip):
        self.lookups.append(ip)
        if ip not in self.known:
            raise AddressNotFoundError(f'{ip} not in the database')
        return self.known[ip]
