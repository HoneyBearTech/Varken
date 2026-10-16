"""Coverage-guided fuzzing (Atheris) of the Hypothesis properties in tests/test_properties.py.

libFuzzer feeds each property's `.hypothesis.fuzz_one_input`, so a fuzzer finding is a failing property.

Atheris only has Linux x86_64 wheels, so this runs in CI (.github/workflows/fuzz.yml) or an amd64 container:

    pip install --require-hashes --no-deps -r requirements.txt -r requirements-dev.txt -r requirements-fuzz.txt
    python fuzz/fuzz_properties.py <target> [libFuzzer flags]      # e.g. -max_total_time=60
    python fuzz/fuzz_properties.py <target> <crash-file>           # replay a finding
"""
import sys
from pathlib import Path

import atheris
from hypothesis import settings

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT)]

# Registered before the properties are imported so their settings inherit it: the fuzzer owns the inputs and the
# time budget, so there's no example database and no deadline.
settings.register_profile('fuzz', deadline=None, database=None)
settings.load_profile('fuzz')

TARGETS = {
    'url_check': 'test_url_check_accepts_or_exits_quickly_whatever_the_text',
    'settings': 'test_any_setting_parses_or_stops_varken_cleanly',
    'log_masking': 'test_no_configured_secret_survives_into_a_log_line',
    'replies': 'test_any_reply_is_handled_and_the_scrape_stays_valid',
    'labels': 'test_any_label_text_makes_a_scrape_that_parses_back',
}


def main():
    """Fuzz the target named on the command line; libFuzzer takes the remaining arguments."""
    if sys.argv[1:2] == [] or sys.argv[1] not in TARGETS:
        sys.exit(f"usage: {sys.argv[0]} <target> [libFuzzer flags]\ntargets: {', '.join(TARGETS)}")
    target = sys.argv.pop(1)

    with atheris.instrument_imports(include=['varken']):
        from tests import test_properties

    prop = getattr(test_properties, TARGETS[target])
    atheris.Setup(sys.argv, prop.hypothesis.fuzz_one_input)
    atheris.Fuzz()


if __name__ == '__main__':
    main()
