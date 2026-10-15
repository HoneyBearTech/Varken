import logging
import os
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


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
