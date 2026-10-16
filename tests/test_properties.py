"""Property-based tests (Hypothesis) for everything that turns untrusted text into behaviour: the operator's URLs and
environment, secrets in log lines, the services' JSON replies, and the label text that ends up in /metrics.

Replies come from services Varken doesn't control and settings from whoever deploys it, so the strategies use
arbitrary JSON and arbitrary Unicode, lone surrogates included (json.loads produces them from "\\ud800" escapes).
Each property is a plain Hypothesis test, so fuzz/fuzz_properties.py can drive it with a coverage-guided fuzzer
(Atheris) through `.hypothesis.fuzz_one_input`.
"""
import logging
import os
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

from hypothesis import example, given, settings
from hypothesis import strategies as st
from prometheus_client import generate_latest
from prometheus_client.parser import text_string_to_metric_families

from tests.arrs_data import LIDARR, RADARR, SONARR
from tests.seerr_data import SEERR
from varken import lidarr, radarr, seerr, sonarr
from varken.iniparser import INIParser
from varken.lidarr import LidarrAPI
from varken.metrics import Metrics
from varken.radarr import RadarrAPI
from varken.seerr import SeerrAPI
from varken.sonarr import SonarrAPI
from varken.structures import PrometheusServer
from varken.varkenlogger import BlacklistFilter

EXAMPLE_INI = Path(__file__).resolve().parent.parent / 'data' / 'varken.example.ini'

# Any text, including what json.loads can produce but st.text() never does: lone surrogates.
any_text = st.text(st.one_of(st.characters(), st.characters(categories=['Cs'])))
# Any JSON document a service could send.
json_values = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | any_text,
    lambda children: st.lists(children, max_size=6) | st.dictionaries(any_text, children, max_size=6),
    max_leaves=40)


def url_checker():
    parser = INIParser.__new__(INIParser)
    parser.logger = logging.getLogger('properties')
    return parser


@given(any_text, st.booleans())
@example('a' * 40 + '!', True)
@example('a-' * 30 + '.', True)
@example('a.' * 30 + '-', True)
def test_url_check_accepts_or_exits_quickly_whatever_the_text(url, include_port):
    try:
        assert url_checker().url_check(url, include_port=include_port, section='test') == url
    except SystemExit:
        pass


# Settings whose values the parser converts: any text must parse or stop Varken with an error, not a traceback.
CONVERTED_SETTINGS = ['VRKN_PROMETHEUS_PORT', 'VRKN_PROMETHEUS_BIND', 'VRKN_PROMETHEUS_STREAM_DETAILS',
                      'VRKN_GLOBAL_TAUTULLI_SERVER_IDS', 'VRKN_TAUTULLI_1_GET_ACTIVITY_RUN_SECONDS',
                      'VRKN_TAUTULLI_1_FALLBACK_IP', 'VRKN_TAUTULLI_1_URL', 'VRKN_SONARR_1_MISSING_DAYS',
                      'VRKN_SONARR_1_QUEUE_RUN_SECONDS', 'VRKN_SEERR_1_GET_REQUESTS_RUN_SECONDS']


@given(st.dictionaries(st.sampled_from(CONVERTED_SETTINGS),
                       st.text(st.characters(exclude_categories=['Cs'], exclude_characters='\x00'), max_size=30),
                       max_size=4))
@settings(deadline=None)
def test_any_setting_parses_or_stops_varken_cleanly(values):
    folder = tempfile.mkdtemp()
    old = {name: os.environ.get(name) for name in values}
    try:
        shutil.copy(EXAMPLE_INI, Path(folder) / 'varken.example.ini')
        os.environ.update(values)
        try:
            INIParser(folder)
        except SystemExit:
            pass
    finally:
        for name, value in old.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        shutil.rmtree(folder, ignore_errors=True)


secrets = st.text(st.characters(exclude_characters='*', exclude_categories=['Cs']), min_size=3, max_size=20)


@given(st.lists(secrets, min_size=1, max_size=4), st.lists(st.one_of(secrets, any_text), max_size=6),
       st.data())
def test_no_configured_secret_survives_into_a_log_line(configured, noise, data):
    message = ''.join(data.draw(st.permutations(configured + noise)))
    record = logging.LogRecord('test', logging.INFO, __file__, 1, '%s', (message,), None)

    BlacklistFilter(set(configured)).filter(record)

    logged = record.getMessage()
    for secret in configured:
        assert secret not in logged


def replying(module, reply):
    module.connection_handler = lambda session, request, verify: reply


JOBS = {
    'sonarr_calendar': (sonarr, lambda m: SonarrAPI(SONARR, m).get_calendar, {'query': 'Missing'}),
    'sonarr_queue': (sonarr, lambda m: SonarrAPI(SONARR, m).get_queue, {}),
    'radarr_missing': (radarr, lambda m: RadarrAPI(RADARR, m).get_missing, {}),
    'radarr_queue': (radarr, lambda m: RadarrAPI(RADARR, m).get_queue, {}),
    'lidarr_calendar': (lidarr, lambda m: LidarrAPI(LIDARR, m).get_calendar, {'query': 'Future'}),
    'lidarr_queue': (lidarr, lambda m: LidarrAPI(LIDARR, m).get_queue, {}),
    'seerr_counts': (seerr, lambda m: SeerrAPI(SEERR, m).get_request_counts, {}),
    'seerr_requests': (seerr, lambda m: SeerrAPI(SEERR, m).get_requests, {}),
}


@given(st.sampled_from(sorted(JOBS)), json_values)
@settings(deadline=None)
def test_any_reply_is_handled_and_the_scrape_stays_valid(name, reply):
    module, job, kwargs = JOBS[name]
    handler = module.connection_handler
    metrics = Metrics(PrometheusServer(stream_details=True))
    try:
        replying(module, reply)
        job(metrics)(**kwargs)  # called directly: an exception here is a crash the scheduler would only log
    finally:
        module.connection_handler = handler
    scrape = generate_latest(metrics.registry).decode()
    list(text_string_to_metric_families(scrape))


class Job:
    """A module job that writes the points it's given (the metrics only see its class name and server id)."""
    server = SimpleNamespace(id=1)

    def __init__(self, output, points):
        self.output, self.points = output, points

    def get_queue(self):
        self.output.write_points(self.points)


class SonarrAPIStub(Job):
    pass


SonarrAPIStub.__name__ = 'SonarrAPI'


@given(st.lists(st.fixed_dictionaries({'name': any_text, 'epname': any_text, 'sxe': any_text,
                                       'protocol': any_text, 'quality': any_text}), max_size=5))
@settings(deadline=None)
def test_any_label_text_makes_a_scrape_that_parses_back(items):
    metrics = Metrics(PrometheusServer())
    metrics.run(SonarrAPIStub(metrics, [{'tags': tags, 'fields': {}} for tags in items]).get_queue)

    families = {family.name: family for family in text_string_to_metric_families(
        generate_latest(metrics.registry).decode())}

    series = families['varken_sonarr_queue_item_info'].samples if items else []
    assert len(series) == len({(i['name'], i['sxe'], i['epname'], i['protocol'].strip().lower().replace(' ', '_'),
                                i['quality']) for i in items})
