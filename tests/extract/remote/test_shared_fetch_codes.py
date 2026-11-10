# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every remote route says a shared condition with the same catalogued code:
over the cap (``over-cap``), a failed request (``download-network-failed``),
a timeout (``download-timeout``) and offline mode (``offline-unusable``),
for a Git URL, a PyPI URL and a Hugging Face model alike. Git and PyPI
raise it as the ``pitloom_code`` of a
:class:`~pitloom.extract.remote.errors.RemoteSourceError`; Hugging Face says
it as a ``WARNING:`` and reads on (or, offline, raises it). A git failure
that is no network failure carries no code.

See also: tests/extract/remote/test_hub_files.py,
tests/extract/remote/test_pypi_fetch_refusals.py and
tests/extract/remote/test_git_hardening.py (each route's own cases).
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from packaging.tags import Tag

from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.extract.remote import _git_run, _http_fetch, pypi_select
from pitloom.extract.remote._git_run import GitRunner, is_network_failure
from pitloom.extract.remote._hub_files import hub_files
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.git import fetch_git_project
from pitloom.extract.remote.huggingface import read_huggingface
from pitloom.extract.remote.pypi import WHEEL, fetch_pypi_file
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import (
    DOWNLOAD_FAILED,
    DOWNLOAD_TIMEOUT,
    OFFLINE_UNUSABLE,
    OVER_CAP,
    Message,
    trusted_message,
)
from tests._fake_hub import hub_and_cdn, point_hub_at, serve_in_git
from tests._fake_pypi_server import Dist, Route, point_at, publish, serving

_needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

_ANY = "x-1.0-py3-none-any.whl"
_PYPI = "https://pypi.org/project/x/1.0/"
_SHA = "0123456789abcdef0123456789abcdef01234567"


def _raised(run: Callable[[], object]) -> RemoteSourceError:
    with pytest.raises(RemoteSourceError) as info:
        run()
    return info.value


def _said_as(error: RemoteSourceError, message: Message) -> bool:
    """*error* carries *message*'s code, and its text is one of its
    ``ERROR`` lines."""
    printed = f"ERROR: {error} [{error.pitloom_code}]"
    return error.pitloom_code == message.code and trusted_message(printed) is message


# -- Git ------------------------------------------------------------------


def _git_answers(
    monkeypatch: pytest.MonkeyPatch, status: int | None, err: str = ""
) -> None:
    """git's every call exits *status* (``None``: killed for time), writing
    *err*."""

    def capture(*_args: object) -> tuple[int | None, str | None, str]:
        return status, None if status is None else "", err

    monkeypatch.setattr(_git_run, "_capture", capture)


@pytest.mark.parametrize(
    "err",
    [
        "fatal: unable to access 'https://h/r/': Could not resolve host: h",
        "fatal: unable to access 'https://h/r/': Failed to connect to h port 443",
        "fatal: unable to access 'https://h/r/': Connection timed out after 1 ms",
        "fatal: unable to access 'https://h/r/': SSL certificate problem: expired",
        "fatal: unable to access 'https://h/r/': The requested URL returned error: 502",
        "error: RPC failed; curl 56 Recv failure: Connection reset by peer",
        "fatal: early EOF",
    ],
)
def test_a_git_network_failure_is_download_network_failed(err: str) -> None:
    assert is_network_failure(err)


@pytest.mark.parametrize(
    "err",
    [
        "remote: Repository not found.\nfatal: repository 'https://h/r/' not found",
        "fatal: Authentication failed for 'https://h/r/'",
        "fatal: could not read Username for 'https://h': terminal prompts disabled",
        "fatal: Remote branch nope not found in upstream origin",
        "fatal: unable to access 'https://h/r/': The requested URL returned error: 404",
        "error: RPC failed; HTTP 400 curl 22 The requested URL returned error: 400",
        "fatal: couldn't find remote ref refs/tags/v9",
        # A network word outside git's error lines is no cause.
        "warning: SSL is fine\nfatal: Remote branch x not found",
    ],
)
def test_a_git_failure_of_another_cause_carries_no_code(err: str) -> None:
    assert not is_network_failure(err)


@_needs_git
@pytest.mark.parametrize(
    ("err", "message"),
    [
        ("fatal: unable to access 'https://h/r/': Could not resolve host: h",
         DOWNLOAD_FAILED),
        ("fatal: repository 'https://h/r/' not found", None),
    ],
    ids=["network", "not-found"],
)  # fmt: skip
def test_a_failed_git_call_carries_the_shared_code_of_its_cause(
    monkeypatch: pytest.MonkeyPatch, err: str, message: Message | None
) -> None:
    _git_answers(monkeypatch, 128, err)
    error = _raised(lambda: GitRunner().run(["clone"], "clone", echo=False))
    assert error.code == "git.clone-failed"
    if message is None:
        assert error.pitloom_code is None and str(error) == err
    else:
        assert _said_as(error, message)
        assert str(error) == f"git clone failed: {err}; nothing fetched"


@_needs_git
@pytest.mark.parametrize("seconds", [600.0, 0.0], ids=["killed", "never-started"])
def test_a_git_timeout_is_download_timeout(
    monkeypatch: pytest.MonkeyPatch, seconds: float
) -> None:
    _git_answers(monkeypatch, None)
    error = _raised(
        lambda: GitRunner(seconds=seconds).run(["clone"], "clone", echo=False)
    )
    assert error.code == "git.timeout" and _said_as(error, DOWNLOAD_TIMEOUT)


@_needs_git
def test_a_git_checkout_over_the_cap_is_over_cap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "big").write_bytes(b"x" * 101)
    _git_answers(monkeypatch, 0)
    runner = GitRunner(max_bytes=100)
    error = _raised(
        lambda: runner.run(["clone"], "clone", echo=False, watch=str(tmp_path))
    )
    assert error.code == "git.too-large" and _said_as(error, OVER_CAP)


def test_git_offline_is_offline_unusable() -> None:
    def run() -> None:
        with fetch_git_project(
            "https://h.invalid/o/r", policy=RemoteFetchPolicy(offline=True)
        ):
            pass  # pragma: no cover

    error = _raised(run)
    assert error.code == "git.offline" and _said_as(error, OFFLINE_UNUSABLE)


# -- PyPI -----------------------------------------------------------------


@pytest.fixture(name="pypi")
def _pypi(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(
        pypi_select, "_environment_tags", lambda: [Tag("py3", "none", "any")]
    )
    with serving() as fake:
        point_at(monkeypatch, fake)
        publish(fake, "x", {"1.0": [Dist(_ANY, b"x" * 101)]})
        fake.routes[f"/files/{_ANY}"] = Route(body=b"x" * 101, drip=0.05)
        yield


def _pypi_error(policy: RemoteFetchPolicy) -> RemoteSourceError:
    def run() -> None:
        with fetch_pypi_file(_PYPI, kind=WHEEL, policy=policy):
            pass  # pragma: no cover

    return _raised(run)


@pytest.mark.loopback
@pytest.mark.usefixtures("pypi")
def test_pypi_over_the_cap_is_over_cap() -> None:
    error = _pypi_error(RemoteFetchPolicy(max_bytes=100))
    assert error.code == "pypi.too-large" and _said_as(error, OVER_CAP)


@pytest.mark.loopback
@pytest.mark.usefixtures("pypi")
def test_pypi_timeout_is_download_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_http_fetch, "FILE_DEADLINE_SECONDS", 0.2)
    error = _pypi_error(RemoteFetchPolicy())
    assert error.code == "pypi.download-timeout" and _said_as(error, DOWNLOAD_TIMEOUT)


@pytest.mark.loopback
def test_pypi_network_failure_is_download_network_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with serving({"/pypi/x/1.0/json": Route(status=503)}) as fake:
        point_at(monkeypatch, fake)
        error = _pypi_error(RemoteFetchPolicy())
    assert error.code == "pypi.download-failed" and _said_as(error, DOWNLOAD_FAILED)


def test_pypi_offline_is_offline_unusable() -> None:
    error = _pypi_error(RemoteFetchPolicy(offline=True))
    assert error.code == "pypi.offline" and _said_as(error, OFFLINE_UNUSABLE)


# -- Hugging Face -----------------------------------------------------------


def _hub_code(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    route: Route,
    policy: RemoteFetchPolicy = RemoteFetchPolicy(),
) -> list[str]:
    """The codes the Hub route says reading a file the Hub answers with
    *route*; the file is left out."""
    with hub_and_cdn() as fake:
        point_hub_at(monkeypatch, fake)
        cache = serve_in_git(fake, "o/m", "config.json", b"", revision=_SHA)
        fake.hub.routes[cache] = route
        with caplog.at_level(logging.WARNING), hub_files(policy) as hub:
            assert hub.read("o/m", "config.json", revision=_SHA, outcome="o") is None
    return [getattr(r, CODE_ATTR) for r in caplog.records if hasattr(r, CODE_ATTR)]


@pytest.mark.loopback
@pytest.mark.parametrize(
    ("route", "policy", "message"),
    [
        (Route(body=b"x" * 101), RemoteFetchPolicy(max_bytes=100), OVER_CAP),
        (Route(status=503), RemoteFetchPolicy(), DOWNLOAD_FAILED),
        (Route(body=b"x" * 10, drip=0.1), RemoteFetchPolicy(), DOWNLOAD_TIMEOUT),
    ],
    ids=["over-cap", "network-failed", "timeout"],
)
def test_the_hub_says_each_condition_with_the_shared_code(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    route: Route,
    policy: RemoteFetchPolicy,
    message: Message,
) -> None:
    monkeypatch.setattr(_http_fetch, "FILE_DEADLINE_SECONDS", 0.3)
    assert _hub_code(monkeypatch, caplog, route, policy) == [message.code]
    printed = f"WARNING: {caplog.records[-1].getMessage()} [{message.code}]"
    assert trusted_message(printed) is message


def test_hub_offline_is_offline_unusable() -> None:
    error = _raised(
        lambda: read_huggingface("o/m", policy=RemoteFetchPolicy(offline=True))
    )
    assert error.code == "huggingface.offline" and _said_as(error, OFFLINE_UNUSABLE)
    assert str(error).startswith("URL=https://huggingface.co/o/m: ")
