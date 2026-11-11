# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
"""Property-based tests (Hypothesis) for what turns untrusted text into behaviour: the INI file and its VRKN_*
overrides, the URL and server-id checks, the filter that redacts secrets from the log, the services' JSON replies
and the label text that ends up in /metrics.

Each property is a plain Hypothesis test, so fuzz/fuzz_properties.py can drive it with a coverage-guided fuzzer
(Atheris) through `.hypothesis.fuzz_one_input`: a fuzzer finding is a failing property.
"""

import io
import logging
import shutil
import tempfile
from configparser import ConfigParser
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest import mock

from hypothesis import example, given
from hypothesis import strategies as st
from prometheus_client import generate_latest
from prometheus_client.parser import text_string_to_metric_families

from tests.arrs_data import LIDARR, RADARR, SONARR
from tests.seerr_data import SEERR
from varken import iniparser, lidarr, radarr, seerr, sonarr
from varken.helpers import boolcheck, clean_sid_check
from varken.iniparser import INIParser
from varken.lidarr import LidarrAPI
from varken.metrics import Metrics, printable
from varken.radarr import RadarrAPI
from varken.seerr import SeerrAPI
from varken.sonarr import SonarrAPI
from varken.structures import PrometheusServer
from varken.varkenlogger import BlacklistFilter

if TYPE_CHECKING:
    from collections.abc import Collection

REPO = Path(__file__).resolve().parent.parent
EXAMPLE_INI = (REPO / 'data' / 'varken.example.ini').read_text()

# Any text, including what a file or the environment can hold that st.text() never draws: lone surrogates.
any_text = st.text(st.one_of(st.characters(), st.characters(categories=['Cs'])))
# A value the way configparser hands it over: one line, no surrounding space.
ini_value = st.text().filter(lambda text: '\n' not in text and '\r' not in text).map(str.strip)


def parser_for(ini_text: str, environment: dict[str, str]) -> INIParser | str:
    """Run INIParser over `ini_text` as the varken.ini of a fresh data folder, with `environment` as the process's
    environment. Returns the parser, or 'exit' where Varken refuses to start (an exit(1) after an error log)."""
    with tempfile.TemporaryDirectory() as folder:
        shutil.copy(REPO / 'data' / 'varken.example.ini', Path(folder) / 'varken.example.ini')
        ini = Path(folder) / 'varken.ini'
        ini.write_text(ini_text, encoding='utf-8', errors='surrogatepass')
        written = ini.read_bytes()
        # No log capture: the parser logs every refusal, and thousands of records slow a long run to a crawl.
        logging.disable(logging.CRITICAL)
        try:
            with mock.patch.object(iniparser, 'env', dict(environment)):
                return INIParser(folder)
        except SystemExit as stop:
            # A refusal to start is always exit(1), never a different code. Starting is fine too, so there is
            # nothing for pytest.raises to expect.
            assert stop.code == 1  # noqa: PT017
            return 'exit'
        finally:
            logging.disable(logging.NOTSET)
            assert ini.read_bytes() == written  # an existing varken.ini is the user's: Varken never writes to it


def example_config() -> ConfigParser:
    config = ConfigParser(interpolation=None)
    config.read_string(EXAMPLE_INI)
    return config


CONFIG_KEYS = [(name, key) for name, section in example_config().items() for key in section]


def with_values(values: dict[tuple[str, str], str], without: Collection[tuple[str, str]] = ()) -> str:
    """The example config with some keys given other values, and some left out. `values` maps (section, key) to
    text; `without` holds the (section, key) pairs to leave out. A section left with no keys goes too."""
    config = example_config()
    for (section, key), value in values.items():
        config[section][key] = value
    for section, key in without:
        config.remove_option(section, key)
        if not config[section]:
            config.remove_section(section)
    out = io.StringIO()
    config.write(out)
    return out.getvalue()


ENV_SUFFIXES = ['URL', 'APIKEY', 'SSL', 'VERIFY_SSL', 'QUEUE_RUN_SECONDS', 'FALLBACK_IP', 'USERNAME', 'SITE']
environments = st.dictionaries(
    st.sampled_from(
        ['VRKN_PROMETHEUS_BIND', 'VRKN_PROMETHEUS_PORT', 'VRKN_PROMETHEUS_STREAM_DETAILS']
        + ['VRKN_GLOBAL_SONARR_SERVER_IDS']
        + [f'VRKN_{s}_{x}_{k}' for s in ('SONARR', 'TAUTULLI', 'UNIFI') for x in (1, 2) for k in ENV_SUFFIXES]
    ),
    any_text.filter(lambda text: '\0' not in text),
    max_size=6,
)


def check_parsed(parser: INIParser) -> None:
    """What every accepted configuration promises."""
    server = parser.prometheus_server
    assert 0 < server.port < 65536
    for service in parser.services:
        for entry in getattr(parser, f'{service}_servers'):
            assert entry is not None
            assert entry.url.startswith(('http://', 'https://'))
            assert not any(char.isspace() for char in entry.url)  # a URL never carries whitespace into a request
            if entry.url.startswith('http://'):
                assert entry.verify_ssl is False  # certificate checks only apply to HTTPS


@given(st.dictionaries(st.sampled_from(CONFIG_KEYS), ini_value, max_size=6), environments)
@example({('prometheus', 'port'): '0'}, {})
@example({('prometheus', 'bind'): 'localhost'}, {})
@example({('global', 'sonarr_server_ids'): '1,,x'}, {})
@example({('global', 'sonarr_server_ids'): '3'}, {})  # no [sonarr-3] section
@example({}, {'VRKN_SONARR_1_URL': 'sonarr.example.com\n'})
def test_any_config_and_environment_starts_cleanly_or_refuses_with_exit_1(
    values: dict[tuple[str, str], str], environment: dict[str, str]
) -> None:
    parser = parser_for(with_values(values), environment)
    if parser != 'exit':
        check_parsed(parser)


def parsed(parser: INIParser | str) -> object:
    """Everything a start-up hands to the rest of Varken."""
    if parser == 'exit':
        return parser
    return (
        parser.prometheus_server,
        [(getattr(parser, f'{service}_enabled'), getattr(parser, f'{service}_servers')) for service in parser.services],
    )


@given(st.sets(st.sampled_from(CONFIG_KEYS), max_size=12), environments)
@example({('prometheus', key) for key in ('bind', 'port', 'stream_details')}, {})  # an upstream 1.7.x file
@example({('global', 'maxmind_account_id')}, {'VRKN_TAUTULLI_1_URL': 'tautulli.example.com'})
@example({key for key in CONFIG_KEYS if key[0] == 'sonarr-2'}, {})  # a server id whose section is gone
def test_keys_missing_from_varken_ini_take_the_examples_values(
    without: set[tuple[str, str]], environment: dict[str, str]
) -> None:
    assert parsed(parser_for(with_values({}, without), environment)) == parsed(parser_for(EXAMPLE_INI, environment))


@given(any_text, st.booleans())
def test_url_check_returns_the_url_untouched_or_refuses_to_start(
    url: str,
    include_port: bool,  # noqa: FBT001 - drawn by Hypothesis, which passes it by name
) -> None:
    parser = INIParser.__new__(INIParser)
    parser.logger = logging.getLogger()
    try:
        checked = parser.url_check(url, include_port=include_port, section='sonarr-1')
    except SystemExit as stop:
        assert stop.code == 1  # noqa: PT017 - either outcome is fine
    else:
        assert checked == url


@given(any_text)
@example('localhost\n')
@example('sonarr:8989/path\n')
def test_a_url_that_passes_has_no_line_break_in_it(url: str) -> None:
    parser = INIParser.__new__(INIParser)
    parser.logger = logging.getLogger()
    try:
        checked = parser.url_check(url, section='sonarr-1')
    except SystemExit:
        return
    assert '\n' not in checked
    assert '\r' not in checked


@given(any_text)
def test_server_ids_are_integers_or_false(text: str) -> None:
    ids = clean_sid_check(text, 'sonarr')
    assert ids is False or (ids and all(isinstance(i, int) for i in ids))


@given(any_text)
def test_boolcheck_is_a_bool_and_only_true_or_yes_are_true(text: str) -> None:
    assert boolcheck(text) is (text.lower() in ('true', 'yes'))


secrets = st.lists(
    st.text(st.characters(categories=['L', 'N']), min_size=4, max_size=12), min_size=1, max_size=4, unique=True
)


@given(secrets, any_text, any_text)
@example(['key'], 'GET /api?apikey=', '')
@example(['key'], '', 'https://host/?apikey=')
def test_no_secret_survives_the_log_filter(secret_list: list[str], text_in_message: str, text_in_argument: str) -> None:
    """A secret placed in a log line's message or in one of its arguments is masked in the output. (Masking only
    inserts asterisks, so it can't join letters into another secret. Secrets are at least four characters, as real
    keys are: a one-letter "secret" such as `s` would also mask the `%s` of a format string.)"""
    message = '%s: ' + text_in_message.replace('%', '%%') + secret_list[0]
    arguments = (text_in_argument + secret_list[-1],)
    record = logging.LogRecord('varken', logging.INFO, __file__, 1, message, arguments, None)
    BlacklistFilter(secret_list).filter(record)
    output = record.getMessage()
    for secret in secret_list:
        assert secret not in output


# Any JSON document a service could send.
json_values = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | any_text,
    lambda children: st.lists(children, max_size=6) | st.dictionaries(any_text, children, max_size=6),
    max_leaves=40,
)

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
@example('sonarr_queue', {'records': [None]})
@example('radarr_missing', [None])
@example('lidarr_calendar', [1, 'text', None])
@example('seerr_requests', {'results': [None, 5]})
def test_any_reply_is_handled_and_the_scrape_stays_valid(name: str, reply: object) -> None:
    """Whatever JSON a service sends, its job doesn't raise (the scheduler would only log the traceback) and the
    scrape that follows is valid exposition text."""
    module, job, kwargs = JOBS[name]
    metrics = Metrics(PrometheusServer(stream_details=True))
    with mock.patch.object(module, 'connection_handler', return_value=reply):
        job(metrics)(**kwargs)
    list(text_string_to_metric_families(generate_latest(metrics.registry).decode()))


class SonarrAPIStub:
    """A module job that writes the points it's given (the metrics only see its class name and server id)."""

    server = SimpleNamespace(id=1)

    def __init__(self, output: Metrics, points: list[dict[str, Any]]) -> None:
        self.output, self.points = output, points

    def get_queue(self) -> None:
        self.output.write_points(self.points)


SonarrAPIStub.__name__ = 'SonarrAPI'


@given(
    st.lists(
        st.fixed_dictionaries(
            {'name': any_text, 'epname': any_text, 'sxe': any_text, 'protocol': any_text, 'quality': any_text}
        ),
        max_size=5,
    )
)
@example([{'name': '\ud800', 'epname': '', 'sxe': '', 'protocol': '', 'quality': ''}])
@example([{'name': 'x', 'epname': '', 'sxe': '', 'protocol': '', 'quality': ''}] * 2)
@example(
    [
        {'name': '\ud800', 'epname': '', 'sxe': '', 'protocol': '', 'quality': ''},
        {'name': '\ud801', 'epname': '', 'sxe': '', 'protocol': '', 'quality': ''},
    ]
)
def test_any_label_text_makes_a_scrape_that_parses_back_without_duplicate_series(items: list[dict[str, str]]) -> None:
    """A lone surrogate in a title mustn't blank the scrape, and items that look alike (or look alike once a
    surrogate is replaced) make one series, not a duplicate that Prometheus drops."""
    metrics = Metrics(PrometheusServer())
    metrics.run(SonarrAPIStub(metrics, [{'tags': tags, 'fields': {}} for tags in items]).get_queue)

    scrape = generate_latest(metrics.registry).decode()
    families = {family.name: family for family in text_string_to_metric_families(scrape)}

    series = [sample.labels for sample in families['varken_sonarr_queue_item_info'].samples] if items else []
    assert len(series) == len({tuple(sorted(labels.items())) for labels in series})
    assert len(series) == len(
        {
            tuple(
                printable(text)
                for text in (
                    i['name'],
                    i['sxe'],
                    i['epname'],
                    i['protocol'].strip().lower().replace(' ', '_'),
                    i['quality'],
                )
            )
            for i in items
        }
    )
