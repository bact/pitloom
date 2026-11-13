# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A credential goes to its own origin only
(:mod:`pitloom.extract.remote._http_credential`): the same scheme, host and
port, as the Git route carries a URL's user information. The token is the
one ``huggingface_hub`` sends, and a fetch error is said again as a
``WARNING:`` only when it is catalogued.

See also: tests/extract/remote/test_hub_files.py (the token on the wire) and
tests/extract/remote/test_git_redirect.py (the Git route's rule).
"""

from __future__ import annotations

import logging

import pytest
from huggingface_hub import constants

from pitloom.core.internal_error import InternalError
from pitloom.extract.remote._http_credential import Credential, origin_of
from pitloom.extract.remote._http_errors import remote_error, warn_instead
from pitloom.extract.remote._hub_files import hub_offline, hub_token
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.messages.pypi import (
    DIGEST_MISMATCH,
    DIGEST_MISMATCH_LINE,
)

_HUB = Credential("Bearer t", ("https", "huggingface.co", 443))


@pytest.mark.parametrize(
    ("url", "sent"),
    [
        ("https://huggingface.co/o/m/resolve/main/config.json", True),
        ("https://HuggingFace.co:443/api/resolve-cache/x", True),
        ("http://huggingface.co/o/m", False),
        ("https://huggingface.co:8443/o/m", False),
        ("https://us.aws.cdn.hf.co/xet-bridge-us/x", False),
        ("https://huggingface.co.evil.example/o/m", False),
        ("https://hf.co/o/m", False),
        ("https://huggingface.co:x/o/m", False),
        ("https:///o/m", False),
    ],
)
def test_the_header_goes_to_its_origin_only(url: str, sent: bool) -> None:
    assert (_HUB.header_for(url) == "Bearer t") is sent
    assert _HUB.header_for(url) in (None, "Bearer t")


def test_origin_of_writes_the_default_port() -> None:
    assert origin_of("https://h.example/x") == ("https", "h.example", 443)
    assert origin_of("http://127.0.0.1:8080/x") == ("http", "127.0.0.1", 8080)
    assert origin_of("http://h.example") == ("http", "h.example", 80)


def test_the_token_is_not_in_the_text() -> None:
    assert "Bearer t" not in repr(_HUB) and "Bearer t" not in str(_HUB)


def test_a_fetch_error_is_said_again_only_when_catalogued() -> None:
    """``warn_instead`` says a catalogued fetch error as its family's
    ``WARNING:``; an error it did not make, or a family with no such line,
    is a programming error."""
    log = logging.getLogger("pitloom.test")
    with pytest.raises(InternalError):
        warn_instead(log, RemoteSourceError("x.y", "text"), "o")
    foreign = RemoteSourceError("x.y", "text")
    foreign.said = ("not a message", {})
    with pytest.raises(InternalError):
        warn_instead(log, foreign, "o")
    lineless = remote_error(
        "pypi.digest-mismatch",
        DIGEST_MISMATCH,
        DIGEST_MISMATCH_LINE,
        file="f",
        measured="0" * 64,
        declared="1" * 64,
        source="s",
    )
    with pytest.raises(InternalError, match="pypi.digest-mismatch"):
        warn_instead(log, lineless, "o")


@pytest.mark.parametrize("disabled", [True, False])
def test_the_hub_token_is_huggingface_hubs_own(
    monkeypatch: pytest.MonkeyPatch, disabled: bool
) -> None:
    monkeypatch.setattr(constants, "HF_HUB_DISABLE_IMPLICIT_TOKEN", disabled)
    monkeypatch.setenv("HF_TOKEN", "hf_x")
    assert hub_token() == (None if disabled else "hf_x")


@pytest.mark.parametrize("offline", [True, False])
def test_hub_offline_is_huggingface_hubs_own(
    monkeypatch: pytest.MonkeyPatch, offline: bool
) -> None:
    monkeypatch.setattr(constants, "HF_HUB_OFFLINE", offline)
    assert hub_offline() is offline
