# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
"""The keys that sign release tags (.github/allowed_signers) and what docs/verifying-releases.md says about them."""

import base64
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIGNERS = [line.split() for line in (ROOT / '.github' / 'allowed_signers').read_text().splitlines() if line.strip()]


def fingerprint(key: str) -> str:
    # What ssh-keygen and "git verify-tag" print: the SHA-256 of the key blob, base64 without padding.
    return 'SHA256:' + base64.b64encode(hashlib.sha256(base64.b64decode(key)).digest()).decode().rstrip('=')


def test_every_signer_is_the_maintainer_and_only_for_git() -> None:
    # A line without namespaces="git" would let the key vouch for anything signed with ssh-keygen, not just git
    # objects; a comment field could carry a hostname into the repository.
    assert SIGNERS
    for fields in SIGNERS:
        assert len(fields) == 4, fields
        principal, namespaces, key_type, _ = fields
        assert principal == SIGNERS[0][0]
        assert principal.endswith('@users.noreply.github.com')
        assert namespaces == 'namespaces="git"'
        assert key_type in {'ssh-rsa', 'ssh-ed25519'}


def test_the_docs_list_the_fingerprint_of_every_signing_key() -> None:
    documented = set(re.findall(r'SHA256:[A-Za-z0-9+/]{43}', (ROOT / 'docs' / 'verifying-releases.md').read_text()))
    assert documented == {fingerprint(fields[3]) for fields in SIGNERS}
