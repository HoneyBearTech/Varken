# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
"""Coverage-guided fuzzing (Atheris) of the Hypothesis properties in tests/test_properties.py.

libFuzzer feeds each property's `.hypothesis.fuzz_one_input`, so a fuzzer finding is a failing property.

Atheris only has Linux x86_64 wheels, so this runs in CI (.github/workflows/fuzz.yml) or an amd64 container:

    pip install --require-hashes --no-deps -r requirements.txt -r requirements-dev.txt -r requirements-fuzz.txt
    python fuzz/fuzz_properties.py <target> [libFuzzer flags]      # e.g. -max_total_time=60
    python fuzz/fuzz_properties.py <target> <crash-file>           # replay a finding
"""

import logging
import sys
from pathlib import Path

import atheris
from hypothesis import settings

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]

# Registered before the properties are imported so their settings inherit it: the fuzzer owns the inputs and the
# time budget, so there's no example database and no deadline.
settings.register_profile('fuzz', deadline=None, database=None)
settings.load_profile('fuzz')

# The parser logs every refusal; nobody reads that here, and without a handler Python prints it to stderr.
logging.getLogger().addHandler(logging.NullHandler())
logging.disable(logging.CRITICAL)

TARGETS = {
    'config': 'test_any_config_and_environment_starts_cleanly_or_refuses_with_exit_1',
    'url': 'test_url_check_returns_the_url_untouched_or_refuses_to_start',
    'url_line_breaks': 'test_a_url_that_passes_has_no_line_break_in_it',
    'server_ids': 'test_server_ids_are_integers_or_false',
    'boolcheck': 'test_boolcheck_is_a_bool_and_only_true_or_yes_are_true',
    'log_filter': 'test_no_secret_survives_the_log_filter',
}


def main() -> None:
    """Fuzz the target named on the command line; libFuzzer takes the remaining arguments."""
    if sys.argv[1:2] == [] or sys.argv[1] not in TARGETS:
        sys.exit(f'usage: {sys.argv[0]} <target> [libFuzzer flags]\ntargets: {", ".join(TARGETS)}')
    target = sys.argv.pop(1)

    # configparser is guidance too: with only varken instrumented, the fuzzer can't tell one INI file from another.
    with atheris.instrument_imports(include=['varken', 'configparser']):
        import test_properties  # noqa: PLC0415 - imported inside the block so it gets instrumented

    prop = getattr(test_properties, TARGETS[target])
    atheris.Setup(sys.argv, prop.hypothesis.fuzz_one_input)
    atheris.Fuzz()


if __name__ == '__main__':
    main()
