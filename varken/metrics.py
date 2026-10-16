"""Varken's output: a Prometheus /metrics endpoint built from the points each scheduled job writes.

Every job (Tautulli activity, Sonarr's queue, ...) runs through Metrics.run, which collects the points the job hands
to write_points, and whether all of its requests succeeded and it logged no error (the modules log at ERROR when a
reply can't be used). When the job ends, its points replace that job's previous
snapshot; a failed run drops it, so nothing stale is exported. Scrapes only read the snapshots: they never call a
service.
"""
from logging import ERROR, Handler, getLogger
from threading import Lock, local
from time import time

from prometheus_client import CollectorRegistry, start_http_server
from prometheus_client.core import GaugeMetricFamily as _GaugeMetricFamily

from varken import BRANCH, VERSION, helpers

JOB_LABELS = ['service', 'server', 'job']
PLAYER_STATES = {0: 'playing', 1: 'paused', 3: 'buffering'}
# What the Tautulli module records when a viewer can't be located; exported as "" instead.
UNKNOWN_PLACE = ('👽', 37.234332396, -115.80666344)
OMBI_REQUEST_STATUS = {0: 'denied', 1: 'approved', 2: 'available', 3: 'pending'}
SICKCHILL_STATUS = {0: 'future', 1: 'later', 2: 'soon', 3: 'today', 4: 'missed'}


def job_key(job, kwargs):
    """(service, server id, job name) for a module's job, or None for anything else (the GeoIP update)."""
    api = getattr(job, '__self__', None)
    server = getattr(api, 'server', None)
    if server is None:
        return None
    service = type(api).__name__.removesuffix('API').lower()
    # get_calendar runs once per query: "missing" or "future".
    name = kwargs['query'].lower() if 'query' in kwargs else job.__name__.removeprefix('get_')
    return service, str(server.id), name


def label(value):
    """A tag value as a label value: 'Direct Play' -> 'direct_play'."""
    return str(value).strip().lower().replace(' ', '_')


def text(value):
    """A tag value as label text; None becomes ""."""
    return '' if value is None else str(value)


def flag(value):
    """A 0/1 tag as "true"/"false"."""
    return 'true' if str(value) in ('1', 'True', 'true') else 'false'


def printable(value):
    """Text as it can go into the scrape: a lone surrogate (JSON can carry one, "\\ud800") becomes U+FFFD. Left in,
    it would make the whole scrape fail to encode, every metric with it."""
    return value.encode('utf-16', 'surrogatepass').decode('utf-16', 'replace') if isinstance(value, str) else value


class GaugeMetricFamily(_GaugeMetricFamily):
    """prometheus_client's gauge family, with every label value made printable."""

    def add_metric(self, labels, value, timestamp=None):
        super().add_metric([printable(label) for label in labels], value, timestamp)


class InfoFamily(GaugeMetricFamily):
    """A family of info series (one per item, value 1) that leaves out a label set it already has: two items that
    look the same (two downloads of one episode, say) must not make a duplicate series, which Prometheus drops."""

    def __init__(self, name, documentation, labels):
        super().__init__(name, documentation, labels=labels)
        self.seen = set()

    def add_metric(self, labels, value, timestamp=None):
        key = tuple(labels)
        if key not in self.seen:
            self.seen.add(key)
            super().add_metric(labels, value, timestamp)


def info(name, documentation, labels):
    return InfoFamily(name, documentation, labels)


class JobErrors(Handler):
    """Marks the running job as failed when it logs an error."""

    def __init__(self, current):
        super().__init__(level=ERROR)
        self.current = current

    def emit(self, record):
        if getattr(self.current, 'points', None) is not None:
            self.current.errored = True


class JobState(object):
    def __init__(self):
        self.up = False
        self.last_success = None
        self.points = []


class Metrics(object):
    def __init__(self, server):
        self.server = server
        self.logger = getLogger()
        self.lock = Lock()
        self.jobs = {}
        self.current = local()
        self.registry = CollectorRegistry()
        self.registry.register(self)
        self.logger.addHandler(JobErrors(self.current))

    def start(self):
        try:
            start_http_server(self.server.port, addr=self.server.bind, registry=self.registry)
        except OSError as e:
            self.logger.error('Could not serve Prometheus metrics on %s:%s (%s). Is the port in use? Exiting.',
                              self.server.bind, self.server.port, e)
            exit(1)
        self.logger.info('Serving Prometheus metrics on %s:%s/metrics', self.server.bind, self.server.port)

    def run(self, job, **kwargs):
        """Run a scheduled job and record its outcome and the points it wrote."""
        key = job_key(job, kwargs)
        if key is None:
            job(**kwargs)
            return
        self.current.points = []
        self.current.errored = False
        helpers.request_state.failed = False
        succeeded = False
        try:
            job(**kwargs)
            succeeded = not helpers.request_state.failed and not self.current.errored
        finally:
            points, self.current.points = self.current.points, None
            self.record(key, succeeded, points)

    def write_points(self, points):
        """Called by the service modules with each batch of points; only points written inside a job count."""
        collected = getattr(self.current, 'points', None)
        if collected is not None:
            collected.extend(points)

    def record(self, key, succeeded, points):
        with self.lock:
            state = self.jobs.setdefault(key, JobState())
            state.up = succeeded
            if succeeded:
                state.last_success = time()
                state.points = points
            else:
                state.points = []

    def snapshot(self):
        with self.lock:
            return {key: (state.up, state.last_success, list(state.points)) for key, state in self.jobs.items()}

    def collect(self):
        jobs = self.snapshot()

        build_info = GaugeMetricFamily('varken_build_info', 'Varken version and branch; always 1.',
                                       labels=['version', 'branch'])
        build_info.add_metric([VERSION, BRANCH], 1)
        yield build_info

        up = GaugeMetricFamily('varken_job_up',
                               'Whether the last run of the job had no failed request and logged no error (1) or '
                               'not (0).',
                               labels=JOB_LABELS)
        last_success = GaugeMetricFamily('varken_job_last_success_timestamp_seconds',
                                         'When the job last ran with no failed request and no logged error, in '
                                         'Unix time.',
                                         labels=JOB_LABELS)
        points = GaugeMetricFamily('varken_job_points',
                                   "Points the job's last successful run wrote; for queue, missing and future jobs, "
                                   'the number of items.', labels=JOB_LABELS)
        for key, (ok, last, written) in sorted(jobs.items()):
            up.add_metric(list(key), 1 if ok else 0)
            if last is not None:
                last_success.add_metric(list(key), last)
            if ok:
                points.add_metric(list(key), len(written))
        yield up
        yield last_success
        yield points

        yield from self.tautulli(jobs)
        yield from self.arrs(jobs)
        yield from self.ombi(jobs)
        yield from self.seerr(jobs)

    def tautulli(self, jobs):
        streams = GaugeMetricFamily('varken_tautulli_streams', 'Current streams.', labels=['server'])
        by_decision = GaugeMetricFamily('varken_tautulli_streams_by_decision',
                                        'Current streams by transcode decision.', labels=['server', 'decision'])
        bandwidth = GaugeMetricFamily('varken_tautulli_bandwidth_bytes_per_second',
                                      'Bandwidth of the current streams, in total and on the LAN and WAN.',
                                      labels=['server', 'network'])
        sessions = GaugeMetricFamily('varken_tautulli_sessions',
                                     'Current sessions by state, media type, decisions, quality and platform.',
                                     labels=['server', 'state', 'media_type', 'transcode_decision', 'video_decision',
                                             'quality', 'platform'])
        libraries = GaugeMetricFamily('varken_tautulli_library_items',
                                      'Items in each library: item="total" (movies, shows, artists, ...), and '
                                      'seasons, episodes, albums or tracks where the library type has them.',
                                      labels=['server', 'library', 'type', 'item'])
        details = self.server.stream_details
        session_info = GaugeMetricFamily('varken_tautulli_session_info',
                                         'One series per current session: who watches what, how and where (the '
                                         "viewer's city and its coordinates with GeoIP on). Only with "
                                         'stream_details = true.',
                                         labels=['server', 'session_id', 'user', 'friendly_name', 'title', 'product',
                                                 'product_version', 'platform', 'quality', 'quality_profile',
                                                 'transcode_decision', 'video_decision', 'state', 'location',
                                                 'full_location', 'region_code', 'latitude', 'longitude'])
        progress = GaugeMetricFamily('varken_tautulli_session_progress_ratio',
                                     'How far into the item each current session is (0 to 1). Only with '
                                     'stream_details = true.', labels=['server', 'session_id'])

        for (service, server, job), (ok, _, written) in sorted(jobs.items()):
            if service != 'tautulli' or not ok:
                continue
            if job == 'activity':
                counts = {}
                for point in written:
                    tags = point['tags']
                    if tags.get('type') == 'current_stream_stats':
                        fields = point['fields']
                        streams.add_metric([server], fields['stream_count'])
                        for decision, field in (('transcode', 'transcode_streams'),
                                                ('direct_play', 'direct_play_streams'),
                                                ('direct_stream', 'direct_streams')):
                            by_decision.add_metric([server, decision], fields[field])
                        # Tautulli reports kbit/s; 1 kbit/s = 125 bytes/s.
                        for network in ('total', 'lan', 'wan'):
                            bandwidth.add_metric([server, network], fields[f'{network}_bandwidth'] * 125)
                    elif tags.get('type') == 'Session':
                        state = PLAYER_STATES.get(tags.get('player_state'), 'other')
                        labels = (server, state, label(tags['media_type']), label(tags['transcode_decision']),
                                  label(tags['video_decision']), str(tags['quality']), str(tags['platform']))
                        counts[labels] = counts.get(labels, 0) + 1
                        if details:
                            located = (tags.get('latitude'), tags.get('longitude')) != UNKNOWN_PLACE[1:]
                            place = text(tags.get('location'))
                            session_info.add_metric(
                                [server, text(tags['session_id']), text(tags['username']),
                                 text(tags.get('friendly_name')), text(tags['title']), text(tags['product']),
                                 text(tags.get('product_version')), text(tags['platform']), text(tags['quality']),
                                 text(tags.get('quality_profile')), label(tags['transcode_decision']),
                                 label(tags['video_decision']), state, '' if place == UNKNOWN_PLACE[0] else place,
                                 text(tags.get('full_location')), text(tags.get('region_code')),
                                 text(tags.get('latitude')) if located else '',
                                 text(tags.get('longitude')) if located else ''], 1)
                            try:
                                progress.add_metric([server, str(tags['session_id'])],
                                                    float(tags['progress_percent']) / 100)
                            except (TypeError, ValueError):
                                pass
                for labels, count in sorted(counts.items()):
                    sessions.add_metric(list(labels), count)
            elif job == 'stats':
                for point in written:
                    tags = point['tags']
                    for item, value in point['fields'].items():
                        libraries.add_metric([server, str(tags['section_name']), str(tags['section_type']), item],
                                             value)

        yield streams
        yield by_decision
        yield bandwidth
        yield sessions
        yield libraries
        if details:
            yield session_info
            yield progress

    def arrs(self, jobs):
        """Sonarr, Radarr, Lidarr and SickChill items: what's queued, missing or coming out."""
        sonarr_queue = info('varken_sonarr_queue_item_info', "One series per episode in Sonarr's download queue.",
                            ['server', 'series', 'episode', 'title', 'protocol', 'quality'])
        sonarr_episodes = info('varken_sonarr_episode_info',
                               'One series per episode Sonarr is missing (kind="missing": monitored, aired in the '
                               'last missing_days, no file) or that airs soon (kind="future": today through '
                               'future_days).',
                               ['server', 'kind', 'series', 'episode', 'title', 'airs', 'downloaded'])
        radarr_queue = info('varken_radarr_queue_item_info', "One series per movie in Radarr's download queue.",
                            ['server', 'movie', 'quality', 'protocol'])
        radarr_missing = info('varken_radarr_missing_info',
                              'One series per monitored movie Radarr has no file for; available="true" once it '
                              'is released.', ['server', 'movie', 'available'])
        lidarr_queue = info('varken_lidarr_queue_item_info', "One series per release in Lidarr's download queue.",
                            ['server', 'artist', 'album', 'release', 'quality', 'protocol'])
        lidarr_albums = info('varken_lidarr_album_info',
                             'One series per album Lidarr is missing tracks for (kind="missing": monitored, '
                             'released in the last missing_days) or that comes out soon (kind="future": today '
                             'through future_days).',
                             ['server', 'kind', 'artist', 'album', 'released', 'tracks'])
        sickchill_episodes = info('varken_sickchill_episode_info',
                                  "One series per episode on SickChill's coming-episodes list.",
                                  ['server', 'show', 'episode', 'title', 'airdate', 'status'])
        for (service, server, job), (ok, _, written) in sorted(jobs.items()):
            if not ok:
                continue
            for point in written:
                tags = point.get('tags', {})
                if service == 'sonarr' and job == 'queue':
                    sonarr_queue.add_metric([server, text(tags.get('name')), text(tags.get('sxe')),
                                             text(tags.get('epname')), label(tags.get('protocol', '')),
                                             text(tags.get('quality'))], 1)
                elif service == 'sonarr' and job in ('missing', 'future'):
                    sonarr_episodes.add_metric([server, job, text(tags.get('name')), text(tags.get('sxe')),
                                                text(tags.get('epname')), text(tags.get('airsUTC')),
                                                flag(tags.get('downloaded'))], 1)
                elif service == 'radarr' and job == 'queue':
                    radarr_queue.add_metric([server, text(tags.get('name')), text(tags.get('quality')),
                                             label(tags.get('protocol', ''))], 1)
                elif service == 'radarr' and job == 'missing':
                    available = 'true' if str(tags.get('Missing_Available')) == '0' else 'false'
                    radarr_missing.add_metric([server, text(tags.get('name')), available], 1)
                elif service == 'lidarr' and job == 'queue':
                    lidarr_queue.add_metric([server, text(tags.get('artistName')), text(tags.get('albumName')),
                                             text(tags.get('title')), text(tags.get('quality')),
                                             label(tags.get('protocol', ''))], 1)
                elif service == 'lidarr' and job in ('missing', 'future'):
                    lidarr_albums.add_metric([server, job, text(tags.get('artistName')), text(tags.get('albumName')),
                                              text(tags.get('releaseDate')), text(tags.get('completeCount'))], 1)
                elif service == 'sickchill' and job == 'missing':
                    sickchill_episodes.add_metric([server, text(tags.get('name')), text(tags.get('sxe')),
                                                   text(tags.get('epname')), text(tags.get('airdate')),
                                                   SICKCHILL_STATUS.get(tags.get('type'), 'other')], 1)
        yield sonarr_queue
        yield sonarr_episodes
        yield radarr_queue
        yield radarr_missing
        yield lidarr_queue
        yield lidarr_albums
        yield sickchill_episodes

    def ombi(self, jobs):
        """Ombi's request and issue counts, and each request."""
        requests = info('varken_ombi_requests', 'Ombi requests by status.', ['server', 'status'])
        issues = info('varken_ombi_issues', 'Ombi issues by status.', ['server', 'status'])
        request_info = info('varken_ombi_request_info',
                            'One series per Ombi request; user (the requester) only with stream_details = true.',
                            ['server', 'type', 'title', 'status', 'requested', 'user'])
        details = self.server.stream_details
        for (service, server, job), (ok, _, written) in sorted(jobs.items()):
            if service != 'ombi' or not ok:
                continue
            for point in written:
                tags, fields = point.get('tags', {}), point.get('fields', {})
                if job == 'request_counts':
                    for status in ('pending', 'approved', 'available'):
                        if status in fields:
                            requests.add_metric([server, status], fields[status])
                elif job == 'issue_counts':
                    for status in ('pending', 'in_progress', 'resolved'):
                        if status in fields:
                            issues.add_metric([server, status], fields[status])
                elif job == 'all_requests' and tags.get('type') == 'Requests':
                    request_info.add_metric(
                        [server, 'movie' if tags.get('request_type') == 1 else 'tv', text(tags.get('title')),
                         OMBI_REQUEST_STATUS.get(tags.get('status'), 'other'), text(tags.get('requested_date')),
                         text(tags.get('requested_user')) if details else ''], 1)
        yield requests
        yield issues
        yield request_info

    def seerr(self, jobs):
        """Seerr's request and issue counts, and each request still waiting."""
        requests = info('varken_seerr_requests', 'Seerr requests by status, as Seerr counts them: approved includes '
                        'processing (approved, not available yet) and available.', ['server', 'status'])
        requests_by_type = info('varken_seerr_requests_by_type', 'Seerr requests by media type.',
                                ['server', 'type'])
        issues = info('varken_seerr_issues', 'Seerr issues by status.', ['server', 'status'])
        issues_by_type = info('varken_seerr_issues_by_type', 'Seerr issues by type.', ['server', 'type'])
        request_info = info('varken_seerr_request_info',
                            'One series per Seerr request still waiting (pending approval, or approved and not '
                            'available yet); user (the requester) only with stream_details = true.',
                            ['server', 'type', 'title', 'status', 'is4k', 'requested', 'user'])
        details = self.server.stream_details
        for (service, server, job), (ok, _, written) in sorted(jobs.items()):
            if service != 'seerr' or not ok:
                continue
            for point in written:
                tags, fields = point.get('tags', {}), point.get('fields', {})
                if job == 'request_counts':
                    for status in ('pending', 'approved', 'declined', 'processing', 'available', 'completed'):
                        if status in fields:
                            requests.add_metric([server, status], fields[status])
                    for kind in ('movie', 'tv'):
                        if kind in fields:
                            requests_by_type.add_metric([server, kind], fields[kind])
                elif job == 'issue_counts':
                    for status in ('open', 'closed'):
                        if status in fields:
                            issues.add_metric([server, status], fields[status])
                    for kind, field in (('video', 'video'), ('audio', 'audio'), ('subtitles', 'subtitles'),
                                        ('other', 'others')):
                        if field in fields:
                            issues_by_type.add_metric([server, kind], fields[field])
                elif job == 'requests' and tags.get('type') == 'Requests':
                    request_info.add_metric(
                        [server, text(tags.get('request_type')), text(tags.get('title')), text(tags.get('status')),
                         flag(tags.get('is4k')), text(tags.get('requested_date')),
                         text(tags.get('requested_user')) if details else ''], 1)
        yield requests
        yield requests_by_type
        yield issues
        yield issues_by_type
        yield request_info
