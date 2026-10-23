# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
"""Every source file names its copyright holders and its license (OpenSSF Best Practices Gold: copyright_per_file,
license_per_file), in SPDX form."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_every_python_file_has_spdx_copyright_and_license_lines():
    files = subprocess.run(['git', 'ls-files', '*.py'], cwd=ROOT, capture_output=True, text=True,  # noqa: S603, S607
                           check=True).stdout.split()
    assert files
    for name in files:
        head = (ROOT / name).read_text(encoding='utf-8').splitlines()[:4]
        assert any(line.startswith('# SPDX-FileCopyrightText: ') for line in head), name
        assert '# SPDX-License-Identifier: MIT' in head, name
