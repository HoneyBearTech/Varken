import logging

from varken.varkenlogger import BlacklistFilter, VarkenLogger


def record(msg, *args):
    return logging.LogRecord('test', logging.INFO, __file__, 1, msg, args, None)


def test_redacts_secrets_in_the_message_and_string_arguments():
    log_filter = BlacklistFilter({'supersecretkey'})
    entry = record('key supersecretkey in %s', 'GET /api?apikey=supersecretkey')

    assert log_filter.filter(entry) is True
    assert 'supersecretkey' not in entry.getMessage()
    assert '********etkey' in entry.getMessage()


def test_redacts_secrets_in_exception_arguments():
    # Regression: only str arguments were redacted, so an exception carrying a URL kept the key.
    log_filter = BlacklistFilter({'supersecretkey'})
    entry = record('Request failed: %s', ConnectionError('https://example.com/api?apikey=supersecretkey'))

    log_filter.filter(entry)

    assert 'supersecretkey' not in entry.getMessage()


def test_leaves_numbers_alone():
    log_filter = BlacklistFilter({'8'})
    entry = record('%d streams', 8)

    log_filter.filter(entry)

    assert entry.args == (8,)
    assert entry.getMessage() == '8 streams'


def test_logs_to_a_file_in_the_data_folder(tmp_path):
    varken_logger = VarkenLogger(debug=False, data_folder=str(tmp_path))
    varken_logger.logger.info('hello from the test')

    for handler in varken_logger.logger.handlers:
        handler.flush()
    assert 'hello from the test' in (tmp_path / 'logs' / 'varken.log').read_text()


def test_logs_to_stdout_only_without_a_file(tmp_path):
    VarkenLogger(debug=False, data_folder=str(tmp_path), log_to_file=False)

    assert not (tmp_path / 'logs').exists()
