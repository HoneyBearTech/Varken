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
from prometheus_client.core import GaugeMetricFamily

from varken import BRANCH, VERSION, helpers

JOB_LABELS = ['service', 'server', 'job']
PLAYER_STATES = {0: 'playing', 1: 'paused', 3: 'buffering'}


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
                                         'One series per current session: who watches what, how and where. Only '
                                         'with stream_details = true.',
                                         labels=['server', 'session_id', 'user', 'title', 'product', 'platform',
                                                 'quality', 'transcode_decision', 'location', 'region_code'])
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
                            session_info.add_metric(
                                [server, str(tags['session_id']), str(tags['username']), str(tags['title']),
                                 str(tags['product']), str(tags['platform']), str(tags['quality']),
                                 label(tags['transcode_decision']), str(tags['location']),
                                 str(tags['region_code'] or '')], 1)
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
