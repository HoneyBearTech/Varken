# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
import logging
from typing import TYPE_CHECKING

import pytest

from varken.iniparser import INIParser
from varken.structures import PrometheusServer

if TYPE_CHECKING:
    from pathlib import Path


def test_first_start_creates_varken_ini_from_the_example(data_folder: Path) -> None:
    parser = INIParser(str(data_folder))

    assert (data_folder / 'varken.ini').exists()
    assert parser.prometheus_server == PrometheusServer()
    assert parser.sonarr_enabled == [1, 2]
    assert [s.url for s in parser.sonarr_servers] == [
        'http://sonarr1.domain.tld:8989',
        'http://sonarr2.domain.tld:8989',
    ]
    assert parser.lidarr_enabled is None
    tautulli = parser.tautulli_servers[0]
    assert tautulli.fallback_ip == '1.1.1.1'
    assert tautulli.get_activity is True
    assert tautulli.get_stats_run_seconds == 3600


def test_environment_variables_override_the_file(data_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('VRKN_GLOBAL_SONARR_SERVER_IDS', 'false')
    monkeypatch.setenv('VRKN_TAUTULLI_1_URL', 'tautulli.example.com:8181')
    monkeypatch.setenv('VRKN_TAUTULLI_1_APIKEY', 'key-from-the-environment')
    monkeypatch.setenv('VRKN_TAUTULLI_1_SSL', 'true')
    monkeypatch.setenv('VRKN_TAUTULLI_1_VERIFY_SSL', 'true')

    parser = INIParser(str(data_folder))

    assert parser.sonarr_enabled is None
    assert parser.sonarr_servers == []
    tautulli = parser.tautulli_servers[0]
    assert tautulli.url == 'https://tautulli.example.com:8181'
    assert tautulli.api_key == 'key-from-the-environment'
    assert tautulli.verify_ssl is True


def test_verify_ssl_is_off_without_ssl(data_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('VRKN_TAUTULLI_1_VERIFY_SSL', 'true')

    parser = INIParser(str(data_folder))

    assert parser.tautulli_servers[0].verify_ssl is False


def test_secrets_from_environment_variables_are_redacted_from_logs(
    data_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression: only varken.ini values used to be redacted, so keys set through VRKN_* leaked into debug logs.
    monkeypatch.setenv('VRKN_TAUTULLI_1_APIKEY', 'tautulli-secret-key')
    monkeypatch.setenv('VRKN_UNIFI_1_PASSWORD', 'unifi-secret-password')
    monkeypatch.setenv('VRKN_GLOBAL_MAXMIND_LICENSE_KEY', 'maxmind-secret-key')
    monkeypatch.setenv('VRKN_TAUTULLI_1_GET_STATS_RUN_SECONDS', '600')

    parser = INIParser(str(data_folder))

    assert {'tautulli-secret-key', 'unifi-secret-password', 'maxmind-secret-key'} <= set(parser.filtered_strings)
    assert '600' not in parser.filtered_strings


def test_invalid_url_exits(data_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('VRKN_SONARR_1_URL', 'not a host name')

    with pytest.raises(SystemExit):
        INIParser(str(data_folder))


def test_private_fallback_ip_exits(data_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('VRKN_TAUTULLI_1_FALLBACK_IP', '192.168.1.10')

    with pytest.raises(SystemExit):
        INIParser(str(data_folder))


def test_a_missing_key_takes_the_examples_value_and_varken_ini_is_left_alone(data_folder: Path) -> None:
    # Regression: a missing key made Varken rewrite varken.ini from what it had parsed, which dropped every comment
    # in the file (and left it truncated if the write was interrupted).
    example = (data_folder / 'varken.example.ini').read_text()
    ini = '# Tautulli moved hosts in March; the old key is revoked.\n' + example.replace(
        'get_stats_run_seconds = 3600\n', '; stats once an hour is plenty\n'
    )
    (data_folder / 'varken.ini').write_text(ini)

    parser = INIParser(str(data_folder))

    assert parser.tautulli_servers[0].get_stats_run_seconds == 3600
    assert (data_folder / 'varken.ini').read_text() == ini


def test_prometheus_settings_from_the_environment(data_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('VRKN_PROMETHEUS_BIND', '127.0.0.1')
    monkeypatch.setenv('VRKN_PROMETHEUS_PORT', '9999')
    monkeypatch.setenv('VRKN_PROMETHEUS_STREAM_DETAILS', 'true')

    parser = INIParser(str(data_folder))

    assert parser.prometheus_server == PrometheusServer(bind='127.0.0.1', port=9999, stream_details=True)


@pytest.mark.parametrize(
    ('name', 'value'),
    [
        ('VRKN_PROMETHEUS_BIND', 'localhost'),
        ('VRKN_PROMETHEUS_PORT', '70000'),
        ('VRKN_PROMETHEUS_PORT', 'many'),
    ],
)
def test_invalid_prometheus_settings_exit(
    data_folder: Path, monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(SystemExit):
        INIParser(str(data_folder))


def test_an_upstream_ini_uses_the_default_prometheus_settings_and_is_left_alone(data_folder: Path) -> None:
    # An upstream 1.7.x file: an [influxdb] section Varken ignores, and no [prometheus] section at all.
    example = (data_folder / 'varken.example.ini').read_text()
    upstream = (
        example[: example.index('[prometheus]')]
        + ('[influxdb]\nurl = influxdb.example.com\nport = 8086\n\n')
        + example[example.index('[tautulli-1]') :]
    )
    (data_folder / 'varken.ini').write_text(upstream)

    parser = INIParser(str(data_folder))

    assert parser.prometheus_server == PrometheusServer()
    assert (data_folder / 'varken.ini').read_text() == upstream


def test_secrets_can_come_from_files(data_folder: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    secret = tmp_path / 'tautulli_api_key'
    secret.write_text('key-from-a-file\n')
    monkeypatch.setenv('VRKN_TAUTULLI_1_APIKEY_FILE', str(secret))

    parser = INIParser(str(data_folder))

    assert parser.tautulli_servers[0].api_key == 'key-from-a-file'
    assert 'key-from-a-file' in parser.filtered_strings


def test_a_secret_set_twice_exits(data_folder: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    secret = tmp_path / 'key'
    secret.write_text('one')
    monkeypatch.setenv('VRKN_TAUTULLI_1_APIKEY_FILE', str(secret))
    monkeypatch.setenv('VRKN_TAUTULLI_1_APIKEY', 'two')

    with pytest.raises(SystemExit):
        INIParser(str(data_folder))


def test_an_unreadable_secret_file_exits(data_folder: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv('VRKN_TAUTULLI_1_APIKEY_FILE', str(tmp_path / 'missing'))

    with pytest.raises(SystemExit):
        INIParser(str(data_folder))


def test_a_first_start_is_not_an_error(data_folder: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)

    INIParser(str(data_folder))

    created = [r for r in caplog.records if 'creating it from varken.example.ini' in r.getMessage()]
    assert created
    assert created[0].levelname == 'INFO'
    assert not [r for r in caplog.records if r.levelname == 'ERROR']


def test_maxmind_account_id_from_the_environment(data_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert INIParser(str(data_folder)).tautulli_servers[0].maxmind_account_id is None  # empty in the example

    monkeypatch.setenv('VRKN_GLOBAL_MAXMIND_ACCOUNT_ID', '123456')

    assert INIParser(str(data_folder)).tautulli_servers[0].maxmind_account_id == '123456'


def test_a_2_1_ini_has_no_maxmind_account_id_and_none_is_used(data_folder: Path) -> None:
    # varken.ini files written before 2.2.0 have no maxmind_account_id; the example's is empty.
    example = (data_folder / 'varken.example.ini').read_text()
    (data_folder / 'varken.ini').write_text(example.replace('maxmind_account_id =\n', ''))

    parser = INIParser(str(data_folder))

    assert 'maxmind_account_id' not in (data_folder / 'varken.ini').read_text()
    assert parser.tautulli_servers[0].maxmind_account_id is None


def test_a_key_new_in_this_version_is_reported_once_without_an_error(
    data_folder: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Regression: upgrading to 2.2.0 logged "ERROR ... Missing key in tautulli-1" for maxmind_account_id.
    example = (data_folder / 'varken.example.ini').read_text()
    ini = example.replace('maxmind_account_id =\n', '').replace('stream_details = false\n', '')
    (data_folder / 'varken.ini').write_text(ini.replace('get_stats_run_seconds = 3600\n', ''))

    with caplog.at_level(logging.INFO):
        INIParser(str(data_folder))

    reports = [record.getMessage() for record in caplog.records if 'varken.ini has no' in record.getMessage()]
    assert len(reports) == 1  # one line for every section, not one per key
    assert '[prometheus] stream_details; [tautulli-1] get_stats_run_seconds; [global] maxmind_account_id' in reports[0]
    assert 'ERROR' not in [record.levelname for record in caplog.records]


def test_a_complete_varken_ini_reports_nothing_and_needs_no_example(
    data_folder: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (data_folder / 'varken.example.ini').rename(data_folder / 'varken.ini')

    with caplog.at_level(logging.INFO):
        parser = INIParser(str(data_folder))

    assert parser.tautulli_servers[0].get_stats_run_seconds == 3600
    assert 'varken.ini has no' not in caplog.text


def test_the_report_of_missing_keys_names_them_without_their_values(
    data_folder: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # A value can be a secret (the example's are placeholders, but the line is built from names alone).
    example = (data_folder / 'varken.example.ini').read_text()
    (data_folder / 'varken.ini').write_text(example.replace('apikey = xxxxxxxxxxxxxxxx\n', '', 1))

    with caplog.at_level(logging.INFO):
        INIParser(str(data_folder))

    assert 'varken.ini has no [tautulli-1] apikey' in caplog.text
    assert 'xxxxxxxxxxxxxxxx' not in caplog.text


def test_a_secret_taken_from_the_example_is_redacted_like_one_in_the_file(
    data_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The password Varken logs in with when [unifi-1] has none: it must not reach the log either.
    example = data_folder / 'varken.example.ini'
    example.write_text(example.read_text().replace('password = ubnt', 'password = from-the-example'))
    (data_folder / 'varken.ini').write_text(example.read_text().replace('password = from-the-example\n', ''))
    monkeypatch.setenv('VRKN_GLOBAL_UNIFI_SERVER_IDS', '1')

    parser = INIParser(str(data_folder))

    assert parser.unifi_servers[0].password == 'from-the-example'
    assert 'from-the-example' in parser.filtered_strings


def test_a_missing_key_with_its_environment_variable_set_is_not_reported(
    data_folder: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    example = (data_folder / 'varken.example.ini').read_text()
    (data_folder / 'varken.ini').write_text(example.replace('get_stats_run_seconds = 3600\n', ''))
    monkeypatch.setenv('VRKN_TAUTULLI_1_GET_STATS_RUN_SECONDS', '600')

    with caplog.at_level(logging.INFO):
        parser = INIParser(str(data_folder))

    assert parser.tautulli_servers[0].get_stats_run_seconds == 600
    assert 'varken.ini has no' not in caplog.text


def test_a_read_only_varken_ini_with_a_missing_key_starts(data_folder: Path) -> None:
    # It used to stop with "Config file is incomplete and read-only".
    example = (data_folder / 'varken.example.ini').read_text()
    ini = data_folder / 'varken.ini'
    ini.write_text(example.replace('get_stats_run_seconds = 3600\n', ''))
    ini.chmod(0o400)

    parser = INIParser(str(data_folder))

    assert parser.tautulli_servers[0].get_stats_run_seconds == 3600


def test_a_key_left_empty_on_purpose_stays_empty(data_folder: Path) -> None:
    # Regression: filling in missing keys also replaced empty values with the example's.
    example = (data_folder / 'varken.example.ini').read_text()
    ini = example.replace('maxmind_license_key = xxxxxxxxxxxxxxxx\n', 'maxmind_license_key =\n')
    (data_folder / 'varken.ini').write_text(ini.replace('get_stats_run_seconds = 3600\n', ''))

    parser = INIParser(str(data_folder))

    assert parser.tautulli_servers[0].maxmind_license_key == ''
    assert parser.tautulli_servers[0].get_stats_run_seconds == 3600


def test_a_key_missing_from_the_example_too_says_so_and_exits(
    data_folder: Path, caplog: pytest.LogCaptureFixture
) -> None:
    for name in ('varken.ini', 'varken.example.ini'):
        path = data_folder / name
        if not path.exists():
            path.write_text((data_folder / 'varken.example.ini').read_text())
        path.write_text(path.read_text().replace('get_stats_run_seconds = 3600\n', ''))

    with pytest.raises(SystemExit) as stop:
        INIParser(str(data_folder))

    assert stop.value.code == 1
    assert '[tautulli-1] get_stats_run_seconds is missing from varken.ini and from varken.example.ini' in caplog.text


def test_a_section_missing_from_the_example_too_says_so_and_exits(
    data_folder: Path, caplog: pytest.LogCaptureFixture
) -> None:
    example = data_folder / 'varken.example.ini'
    text = example.read_text()
    without = text[: text.index('[prometheus]')] + text[text.index('[tautulli-1]') :]
    example.write_text(without)
    (data_folder / 'varken.ini').write_text(without)

    with pytest.raises(SystemExit) as stop:
        INIParser(str(data_folder))

    assert stop.value.code == 1
    assert 'varken.ini and varken.example.ini have no [prometheus] section' in caplog.text


def test_a_missing_key_without_an_example_to_take_it_from_says_so_and_exits(
    data_folder: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # It used to end in a FileNotFoundError traceback.
    example = data_folder / 'varken.example.ini'
    (data_folder / 'varken.ini').write_text(example.read_text().replace('get_stats_run_seconds = 3600\n', ''))
    example.unlink()

    with pytest.raises(SystemExit) as stop:
        INIParser(str(data_folder))

    assert stop.value.code == 1
    assert 'varken.ini has no [tautulli-1] get_stats_run_seconds, and there is no varken.example.ini' in caplog.text


def test_seerr_is_off_by_default_and_configured_from_the_environment(
    data_folder: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert INIParser(str(data_folder)).seerr_enabled is None

    key = tmp_path / 'seerr_api_key'
    key.write_text('key-from-a-file\n')
    monkeypatch.setenv('VRKN_GLOBAL_SEERR_SERVER_IDS', '1')
    monkeypatch.setenv('VRKN_SEERR_1_URL', 'seerr.example.com:5055')
    monkeypatch.setenv('VRKN_SEERR_1_APIKEY_FILE', str(key))
    monkeypatch.setenv('VRKN_SEERR_1_GET_REQUESTS', 'false')

    parser = INIParser(str(data_folder))

    server = parser.seerr_servers[0]
    assert (server.url, server.api_key) == ('http://seerr.example.com:5055', 'key-from-a-file')
    assert server.get_request_counts is True
    assert server.get_issue_counts is True
    assert server.get_requests is False
    assert server.get_request_counts_run_seconds == 300
    assert 'key-from-a-file' in parser.filtered_strings


def test_new_configs_check_certificates(data_folder: Path) -> None:
    INIParser(str(data_folder))

    text = (data_folder / 'varken.ini').read_text()
    assert 'verify_ssl = false' not in text
    assert 'verify_ssl = true' in text


def test_https_without_certificate_checks_is_a_warning(
    data_folder: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv('VRKN_TAUTULLI_1_SSL', 'true')
    monkeypatch.setenv('VRKN_TAUTULLI_1_VERIFY_SSL', 'false')

    with caplog.at_level(logging.WARNING):
        parser = INIParser(str(data_folder))

    assert parser.tautulli_servers[0].verify_ssl is False
    assert '[tautulli-1] uses HTTPS without checking the certificate' in caplog.text


def test_plain_http_has_nothing_to_verify_and_no_warning(data_folder: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        parser = INIParser(str(data_folder))

    assert parser.tautulli_servers[0].verify_ssl is False  # ssl = false in the example
    assert 'without checking the certificate' not in caplog.text


def test_a_server_id_without_a_section_says_what_to_add_and_exits(
    data_folder: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Regression (found by the property tests): sonarr_server_ids = 3 without [sonarr-3] ended in a NoSectionError
    # traceback after the example had filled in what it could.
    ini = (data_folder / 'varken.example.ini').read_text().replace('sonarr_server_ids = 1,2', 'sonarr_server_ids = 3')
    (data_folder / 'varken.ini').write_text(ini)

    with pytest.raises(SystemExit) as stop:
        INIParser(str(data_folder))

    assert stop.value.code == 1
    assert 'no [sonarr-3] section' in caplog.text


def test_a_url_with_a_trailing_line_break_is_refused(
    data_folder: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Regression (found by the property tests): `$` matched before a final newline, so 'host\n' passed url_check.
    monkeypatch.setenv('VRKN_TAUTULLI_1_URL', 'tautulli.example.com:8181\n')

    with pytest.raises(SystemExit) as stop:
        INIParser(str(data_folder))

    assert stop.value.code == 1
    assert 'is invalid in module [tautulli-1]' in caplog.text
