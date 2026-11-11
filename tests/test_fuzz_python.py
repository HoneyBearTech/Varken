# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
"""The fuzzer's Python (.github/workflows/fuzz.yml) can be older than the image's: the code has to run on it too."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LAZY_IMPORT = re.compile(r'^[ \t]*lazy[ \t]+(?:import|from)[ \t]', re.MULTILINE)


def test_no_lazy_import_while_the_fuzzer_runs_on_a_python_before_3_15() -> None:
    # ruff's fix for an import that only annotations use (TC001, TC002) is a `lazy` import, new in Python 3.15. The
    # Fuzz workflow runs on 3.14 until Atheris has wheels for 3.15, and there `lazy` is a syntax error: such an
    # import goes in an `if TYPE_CHECKING:` block instead.
    workflow = (ROOT / '.github' / 'workflows' / 'fuzz.yml').read_text()
    minor = int(re.search(r'python-version: "3\.(\d+)"', workflow)[1])
    if minor >= 15:
        pytest.skip('the fuzzer runs on Python 3.15 or later, where a lazy import is fine')
    files = [
        ROOT / 'Varken.py',
        *(path for folder in ('varken', 'tests', 'fuzz', 'dashboard') for path in (ROOT / folder).rglob('*.py')),
    ]
    assert len(files) > 30
    assert [str(path.relative_to(ROOT)) for path in files if LAZY_IMPORT.search(path.read_text())] == []


def test_the_check_finds_a_lazy_import() -> None:
    assert LAZY_IMPORT.search('import sys\nlazy from varken.metrics import Metrics\n')
    assert LAZY_IMPORT.search('if True:\n    lazy import json\n')
    assert not LAZY_IMPORT.search('lazy = 1\n# lazy import json\nlazy_import = "lazy from x"\n')
