# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The Hub a Hugging Face file is asked of
(:func:`pitloom.extract.remote._hub_files.hub_base`): ``huggingface_hub``'s
own ``constants.ENDPOINT`` (``HF_ENDPOINT``), https only, its host allowed
and the token sent to its origin only; one ``INFO:`` naming a Hub other than
``https://huggingface.co``, one ``WARNING:`` for one refused, and then
nothing asked of the Hub at all, not even through ``huggingface_hub``.

The Hub and its CDN are local servers (``loopback``, tests/_fake_hub.py).

See also: tests/extract/remote/test_hub_files.py (the downloads).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import huggingface_hub
import pytest
from huggingface_hub import constants, hf_api
from huggingface_hub.errors import HfHubHTTPError

from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.core.internal_error import InternalError
from pitloom.extract.remote import _http_fetch, _hub_files, read_huggingface
from pitloom.extract.remote._hub_files import (
    DEFAULT_HUB_BASE,
    HUB_JSON_CAP,
    FileKind,
    HubFiles,
    endpoint_refusal,
    file_policy,
    file_url,
    hub_base,
    hub_credential,
    hub_files,
)
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import ENDPOINT_MOVED, ENDPOINT_REFUSED
from tests._fake_hub import (
    TOKEN,
    FakeHub,
    hub_and_cdn,
    point_hub_at,
    serve_in_git,
    serve_in_xet,
)
from tests._fake_pypi_server import serving

pytestmark = pytest.mark.loopback

_REPO = "o/m"
_SHA = "0123456789abcdef0123456789abcdef01234567"
_BEARER = f"Bearer {TOKEN}"
_KIND = FileKind(HUB_JSON_CAP, "x not read")
#: The module's own endpoint lookup, before a test replaces it.
_real_hub_endpoint = _hub_files.hub_endpoint


@pytest.fixture(name="fake")
def _fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeHub]:
    """A fake Hub that ``huggingface_hub``'s ``ENDPOINT`` names."""
    with hub_and_cdn() as fake:
        point_hub_at(monkeypatch, fake)
        monkeypatch.setattr(_hub_files, "hub_endpoint", _real_hub_endpoint)
        monkeypatch.setattr(constants, "ENDPOINT", fake.hub.base)
        yield fake


def _codes(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [getattr(r, CODE_ATTR) for r in caplog.records if hasattr(r, CODE_ATTR)]


def _read_two() -> tuple[bytes | None, bytes | None]:
    """``config.json`` and ``README.md`` of one read."""
    got: list[bytes | None] = []
    with hub_files(RemoteFetchPolicy()) as hub:
        for name in ("config.json", "README.md"):
            path = hub.read(_REPO, name, revision=_SHA, kind=_KIND)
            got.append(None if path is None else path.read_bytes())
    return got[0], got[1]


def test_files_come_from_the_endpoint_with_the_token_said_once(
    fake: FakeHub, caplog: pytest.LogCaptureFixture
) -> None:
    """Both files are asked of the endpoint with the token; a file it
    sends to the CDN is asked without it; one ``INFO:`` for the read."""
    serve_in_git(fake, _REPO, "config.json", b"{}", revision=_SHA)
    signed = serve_in_xet(fake, _REPO, "README.md", b"# c", revision=_SHA)
    with caplog.at_level(logging.INFO):
        assert _read_two() == (b"{}", b"# c")
    assert fake.hub.seen[0] == f"/{_REPO}/resolve/{_SHA}/config.json"
    assert [h.get("authorization") for h in fake.hub.headers] == [_BEARER] * 3
    assert fake.cdn.seen == [signed + "?X-Xet-Signed=1"]
    assert "authorization" not in fake.cdn.headers[0]
    assert _codes(caplog).count(ENDPOINT_MOVED.code) == 1
    assert caplog.records[0].getMessage() == (
        f"URL={fake.hub.base}: the Hub HF_ENDPOINT names; Hugging Face files "
        "are fetched from it"
    )


def test_a_non_https_endpoint_is_refused_once_and_fetches_nothing(
    fake: FakeHub,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """With only https allowed (as in production), the http endpoint is
    refused: nothing is asked of it, one ``WARNING:`` for the read."""
    monkeypatch.setattr(_http_fetch, "ALLOWED_SCHEMES", frozenset({"https"}))
    serve_in_git(fake, _REPO, "config.json", b"{}", revision=_SHA)
    with caplog.at_level(logging.INFO):
        assert _read_two() == (None, None)
    assert not fake.hub.seen
    assert _codes(caplog) == [ENDPOINT_REFUSED.code]
    record = caplog.records[0]
    assert record.levelno == logging.WARNING
    assert record.getMessage() == (
        f"URL={fake.hub.base}: HF_ENDPOINT not used (only https is "
        "followed); nothing asked of the Hub"
    )


def test_a_refused_endpoint_is_asked_nothing_not_even_by_huggingface_hub(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """With an http ``HF_ENDPOINT`` and a token, ``model_info()``, the file
    listing, ``dataset_info()`` and every file would carry the token over
    plain http: no request at all reaches the endpoint. The model keeps its
    id and URL; the refusal is the one ``WARNING:``."""
    monkeypatch.setenv("HF_TOKEN", TOKEN)
    with serving() as endpoint:
        monkeypatch.setattr(constants, "ENDPOINT", endpoint.base)
        monkeypatch.setattr(hf_api.api, "endpoint", endpoint.base)
        # The set-up routes huggingface_hub's own requests to the endpoint,
        # token and all.
        with pytest.raises(HfHubHTTPError):
            huggingface_hub.model_info("o/probe")
        assert [h.get("authorization") for h in endpoint.headers] == [_BEARER]
        endpoint.seen.clear()
        with patch(
            "pitloom.extract.remote.huggingface._extract_datasets",
            return_value=[DatasetReference("trainedOn", DatasetMetadata(name="o/d"))],
        ):
            meta = read_huggingface("o/m")
        assert not endpoint.seen
    assert (meta.name, meta.url, meta.license) == (
        "m",
        "https://huggingface.co/o/m",
        None,
    )
    assert meta.extra_data == {
        "hf.model_id": "o/m",
        "hf.url": "https://huggingface.co/o/m",
    }
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert [getattr(r, CODE_ATTR, None) for r in warnings] == [ENDPOINT_REFUSED.code]
    assert warnings[0].getMessage().endswith("; nothing asked of the Hub")


@pytest.mark.parametrize(
    "endpoint",
    [
        DEFAULT_HUB_BASE,
        "https://huggingface.co/",
        "https://HuggingFace.co/",
        "HTTPS://huggingface.co",
        "https://huggingface.co:443",
    ],
)
def test_the_default_endpoint_is_said_nothing_of(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, endpoint: str
) -> None:
    """The default Hub, however spelt, is the default: no ``INFO:``."""
    monkeypatch.setattr(constants, "ENDPOINT", endpoint)
    with caplog.at_level(logging.INFO):
        assert hub_base() == DEFAULT_HUB_BASE
        with hub_files(RemoteFetchPolicy()) as hub:
            assert hub.base == DEFAULT_HUB_BASE
    assert not caplog.records


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://huggingface.co.evil.example",
        "https://huggingface.co:8443",
        "https://huggingface.co/mirror",
        "https://huggingface.co.",
        "https://hf.co",
    ],
)
def test_an_endpoint_like_the_default_is_another_hub(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, endpoint: str
) -> None:
    """A host, port or path other than the default's is another Hub, said
    as one ``INFO:``, and its own host is the one allowed."""
    monkeypatch.setattr(constants, "ENDPOINT", endpoint)
    with caplog.at_level(logging.INFO):
        assert hub_base() == endpoint
    assert _codes(caplog) == [ENDPOINT_MOVED.code]


@pytest.mark.parametrize(
    ("endpoint", "why"),
    [
        ("http://hub.example", "only https is followed"),
        ("https://u:secret@hub.example", "it holds user information"),
        ("https://huggingface.co@evil.example", "it holds user information"),
        ("https://u:secret@huggingface.co", "it holds user information"),
        ("http://huggingface.co", "only https is followed"),
        ("https://huggingface.co?x=1", "it holds a query or a fragment"),
        ("https://hub.example/?x=1", "it holds a query or a fragment"),
        ("https://hub.example/#x", "it holds a query or a fragment"),
        ("https://", "it is not a URL with a host"),
        ("https://hub.example:x", "it is not a URL with a host"),
        ("hub.example", "it is not a URL with a host"),
    ],
)
def test_an_endpoint_is_refused(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    endpoint: str,
    why: str,
) -> None:
    monkeypatch.setattr(constants, "ENDPOINT", endpoint)
    assert endpoint_refusal(endpoint) == why
    assert hub_base() is None
    assert _codes(caplog) == [ENDPOINT_REFUSED.code]
    assert f"({why})" in caplog.text and "secret" not in caplog.text


@pytest.mark.parametrize(
    ("endpoint", "host", "origin"),
    [
        ("https://hub.example", "hub.example", ("https", "hub.example", 443)),
        ("https://Hub.Example:443", "hub.example", ("https", "hub.example", 443)),
        (
            "https://hub.example:8443",
            "hub.example:8443",
            ("https", "hub.example", 8443),
        ),
        ("https://hub.example/hf", "hub.example", ("https", "hub.example", 443)),
    ],
)
def test_an_endpoint_s_host_is_allowed_and_takes_the_token(
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
    host: str,
    origin: tuple[str, str, int],
) -> None:
    """The endpoint replaces huggingface.co: its host (and port) only, the
    CDN's domain kept; the token goes to its origin, not to huggingface.co."""
    monkeypatch.setattr(constants, "ENDPOINT", endpoint)
    monkeypatch.setattr(_hub_files, "hub_token", lambda: TOKEN)
    assert endpoint_refusal(endpoint) is None
    with hub_files(RemoteFetchPolicy()) as hub:
        assert hub.base == endpoint
    http = file_policy(endpoint, None, RemoteFetchPolicy())
    assert http.hosts == frozenset({host}) and http.domains == frozenset({"cdn.hf.co"})
    credential = hub_credential(endpoint)
    assert credential is not None and credential.origin == origin
    assert credential.header_for(f"{endpoint}/o/m") == _BEARER
    assert credential.header_for("https://huggingface.co/o/m") is None
    assert credential.header_for("https://us.aws.cdn.hf.co/x") is None


def test_a_file_url_is_built_on_the_endpoint() -> None:
    url = file_url(_REPO, "config.json", revision=None, base="https://hub.example/hf/")
    assert url == "https://hub.example/hf/o/m/resolve/main/config.json"
    dataset = file_url("o/d", "x", revision=None, repo_type="dataset", base="https://h")
    assert dataset == "https://h/datasets/o/d/resolve/main/x"


def test_a_hub_with_no_host_has_no_file_policy() -> None:
    with pytest.raises(InternalError, match="not a Hub to fetch from"):
        file_policy("https://", None, RemoteFetchPolicy())


def test_no_token_means_no_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_hub_files, "hub_token", lambda: None)
    assert hub_credential("https://hub.example") is None
    monkeypatch.setattr(_hub_files, "hub_token", lambda: TOKEN)
    assert hub_credential("https://") is None


def test_a_hub_with_no_endpoint_reads_nothing_and_fetch_is_a_bug(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``read`` is ``None`` with nothing said (``hub_base`` said it);
    ``fetch`` without a Hub is a programming error."""
    hub = HubFiles(RemoteFetchPolicy(), tmp_path, None, None)
    assert not hub.asks_hub
    assert hub.read(_REPO, "config.json", revision=_SHA, kind=_KIND) is None
    assert not caplog.records
    with pytest.raises(InternalError):
        hub.fetch(_REPO, "config.json", revision=_SHA, cap=HUB_JSON_CAP)
