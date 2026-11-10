# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The Hugging Face route's file downloads
(:mod:`pitloom.extract.remote._hub_files`): the ``max-download-bytes`` cap on
the bytes received, a redirect only to an allowed host, the token sent to the
Hub's origin only, the revision asked, offline mode, and the temporary
directory removed.

The Hub and its CDN are local servers (``loopback``, tests/_fake_hub.py).

See also: tests/extract/remote/test_http_credential.py (the origin rule) and
tests/extract/remote/test_huggingface_hub_route.py (the reader end to end).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.extract.remote import _hub_files
from pitloom.extract.remote._http_fetch import url_refusal
from pitloom.extract.remote._hub_files import HubFiles, file_url, hub_files
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import (
    DOWNLOAD_FAILED,
    NETWORK_UNUSABLE,
    OVER_CAP,
    URL_REFUSED,
)
from tests._fake_hub import (
    TOKEN,
    FakeHub,
    hub_and_cdn,
    point_hub_at,
    serve_in_git,
    serve_in_xet,
)
from tests._fake_pypi_server import Route, redirect, serving

pytestmark = pytest.mark.loopback

_REPO = "o/m"
_SHA = "0123456789abcdef0123456789abcdef01234567"
_BEARER = f"Bearer {TOKEN}"
#: The module's own token lookup, before a test replaces it.
_real_hub_token = _hub_files.hub_token


@pytest.fixture(name="fake")
def _fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeHub]:
    with hub_and_cdn() as fake:
        point_hub_at(monkeypatch, fake)
        yield fake


def _read(
    policy: RemoteFetchPolicy = RemoteFetchPolicy(),
    *,
    revision: str | None = _SHA,
    filename: str = "config.json",
) -> bytes | None:
    """What the route reads of *filename*: its bytes, or ``None``."""
    with hub_files(policy) as hub:
        path = hub.read(_REPO, filename, revision=revision, outcome="x not read")
        return None if path is None else path.read_bytes()


def _codes(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [getattr(r, CODE_ATTR) for r in caplog.records if hasattr(r, CODE_ATTR)]


def test_a_file_kept_in_git_is_read_with_the_token_on_the_hub(fake: FakeHub) -> None:
    cache = serve_in_git(fake, _REPO, "config.json", b'{"a": 1}', revision=_SHA)
    assert _read() == b'{"a": 1}'
    assert fake.hub.seen == [f"/{_REPO}/resolve/{_SHA}/config.json", cache]
    assert [h.get("authorization") for h in fake.hub.headers] == [_BEARER] * 2
    assert fake.hub.headers[0]["user-agent"] == "pitloom-huggingface"


def test_the_token_never_reaches_the_cdn(fake: FakeHub) -> None:
    """The CDN is another origin (another port of the same host): the
    signed URL is asked without the token."""
    signed = serve_in_xet(fake, _REPO, "README.md", b"# card", revision=_SHA)
    assert _read(filename="README.md") == b"# card"
    assert fake.hub.headers[0].get("authorization") == _BEARER
    assert fake.cdn.seen == [signed + "?X-Xet-Signed=1"]
    assert "authorization" not in fake.cdn.headers[0]


def test_no_token_is_sent_when_there_is_none(
    fake: FakeHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    point_hub_at(monkeypatch, fake, token=None)
    serve_in_git(fake, _REPO, "config.json", b"{}", revision=_SHA)
    assert _read() == b"{}"
    assert all("authorization" not in h for h in fake.hub.headers)


def test_the_token_is_the_one_huggingface_hub_sends(
    fake: FakeHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``HF_TOKEN``, read by ``huggingface_hub.get_token`` at the call."""
    monkeypatch.setattr(_hub_files, "hub_token", _real_hub_token)
    monkeypatch.setenv("HF_TOKEN", "hf_from_env")
    serve_in_git(fake, _REPO, "config.json", b"{}", revision=_SHA)
    assert _read() == b"{}"
    assert fake.hub.headers[0].get("authorization") == "Bearer hf_from_env"


@pytest.mark.parametrize(
    ("revision", "asked"), [(_SHA, _SHA), (None, "main"), ("v1/x", "v1%2Fx")]
)
def test_the_revision_is_asked(fake: FakeHub, revision: str | None, asked: str) -> None:
    fake.hub.routes[f"/{_REPO}/resolve/{asked}/config.json"] = Route(body=b"{}")
    assert _read(revision=revision) == b"{}"
    assert fake.hub.seen == [f"/{_REPO}/resolve/{asked}/config.json"]


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("https://huggingface.co/o/m/resolve/main/config.json", True),
        ("https://huggingface.co/api/resolve-cache/models/o/m/1/x", True),
        ("https://us.aws.cdn.hf.co/xet-bridge-us/1/2?X-Xet-Cas-Uid=public", True),
        ("https://cdn-lfs.hf.co/x", False),
        ("https://hf.co/o/m/resolve/main/config.json", False),
        ("http://huggingface.co/o/m", False),
        ("https://huggingface.co:8443/o/m", False),
        ("https://huggingface.co.evil.example/o/m", False),
    ],
)
def test_only_the_measured_hosts_are_fetched_from(url: str, allowed: bool) -> None:
    """The Hub and the one CDN host it was measured to redirect a file to
    (see working-docs/implementation/remote-fetch-policy.md); nothing else."""
    assert (url_refusal(url, _hub_files.FILE_HOSTS) is None) is allowed


def test_a_dataset_file_is_asked_under_datasets() -> None:
    url = file_url("o/d", "README.md", revision=_SHA, repo_type="dataset")
    assert url == f"{_hub_files.HUB_BASE}/datasets/o/d/resolve/{_SHA}/README.md"


def test_a_file_the_repository_does_not_hold_is_absent_silently(
    fake: FakeHub, caplog: pytest.LogCaptureFixture
) -> None:
    assert _read() is None
    assert fake.hub.seen == [f"/{_REPO}/resolve/{_SHA}/config.json"]
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.parametrize("status", [401, 403, 500])
def test_a_failed_request_is_one_warning(
    fake: FakeHub, caplog: pytest.LogCaptureFixture, status: int
) -> None:
    fake.hub.routes[f"/{_REPO}/resolve/{_SHA}/config.json"] = Route(status=status)
    assert _read() is None
    assert _codes(caplog) == [DOWNLOAD_FAILED.code]
    message = caplog.records[-1].getMessage()
    assert f"HTTP Error {status}" in message and message.endswith("; x not read")


@pytest.mark.parametrize("length", [-1, None], ids=["no-length", "true-length"])
def test_the_cap_holds_on_the_bytes_received(
    fake: FakeHub, caplog: pytest.LogCaptureFixture, length: int | None
) -> None:
    """With or without a ``Content-Length``, more than ``max_bytes``
    received stops the file: ``over-cap``."""
    serve_in_git(fake, _REPO, "config.json", b"x" * 101, revision=_SHA, length=length)
    assert _read(RemoteFetchPolicy(max_bytes=100)) is None
    assert _codes(caplog) == [OVER_CAP.code]
    message = caplog.records[-1].getMessage()
    assert message.startswith(f"FILE={_REPO}/config.json: larger than the 100-byte")
    assert message.endswith("max-download-bytes cap; x not read")


def test_a_lying_length_over_the_cap_gates_nothing(
    fake: FakeHub, caplog: pytest.LogCaptureFixture
) -> None:
    """A ``Content-Length`` over the cap is not acted on: the 50 bytes sent
    are under it, and the answer is cut short of what it declared (a failed
    download), not over the cap."""
    serve_in_git(fake, _REPO, "config.json", b"x" * 50, revision=_SHA, length=1000)
    assert _read(RemoteFetchPolicy(max_bytes=100)) is None
    assert _codes(caplog) == [DOWNLOAD_FAILED.code]
    assert "ended after 50 of 1000 bytes" in caplog.text


def test_a_file_at_the_cap_is_read(fake: FakeHub) -> None:
    serve_in_git(fake, _REPO, "config.json", b"x" * 100, revision=_SHA, length=-1)
    assert _read(RemoteFetchPolicy(max_bytes=100)) == b"x" * 100


def test_a_redirect_to_another_host_is_not_followed(
    fake: FakeHub, caplog: pytest.LogCaptureFixture
) -> None:
    with serving({"/x": Route(body=b"{}")}) as other:
        fake.hub.routes[f"/{_REPO}/resolve/{_SHA}/config.json"] = redirect(
            other.url("/x")
        )
        assert _read() is None
        assert not other.seen
    assert _codes(caplog) == [URL_REFUSED.code]


def test_check_url_sees_each_url_and_its_refusal_stops_the_read(
    fake: FakeHub,
) -> None:
    serve_in_git(fake, _REPO, "config.json", b"{}", revision=_SHA)
    seen: list[str] = []
    assert _read(RemoteFetchPolicy(check_url=seen.append)) == b"{}"
    assert [u.removeprefix(fake.hub.base) for u in seen] == fake.hub.seen

    def refuse(url: str) -> None:
        raise RemoteSourceError("caller.refused", f"no: {url}")

    with pytest.raises(RemoteSourceError, match="no: "):
        _read(RemoteFetchPolicy(check_url=refuse))


def test_hf_hub_offline_fetches_nothing(
    fake: FakeHub,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    point_hub_at(monkeypatch, fake, offline=True)
    serve_in_git(fake, _REPO, "config.json", b"{}", revision=_SHA)
    assert _read() is None
    assert not fake.hub.seen
    assert _codes(caplog) == [NETWORK_UNUSABLE.code]
    assert "network access is forbidden" in caplog.text


def test_files_land_in_a_temporary_directory_removed_on_exit(fake: FakeHub) -> None:
    serve_in_git(fake, _REPO, "config.json", b"{}", revision=_SHA)
    serve_in_git(fake, _REPO, "README.md", b"# c", revision=_SHA)
    with hub_files(RemoteFetchPolicy()) as hub:
        first = hub.fetch(_REPO, "config.json", revision=_SHA)
        second = hub.fetch(_REPO, "README.md", revision=_SHA)
        assert first is not None and second is not None
        work = hub.work_dir
        assert work.name.startswith("pitloom-hf-")
        assert first.parent.parent == work == second.parent.parent
        assert first.parent != second.parent
    assert not work.exists()


def test_a_hub_files_takes_the_policy_cap() -> None:
    hub = HubFiles(RemoteFetchPolicy(max_bytes=7), Path("."), None)
    assert hub.policy.max_bytes == 7
