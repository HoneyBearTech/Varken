# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
"""Property-based tests (Hypothesis) for what turns untrusted text into configuration and log lines: the INI file
and its VRKN_* overrides, the URL and server-id checks, and the filter that redacts secrets from the log.

Each property is a plain Hypothesis test, so fuzz/fuzz_properties.py can drive it with a coverage-guided fuzzer
(Atheris) through `.hypothesis.fuzz_one_input`: a fuzzer finding is a failing property.
"""

import io
import logging
import shutil
import tempfile
from configparser import ConfigParser
from pathlib import Path
from unittest import mock

from hypothesis import example, given
from hypothesis import strategies as st

from varken import iniparser
from varken.helpers import boolcheck, clean_sid_check
from varken.iniparser import INIParser
from varken.varkenlogger import BlacklistFilter

REPO = Path(__file__).resolve().parent.parent
EXAMPLE_INI = (REPO / 'data' / 'varken.example.ini').read_text()

# Any text, including what a file or the environment can hold that st.text() never draws: lone surrogates.
any_text = st.text(st.one_of(st.characters(), st.characters(categories=['Cs'])))
# A value the way configparser hands it over: one line, no surrounding space.
ini_value = st.text().filter(lambda text: '\n' not in text and '\r' not in text).map(str.strip)


def parser_for(ini_text, environment):
    """Run INIParser over `ini_text` as the varken.ini of a fresh data folder, with `environment` as the process's
    environment. Returns the parser, or 'exit' where Varken refuses to start (an exit(1) after an error log)."""
    with tempfile.TemporaryDirectory() as folder:
        shutil.copy(REPO / 'data' / 'varken.example.ini', Path(folder) / 'varken.example.ini')
        (Path(folder) / 'varken.ini').write_text(ini_text, encoding='utf-8', errors='surrogatepass')
        # No log capture: the parser logs every refusal, and thousands of records slow a long run to a crawl.
        logging.disable(logging.CRITICAL)
        try:
            with mock.patch.object(iniparser, 'env', dict(environment)):
                return INIParser(folder)
        except SystemExit as stop:
            assert stop.code == 1  # a refusal to start is always exit(1), never a different code
            return 'exit'
        finally:
            logging.disable(logging.NOTSET)


def example_config():
    config = ConfigParser(interpolation=None)
    config.read_string(EXAMPLE_INI)
    return config


CONFIG_KEYS = [(name, key) for name, section in example_config().items() for key in section]


def with_values(values):
    """The example config with some keys given other values. `values` maps (section, key) to text."""
    config = example_config()
    for (section, key), value in values.items():
        config[section][key] = value
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


def check_parsed(parser):
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
def test_any_config_and_environment_starts_cleanly_or_refuses_with_exit_1(values, environment):
    parser = parser_for(with_values(values), environment)
    if parser != 'exit':
        check_parsed(parser)


@given(any_text, st.booleans())
def test_url_check_returns_the_url_untouched_or_refuses_to_start(url, include_port):
    parser = INIParser.__new__(INIParser)
    parser.logger = logging.getLogger()
    try:
        checked = parser.url_check(url, include_port=include_port, section='sonarr-1')
    except SystemExit as stop:
        assert stop.code == 1
    else:
        assert checked == url


@given(any_text)
@example('localhost\n')
@example('sonarr:8989/path\n')
def test_a_url_that_passes_has_no_line_break_in_it(url):
    parser = INIParser.__new__(INIParser)
    parser.logger = logging.getLogger()
    try:
        checked = parser.url_check(url, section='sonarr-1')
    except SystemExit:
        return
    assert '\n' not in checked and '\r' not in checked  # it ends up in a request line and in log lines


@given(any_text)
def test_server_ids_are_integers_or_false(text):
    ids = clean_sid_check(text, 'sonarr')
    assert ids is False or (ids and all(isinstance(i, int) for i in ids))


@given(any_text)
def test_boolcheck_is_a_bool_and_only_true_or_yes_are_true(text):
    assert boolcheck(text) is (text.lower() in ('true', 'yes'))


secrets = st.lists(
    st.text(st.characters(categories=['L', 'N']), min_size=4, max_size=12), min_size=1, max_size=4, unique=True
)


@given(secrets, any_text, any_text)
@example(['key'], 'GET /api?apikey=', '')
@example(['key'], '', 'https://host/?apikey=')
def test_no_secret_survives_the_log_filter(secret_list, text_in_message, text_in_argument):
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
