import pytest

from varken.iniparser import INIParser


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
