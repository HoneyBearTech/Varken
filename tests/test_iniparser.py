import logging

import pytest

from varken.iniparser import INIParser
from varken.structures import PrometheusServer


def test_first_start_creates_varken_ini_from_the_example(data_folder):
    parser = INIParser(str(data_folder))

    assert (data_folder / 'varken.ini').exists()
    assert parser.prometheus_server == PrometheusServer()
    assert parser.sonarr_enabled == [1, 2]
    assert [s.url for s in parser.sonarr_servers] == ['http://sonarr1.domain.tld:8989', 'http://sonarr2.domain.tld:8989']
    assert parser.lidarr_enabled is None
    tautulli = parser.tautulli_servers[0]
    assert tautulli.fallback_ip == '1.1.1.1'
    assert tautulli.get_activity is True
    assert tautulli.get_stats_run_seconds == 3600


def test_environment_variables_override_the_file(data_folder, monkeypatch):
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


def test_verify_ssl_is_off_without_ssl(data_folder, monkeypatch):
    monkeypatch.setenv('VRKN_TAUTULLI_1_VERIFY_SSL', 'true')

    parser = INIParser(str(data_folder))

    assert parser.tautulli_servers[0].verify_ssl is False


def test_secrets_from_environment_variables_are_redacted_from_logs(data_folder, monkeypatch):
    # Regression: only varken.ini values used to be redacted, so keys set through VRKN_* leaked into debug logs.
    monkeypatch.setenv('VRKN_TAUTULLI_1_APIKEY', 'tautulli-secret-key')
    monkeypatch.setenv('VRKN_UNIFI_1_PASSWORD', 'unifi-secret-password')
    monkeypatch.setenv('VRKN_GLOBAL_MAXMIND_LICENSE_KEY', 'maxmind-secret-key')
    monkeypatch.setenv('VRKN_TAUTULLI_1_GET_STATS_RUN_SECONDS', '600')

    parser = INIParser(str(data_folder))

    assert {'tautulli-secret-key', 'unifi-secret-password', 'maxmind-secret-key'} <= set(parser.filtered_strings)
    assert '600' not in parser.filtered_strings


def test_invalid_url_exits(data_folder, monkeypatch):
    monkeypatch.setenv('VRKN_SONARR_1_URL', 'not a host name')

    with pytest.raises(SystemExit):
        INIParser(str(data_folder))


def test_private_fallback_ip_exits(data_folder, monkeypatch):
    monkeypatch.setenv('VRKN_TAUTULLI_1_FALLBACK_IP', '192.168.1.10')

    with pytest.raises(SystemExit):
        INIParser(str(data_folder))


def test_missing_key_is_restored_from_the_example(data_folder):
    example = (data_folder / 'varken.example.ini').read_text()
    (data_folder / 'varken.ini').write_text(example.replace('get_stats_run_seconds = 3600\n', ''))

    parser = INIParser(str(data_folder))

    assert 'get_stats_run_seconds = 3600' in (data_folder / 'varken.ini').read_text()
    assert parser.tautulli_servers[0].get_stats_run_seconds == 3600


def test_prometheus_settings_from_the_environment(data_folder, monkeypatch):
    monkeypatch.setenv('VRKN_PROMETHEUS_BIND', '127.0.0.1')
    monkeypatch.setenv('VRKN_PROMETHEUS_PORT', '9999')
    monkeypatch.setenv('VRKN_PROMETHEUS_STREAM_DETAILS', 'true')

    parser = INIParser(str(data_folder))

    assert parser.prometheus_server == PrometheusServer(bind='127.0.0.1', port=9999, stream_details=True)


@pytest.mark.parametrize(('name', 'value'), [
    ('VRKN_PROMETHEUS_BIND', 'localhost'),
    ('VRKN_PROMETHEUS_PORT', '70000'),
    ('VRKN_PROMETHEUS_PORT', 'many'),
])
def test_invalid_prometheus_settings_exit(data_folder, monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    with pytest.raises(SystemExit):
        INIParser(str(data_folder))


def test_an_upstream_ini_gets_the_prometheus_settings_and_keeps_its_influxdb_section(data_folder):
    example = (data_folder / 'varken.example.ini').read_text()
    upstream = example[:example.index('[prometheus]')] + (
        '[influxdb]\nurl = influxdb.example.com\nport = 8086\n\n') + example[example.index('[tautulli-1]'):]
    (data_folder / 'varken.ini').write_text(upstream)

    parser = INIParser(str(data_folder))

    written = (data_folder / 'varken.ini').read_text()
    assert '[prometheus]' in written
    assert '[influxdb]' in written
    assert parser.prometheus_server == PrometheusServer()


def test_secrets_can_come_from_files(data_folder, monkeypatch, tmp_path):
    secret = tmp_path / 'tautulli_api_key'
    secret.write_text('key-from-a-file\n')
    monkeypatch.setenv('VRKN_TAUTULLI_1_APIKEY_FILE', str(secret))

    parser = INIParser(str(data_folder))

    assert parser.tautulli_servers[0].api_key == 'key-from-a-file'
    assert 'key-from-a-file' in parser.filtered_strings


def test_a_secret_set_twice_exits(data_folder, monkeypatch, tmp_path):
    secret = tmp_path / 'key'
    secret.write_text('one')
    monkeypatch.setenv('VRKN_TAUTULLI_1_APIKEY_FILE', str(secret))
    monkeypatch.setenv('VRKN_TAUTULLI_1_APIKEY', 'two')

    with pytest.raises(SystemExit):
        INIParser(str(data_folder))


def test_an_unreadable_secret_file_exits(data_folder, monkeypatch, tmp_path):
    monkeypatch.setenv('VRKN_TAUTULLI_1_APIKEY_FILE', str(tmp_path / 'missing'))

    with pytest.raises(SystemExit):
        INIParser(str(data_folder))


def test_a_first_start_is_not_an_error(data_folder, caplog):
    caplog.set_level(logging.INFO)

    INIParser(str(data_folder))

    created = [r for r in caplog.records if 'creating it from varken.example.ini' in r.getMessage()]
    assert created and created[0].levelname == 'INFO'
    assert not [r for r in caplog.records if r.levelname == 'ERROR']


def test_maxmind_account_id_from_the_environment(data_folder, monkeypatch):
    assert INIParser(str(data_folder)).tautulli_servers[0].maxmind_account_id is None  # empty in the example

    monkeypatch.setenv('VRKN_GLOBAL_MAXMIND_ACCOUNT_ID', '123456')

    assert INIParser(str(data_folder)).tautulli_servers[0].maxmind_account_id == '123456'


def test_a_2_1_ini_gets_the_maxmind_account_id(data_folder):
    # varken.ini files written before 2.2.0 have no maxmind_account_id; it's added, empty, on the next start.
    example = (data_folder / 'varken.example.ini').read_text()
    (data_folder / 'varken.ini').write_text(example.replace('maxmind_account_id =\n', ''))

    parser = INIParser(str(data_folder))

    assert 'maxmind_account_id' in (data_folder / 'varken.ini').read_text()
    assert parser.tautulli_servers[0].maxmind_account_id is None


def test_a_key_new_in_this_version_is_added_without_an_error(data_folder, caplog):
    # Regression: upgrading to 2.2.0 logged "ERROR ... Missing key in tautulli-1" for maxmind_account_id.
    example = (data_folder / 'varken.example.ini').read_text()
    (data_folder / 'varken.ini').write_text(example.replace('maxmind_account_id =\n', ''))

    with caplog.at_level(logging.INFO):
        INIParser(str(data_folder))

    assert 'varken.ini has no maxmind_account_id in [global]' in caplog.text
    assert 'ERROR' not in [record.levelname for record in caplog.records]


def test_a_key_left_empty_on_purpose_stays_empty(data_folder):
    # Regression: filling in missing keys also replaced empty values with the example's.
    example = (data_folder / 'varken.example.ini').read_text()
    ini = example.replace('maxmind_license_key = xxxxxxxxxxxxxxxx\n', 'maxmind_license_key =\n')
    (data_folder / 'varken.ini').write_text(ini.replace('get_stats_run_seconds = 3600\n', ''))

    INIParser(str(data_folder))

    text = (data_folder / 'varken.ini').read_text()
    assert 'get_stats_run_seconds = 3600' in text
    assert 'maxmind_license_key = \n' in text or 'maxmind_license_key =\n' in text


def test_a_key_missing_from_the_example_too_exits_instead_of_looping(data_folder):
    for name in ('varken.ini', 'varken.example.ini'):
        path = data_folder / name
        if not path.exists():
            path.write_text((data_folder / 'varken.example.ini').read_text())
        path.write_text(path.read_text().replace('get_stats_run_seconds = 3600\n', ''))

    with pytest.raises(SystemExit):
        INIParser(str(data_folder))


def test_seerr_is_off_by_default_and_configured_from_the_environment(data_folder, monkeypatch, tmp_path):
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
    assert server.get_request_counts is True and server.get_issue_counts is True and server.get_requests is False
    assert server.get_request_counts_run_seconds == 300
    assert 'key-from-a-file' in parser.filtered_strings


def test_new_configs_check_certificates(data_folder):
    INIParser(str(data_folder))

    text = (data_folder / 'varken.ini').read_text()
    assert 'verify_ssl = false' not in text and 'verify_ssl = true' in text


def test_https_without_certificate_checks_is_a_warning(data_folder, monkeypatch, caplog):
    monkeypatch.setenv('VRKN_TAUTULLI_1_SSL', 'true')
    monkeypatch.setenv('VRKN_TAUTULLI_1_VERIFY_SSL', 'false')

    with caplog.at_level(logging.WARNING):
        parser = INIParser(str(data_folder))

    assert parser.tautulli_servers[0].verify_ssl is False
    assert '[tautulli-1] uses HTTPS without checking the certificate' in caplog.text


def test_plain_http_has_nothing_to_verify_and_no_warning(data_folder, caplog):
    with caplog.at_level(logging.WARNING):
        parser = INIParser(str(data_folder))

    assert parser.tautulli_servers[0].verify_ssl is False  # ssl = false in the example
    assert 'without checking the certificate' not in caplog.text
