# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
import logging
import os
import shutil
from pathlib import Path

import pytest
from hypothesis import settings

REPO = Path(__file__).resolve().parent.parent

# Hypothesis: the parser properties write files, so no deadline; `pytest --hypothesis-profile=thorough` runs 5,000
# examples per property. No example database, so a run never depends on what an earlier run left in the checkout.
settings.register_profile('default', deadline=None, database=None)
settings.register_profile('thorough', deadline=None, database=None, max_examples=5000)
settings.load_profile('default')


@pytest.fixture(autouse=True)
def clean_environment():
    """No VRKN_* variables from the machine running the tests, and none left behind by a test (the parser sets
    VRKN_* itself from *_FILE variables); no handlers or filters left on the root logger."""
    saved = dict(os.environ)
    for name in list(os.environ):
        if name.startswith('VRKN_'):
            del os.environ[name]
    root = logging.getLogger()
    handlers = list(root.handlers)
    yield
    os.environ.clear()
    os.environ.update(saved)
    for handler in root.handlers:
        handler.filters.clear()
    for handler in root.handlers[:]:
        if handler not in handlers:
            root.removeHandler(handler)
            handler.close()


@pytest.fixture
def data_folder(tmp_path):
    """A data folder holding only the example config, as on a first start."""
    shutil.copy(REPO / 'data' / 'varken.example.ini', tmp_path / 'varken.example.ini')
    return tmp_path
