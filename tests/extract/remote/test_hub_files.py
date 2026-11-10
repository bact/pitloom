# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The Hugging Face route's file downloads
(:mod:`pitloom.extract.remote._hub_files`): the ``max-download-bytes`` cap on
the bytes received, a redirect only to an allowed host (the Hub, or a host
under the CDN's domain), the token sent to the Hub's origin only, the
revision asked, offline mode, and the temporary directory removed.

The Hub and its CDN are local servers (``loopback``, tests/_fake_hub.py).

See also: tests/extract/remote/test_http_credential.py (the origin rule),
tests/extract/remote/test_hub_files_endpoint.py (``HF_ENDPOINT``) and
tests/extract/remote/test_huggingface_hub_route.py (the reader end to end).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.extract.remote import _hub_files
from pitloom.extract.remote._http_credential import Credential
from pitloom.extract.remote._http_fetch import under_domain, url_refusal
from pitloom.extract.remote._hub_files import (
    DEFAULT_HUB_BASE,
    HubFiles,
    file_policy,
    file_url,
    hub_files,
)
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import (
    DOWNLOAD_FAILED,
    OFFLINE_UNUSABLE,
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


#: The default Hub's file policy, with a token.
_HUB_POLICY = file_policy(
    DEFAULT_HUB_BASE,
    Credential(_BEARER, ("https", "huggingface.co", 443)),
    RemoteFetchPolicy(),
)


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("https://huggingface.co/o/m/resolve/main/config.json", True),
        ("https://huggingface.co/api/resolve-cache/models/o/m/1/x", True),
        ("https://us.aws.cdn.hf.co/xet-bridge-us/1/2?X-Xet-Cas-Uid=public", True),
        ("https://eu.aws.cdn.hf.co/xet-bridge-eu/1/2", True),
        ("https://ap-south-1.gcp.cdn.hf.co/x", True),
        ("https://cdn.hf.co/x", True),
        ("https://US.AWS.CDN.HF.CO./x", True),
        ("https://cdn.hf.co.evil.example/x", False),
        ("https://evilcdn.hf.co/x", False),
        ("https://cdn-hf.co/x", False),
        ("https://xcdn.hf.co/x", False),
        ("https://cdn.hf.com/x", False),
        ("https://us.cdn.hf.co../x", False),
        ("https://.cdn.hf.co/x", False),
        ("https://a..cdn.hf.co/x", False),
        ("https://a_b.cdn.hf.co/x", False),
        ("https://-a.cdn.hf.co/x", False),
        ("https://cdn-lfs.hf.co/x", False),
        ("https://hf.co/o/m/resolve/main/config.json", False),
        ("http://us.aws.cdn.hf.co/x", False),
        ("https://us.aws.cdn.hf.co:8443/x", False),
        ("https://u:p@us.aws.cdn.hf.co/x", False),
        ("http://huggingface.co/o/m", False),
        ("https://huggingface.co:8443/o/m", False),
        ("https://www.huggingface.co/o/m", False),
        ("https://huggingface.co.evil.example/o/m", False),
    ],
    ids=lambda v: v if isinstance(v, str) else None,
)
def test_the_hub_and_hosts_under_the_cdn_domain_are_fetched_from(
    url: str, allowed: bool
) -> None:
    """The Hub's own host, and on the default https port any host under
    ``cdn.hf.co`` (the regional CDN, see
    working-docs/implementation/remote-fetch-policy.md); nothing else."""
    hosts, domains = _HUB_POLICY.hosts, _HUB_POLICY.domains
    assert (hosts, domains) == (frozenset({"huggingface.co"}), frozenset({"cdn.hf.co"}))
    assert (url_refusal(url, hosts, domains) is None) is allowed


def test_a_refusal_names_the_hub_and_the_cdn_domain() -> None:
    why = url_refusal("https://x.example/", _HUB_POLICY.hosts, _HUB_POLICY.domains)
    assert why == "its host is not huggingface.co, cdn.hf.co or a name under it"


@pytest.mark.parametrize(
    "url",
    [
        "https://us.aws.cdn.hf.co/xet-bridge-us/x",
        "https://eu.aws.cdn.hf.co/xet-bridge-eu/x",
        "https://cdn.hf.co/x",
    ],
)
def test_no_token_goes_to_a_cdn_host(url: str) -> None:
    assert url_refusal(url, _HUB_POLICY.hosts, _HUB_POLICY.domains) is None
    credential = _HUB_POLICY.credential
    assert credential is not None and credential.header_for(url) is None
    assert credential.header_for("https://huggingface.co/o/m") == _BEARER


def test_under_domain_strips_one_trailing_dot_only() -> None:
    assert under_domain("a.cdn.hf.co.", "cdn.hf.co")
    assert not under_domain("a.cdn.hf.co..", "cdn.hf.co")


def test_a_dataset_file_is_asked_under_datasets() -> None:
    url = file_url("o/d", "README.md", revision=_SHA, repo_type="dataset")
    assert url == f"{DEFAULT_HUB_BASE}/datasets/o/d/resolve/{_SHA}/README.md"


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
    assert _codes(caplog) == [OFFLINE_UNUSABLE.code]
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
