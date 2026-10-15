import pytest

from varken.iniparser import INIParser
from varken.structures import PrometheusServer


def test_first_start_creates_varken_ini_from_the_example(data_folder):
    parser = INIParser(str(data_folder))

    assert (data_folder / 'varken.ini').exists()
    assert parser.influx_server.url == 'influxdb.domain.tld'
    assert parser.influx_server.port == 8086
    assert parser.sonarr_enabled == [1, 2]
    assert [s.url for s in parser.sonarr_servers] == ['http://sonarr1.domain.tld:8989', 'http://sonarr2.domain.tld:8989']
    assert parser.lidarr_enabled is None
    tautulli = parser.tautulli_servers[0]
    assert tautulli.fallback_ip == '1.1.1.1'
    assert tautulli.get_activity is True
    assert tautulli.get_stats_run_seconds == 3600


def test_environment_variables_override_the_file(data_folder, monkeypatch):
    monkeypatch.setenv('VRKN_GLOBAL_SONARR_SERVER_IDS', 'false')
    monkeypatch.setenv('VRKN_INFLUXDB_URL', 'influxdb')
    monkeypatch.setenv('VRKN_TAUTULLI_1_URL', 'tautulli.example.com:8181')
    monkeypatch.setenv('VRKN_TAUTULLI_1_APIKEY', 'key-from-the-environment')
    monkeypatch.setenv('VRKN_TAUTULLI_1_SSL', 'true')
    monkeypatch.setenv('VRKN_TAUTULLI_1_VERIFY_SSL', 'true')

    parser = INIParser(str(data_folder))

    assert parser.sonarr_enabled is None
    assert parser.sonarr_servers == []
    assert parser.influx_server.url == 'influxdb'
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
    monkeypatch.setenv('VRKN_INFLUXDB_PASSWORD', 'influx-secret-password')
    monkeypatch.setenv('VRKN_GLOBAL_MAXMIND_LICENSE_KEY', 'maxmind-secret-key')
    monkeypatch.setenv('VRKN_TAUTULLI_1_GET_STATS_RUN_SECONDS', '600')

    parser = INIParser(str(data_folder))

    assert {'tautulli-secret-key', 'influx-secret-password', 'maxmind-secret-key'} <= set(parser.filtered_strings)
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


def test_outputs_default_to_influxdb_only(data_folder):
    parser = INIParser(str(data_folder))

    assert parser.influx_server.enabled is True
    assert parser.prometheus_server.enabled is False
    assert parser.prometheus_server.port == 9180
    assert parser.prometheus_server.stream_details is False


def test_prometheus_settings_from_the_environment(data_folder, monkeypatch):
    monkeypatch.setenv('VRKN_INFLUXDB_ENABLED', 'false')
    monkeypatch.setenv('VRKN_PROMETHEUS_ENABLED', 'true')
    monkeypatch.setenv('VRKN_PROMETHEUS_BIND', '127.0.0.1')
    monkeypatch.setenv('VRKN_PROMETHEUS_PORT', '9999')
    monkeypatch.setenv('VRKN_PROMETHEUS_STREAM_DETAILS', 'true')

    parser = INIParser(str(data_folder))

    assert parser.influx_server.enabled is False
    assert parser.prometheus_server == PrometheusServer(enabled=True, bind='127.0.0.1', port=9999, stream_details=True)


@pytest.mark.parametrize(('name', 'value'), [
    ('VRKN_PROMETHEUS_BIND', 'localhost'),
    ('VRKN_PROMETHEUS_PORT', '70000'),
    ('VRKN_PROMETHEUS_PORT', 'many'),
])
def test_invalid_prometheus_settings_exit(data_folder, monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    with pytest.raises(SystemExit):
        INIParser(str(data_folder))


def test_an_ini_from_before_the_prometheus_output_gets_the_new_settings(data_folder):
    example = (data_folder / 'varken.example.ini').read_text()
    old = example.replace('enabled = true\n', '', 1)
    old = old[:old.index('[prometheus]')] + old[old.index('[tautulli-1]'):]
    (data_folder / 'varken.ini').write_text(old)

    parser = INIParser(str(data_folder))

    written = (data_folder / 'varken.ini').read_text()
    assert '[prometheus]' in written
    assert parser.influx_server.enabled is True
    assert parser.prometheus_server.enabled is False


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
