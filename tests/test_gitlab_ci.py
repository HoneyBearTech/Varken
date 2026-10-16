"""The GitLab copy's pipeline (.gitlab-ci.yml): GitLab rejects the whole file when a script line isn't a string."""
from pathlib import Path

import yaml

CONFIG = yaml.safe_load((Path(__file__).resolve().parent.parent / '.gitlab-ci.yml').read_text())
KEYWORDS = {'workflow', 'default', 'stages', 'variables', 'include'}


def test_every_script_line_is_a_string():
    # Regression: a plain list item holding "ref: " parsed as a mapping, and GitLab refused to run any pipeline
    # ("jobs:mirror:script config should be a string or a nested array of strings").
    for name, job in CONFIG.items():
        if name in KEYWORDS or not isinstance(job, dict):
            continue
        for key in ('before_script', 'script', 'after_script'):
            for line in job.get(key, []):
                assert isinstance(line, str), f'{name}.{key}: {line!r}'


def test_the_mirror_reads_githubs_default_branch():
    script = '\n'.join(CONFIG['mirror']['script'])
    assert 'ls-remote --symref "$MIRROR_SOURCE" HEAD' in script
    assert 'refs/heads/master' not in script
