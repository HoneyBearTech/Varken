import logging
import os
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """No VRKN_* variables from the machine running the tests, and no filters left on the root logger's handlers."""
    for name in list(os.environ):
        if name.startswith('VRKN_'):
            monkeypatch.delenv(name)
    root = logging.getLogger()
    handlers = list(root.handlers)
    yield
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
