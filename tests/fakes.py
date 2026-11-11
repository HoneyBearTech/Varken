# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
"""A stand-in for connection_handler, for the modules whose tests answer requests by their path."""

from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from varken import helpers

if TYPE_CHECKING:
    from types import ModuleType

    import pytest
    from requests import PreparedRequest, Session


def answer_by_path(
    monkeypatch: pytest.MonkeyPatch, module: ModuleType, routes: dict[str, object]
) -> list[PreparedRequest]:
    """Make the module's service answer each request with its path's reply; return the requests made.

    A path without a reply, or with False for one, is a failed request, as connection_handler reports it.
    """
    made = []

    def fake(session: Session, request: PreparedRequest, *, verify: bool, as_is_reply: bool = False) -> object:
        made.append(request)
        reply = routes.get(urlsplit(request.url).path, False)
        if reply is False:
            helpers.request_state.failed = True
        return reply

    monkeypatch.setattr(module, 'connection_handler', fake)
    return made
