# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every refusal of :func:`pitloom.extract.remote.pypi.fetch_pypi_file`: its
code, its catalogued line, a ``WARNING:`` too, and no file requested that
must not be.

See also: tests/extract/remote/test_pypi_fetch.py (what is read),
tests/extract/remote/test_pypi_http_fetch.py (the client's own caps).
"""

from __future__ import annotations

import errno
import json
import logging
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from packaging.tags import Tag

from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.extract.remote import fetch_pypi_file, pypi, pypi_select
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.pypi import SDIST, WHEEL
from pitloom.messages import (
    DIGEST_MISMATCH,
    DOWNLOAD_FAILED,
    NETWORK_UNUSABLE,
    OVER_CAP,
    PYPI_RESPONSE_INVALID,
    PYPI_URL_INVALID,
    RELEASE_FILE_NOT_FOUND,
    RELEASE_FILE_NOT_FOUND_COMPATIBLE,
    RELEASE_FILE_NOT_FOUND_SDIST,
    RELEASE_NOT_FOUND,
    TEMP_DIR_UNUSABLE,
    URL_REFUSED,
    code_of,
)
from tests._fake_pypi_server import (
    Dist,
    FakePypi,
    Route,
    point_at,
    publish,
    release_json,
    serving,
)

pytestmark = pytest.mark.loopback

_ANY = "x-1.0-py3-none-any.whl"
_PAGE = "https://pypi.org/project/"


@pytest.fixture(name="temp")
def _temp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    temp = tmp_path / "temp"
    temp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    return temp


@pytest.fixture(name="fake")
def _fake(monkeypatch: pytest.MonkeyPatch, temp: Path) -> Iterator[FakePypi]:
    del temp
    tags = [Tag("py3", "none", "any")]
    monkeypatch.setattr(pypi_select, "_environment_tags", lambda: list(tags))
    with serving() as fake:
        point_at(monkeypatch, fake)
        yield fake


def _refused(
    url: str, caplog: pytest.LogCaptureFixture, kind: str = WHEEL, **kwargs: Any
) -> RemoteSourceError:
    """The error *url* raises under the policy *kwargs* make; its text is a
    ``WARNING:`` too."""
    policy = RemoteFetchPolicy(**kwargs)
    with caplog.at_level(logging.WARNING), pytest.raises(RemoteSourceError) as info:
        with fetch_pypi_file(url, kind=kind, policy=policy):
            pass
    assert str(info.value) in caplog.messages
    assert "\n" not in str(info.value)
    return info.value


def test_offline_refuses_before_any_request(
    fake: FakePypi, caplog: pytest.LogCaptureFixture
) -> None:
    error = _refused(f"{_PAGE}x/", caplog, offline=True)
    assert (error.code, error.pitloom_code) == ("pypi.offline", NETWORK_UNUSABLE.code)
    assert str(error) == (
        f"URL={_PAGE}x/: network access is forbidden (offline mode); nothing fetched"
    )
    assert not fake.seen


@pytest.mark.parametrize("offline", [False, True], ids=["online", "offline"])
def test_an_invalid_url_requests_nothing(
    offline: bool, fake: FakePypi, caplog: pytest.LogCaptureFixture
) -> None:
    """The URL is read before *offline*: an invalid one says so either way."""
    with caplog.at_level(logging.WARNING), pytest.raises(ValueError) as info:
        with fetch_pypi_file(
            "http://pypi.org/project/x/",
            kind=WHEEL,
            policy=RemoteFetchPolicy(offline=offline),
        ):
            pass
    assert code_of(info.value) == PYPI_URL_INVALID.code
    assert len(caplog.records) == 1 and not fake.seen


@pytest.mark.parametrize(
    ("releases", "url", "code", "message"),
    [
        ({}, f"{_PAGE}y/", "pypi.project-not-found", "PYPI=y: no such project"),
        (
            {"1.0": [Dist("x-1.0.tar.gz")]},
            f"{_PAGE}x/2.0/",
            "pypi.release-not-found",
            "PYPI=x VERSION=2.0: no such release",
        ),
        (
            {"1.0": [Dist("x-1.0.tar.gz", sha256=None)]},
            f"{_PAGE}x/",
            "pypi.release-not-found",
            "no release has a wheel or sdist",
        ),
    ],
    ids=["project", "version", "no-usable"],
)
def test_what_pypi_does_not_hold(
    fake: FakePypi,
    caplog: pytest.LogCaptureFixture,
    releases: dict[str, list[Dist]],
    url: str,
    code: str,
    message: str,
) -> None:
    publish(fake, "x", releases)
    error = _refused(url, caplog, kind=SDIST)
    assert (error.code, error.pitloom_code) == (code, RELEASE_NOT_FOUND.code)
    assert message in str(error)


@pytest.mark.parametrize(
    ("dists", "kind", "codes", "message"),
    [
        (
            [Dist("x-1.0.tar.gz")],
            WHEEL,
            ("pypi.no-wheel", RELEASE_FILE_NOT_FOUND.code),
            f"'loom project {_PAGE}x/1.0/' reads its sdist",
        ),
        (
            [
                Dist("x-1.0-cp27-cp27m-win32.whl"),
                Dist("x-1.0-cp27-cp27m-macosx_10_9_x86_64.whl"),
            ],
            WHEEL,
            ("pypi.no-compatible-wheel", RELEASE_FILE_NOT_FOUND_COMPATIBLE.code),
            "(wheels: x-1.0-cp27-cp27m-macosx_10_9_x86_64.whl, "
            "x-1.0-cp27-cp27m-win32.whl)",
        ),
        (
            [Dist(_ANY)],
            SDIST,
            ("pypi.no-sdist", RELEASE_FILE_NOT_FOUND_SDIST.code),
            f"'loom wheel {_PAGE}x/1.0/' reads a wheel",
        ),
    ],
    ids=["no-wheel", "no-compatible-wheel", "no-sdist"],
)
def test_a_release_without_the_kind_asked_for(
    fake: FakePypi,
    caplog: pytest.LogCaptureFixture,
    dists: list[Dist],
    kind: str,
    codes: tuple[str, str],
    message: str,
) -> None:
    """No fallback to the other kind: the error names the other command."""
    publish(fake, "x", {"1.0": dists})
    error = _refused(f"{_PAGE}x/1.0/", caplog, kind=kind)
    assert (error.code, error.pitloom_code) == codes
    assert message in str(error)
    assert not any(p.startswith("/files/") for p in fake.seen)


def test_many_incompatible_wheels_are_listed_in_short(
    fake: FakePypi, caplog: pytest.LogCaptureFixture
) -> None:
    publish(
        fake, "x", {"1.0": [Dist(f"x-1.0-cp27-cp27m-win{n:02}.whl") for n in range(12)]}
    )
    error = _refused(f"{_PAGE}x/1.0/", caplog)
    assert "win09.whl and 2 more)" in str(error) and "win10" not in str(error)


def test_a_digest_mismatch_is_an_error_and_no_file(
    fake: FakePypi, caplog: pytest.LogCaptureFixture, temp: Path
) -> None:
    publish(fake, "x", {"1.0": [Dist(_ANY, b"real", sha256="AB" * 32)]})
    error = _refused(f"{_PAGE}x/1.0/", caplog)
    assert (error.code, error.pitloom_code) == (
        "pypi.digest-mismatch",
        DIGEST_MISMATCH.code,
    )
    assert f"FILE={_ANY}: SHA-256 " in str(error) and "ab" * 32 in str(error)
    assert not any(temp.iterdir())


_INVALID = ("pypi.response-invalid", PYPI_RESPONSE_INVALID.code)
_UNSAFE = ("pypi.url-refused", URL_REFUSED.code)


@pytest.mark.parametrize(
    ("dist", "codes", "message"),
    [
        (Dist(_ANY, sha256=None), _INVALID, "declares no SHA-256"),
        (Dist(_ANY, sha256="xyz"), _INVALID, "declares no SHA-256"),
        (
            Dist(_ANY, url="https://evil.example/x-1.0-py3-none-any.whl"),
            _UNSAFE,
            "download URL https://evil.example/",
        ),
        (
            Dist(_ANY, url="file:///etc/passwd"),
            _UNSAFE,
            "download URL file:///etc/passwd",
        ),
    ],
    ids=["no-digest", "bad-digest", "other-host", "file-url"],
)
def test_a_file_that_cannot_be_checked_is_never_requested(
    fake: FakePypi,
    caplog: pytest.LogCaptureFixture,
    dist: Dist,
    codes: tuple[str, str],
    message: str,
) -> None:
    publish(fake, "x", {"1.0": [dist]})
    error = _refused(f"{_PAGE}x/1.0/", caplog)
    assert (error.code, error.pitloom_code) == codes
    assert message in str(error)
    assert fake.seen == ["/pypi/x/1.0/json"]


def test_a_file_over_the_download_cap(
    fake: FakePypi, caplog: pytest.LogCaptureFixture
) -> None:
    publish(fake, "x", {"1.0": [Dist(_ANY, b"x" * 101)]})
    error = _refused(f"{_PAGE}x/1.0/", caplog, max_bytes=100)
    assert (error.code, error.pitloom_code) == ("pypi.too-large", OVER_CAP.code)
    assert (
        str(error) == f"FILE={_ANY}: larger than the 100-byte max-download-bytes cap; "
        "not downloaded"
    )


def test_a_file_gone_from_the_host(
    fake: FakePypi, caplog: pytest.LogCaptureFixture
) -> None:
    publish(fake, "x", {"1.0": [Dist(_ANY)]})
    del fake.routes[f"/files/{_ANY}"]
    error = _refused(f"{_PAGE}x/1.0/", caplog)
    assert (error.code, error.pitloom_code) == (
        "pypi.download-failed",
        DOWNLOAD_FAILED.code,
    )
    assert str(error).endswith(": HTTP Error 404: Not Found; not read")


def _answer(info: object, urls: object = ()) -> Route:
    return Route(body=json.dumps({"info": info, "urls": urls}).encode())


@pytest.mark.parametrize(
    ("route", "message"),
    [
        (_answer({"name": "other", "version": "1.0"}), "answered for project other"),
        (_answer({"name": "X", "version": "2.0"}), "no valid info.version"),
        (_answer({"name": "x", "version": "1.0"}, "nope"), "no valid urls"),
        (_answer({"version": "1.0"}), "no valid info.name"),
        (_answer(["x"]), "no valid info;"),
    ],
    ids=["name", "version", "urls", "no-name", "no-info"],
)
def test_an_answer_that_is_not_about_the_release(
    fake: FakePypi, caplog: pytest.LogCaptureFixture, route: Route, message: str
) -> None:
    fake.routes["/pypi/x/1.0/json"] = route
    error = _refused(f"{_PAGE}x/1.0/", caplog)
    assert (error.code, error.pitloom_code) == (
        "pypi.response-invalid",
        PYPI_RESPONSE_INVALID.code,
    )
    assert message in str(error)


def test_a_listed_release_whose_own_answer_is_gone(
    fake: FakePypi, caplog: pytest.LogCaptureFixture
) -> None:
    publish(fake, "x", {"1.0": [Dist("x-1.0.tar.gz")]})
    del fake.routes["/pypi/x/1.0/json"]
    error = _refused(f"{_PAGE}x/", caplog, kind=SDIST)
    assert error.code == "pypi.release-not-found"


def test_a_project_answer_without_releases(
    fake: FakePypi, caplog: pytest.LogCaptureFixture
) -> None:
    fake.routes["/pypi/x/json"] = Route(body=release_json("x", "1.0", []))
    error = _refused(f"{_PAGE}x/", caplog)
    assert "no valid releases" in str(error)


def test_hostile_file_names_are_skipped_aloud(
    fake: FakePypi, caplog: pytest.LogCaptureFixture, temp: Path
) -> None:
    """Each hostile name is one escaped ``WARNING:``; the good wheel is read
    and nothing is written outside the download directory."""
    hostile = [
        "../x-1.0-py3-none-any.whl",
        "a/x-1.0-py3-none-any.whl",
        "x-1.0\n-py3-none-any.whl",
    ]
    publish(fake, "x", {"1.0": [Dist(name) for name in hostile] + [Dist(_ANY)]})
    with (
        caplog.at_level(logging.WARNING),
        fetch_pypi_file(f"{_PAGE}x/1.0/", kind=WHEEL) as got,
    ):
        assert got.filename == _ANY
        assert sorted(p.name for p in temp.rglob("*") if p.is_file()) == [_ANY]
    skipped = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(skipped) == 3 and all("\n" not in r.getMessage() for r in skipped)
    assert {getattr(r, "pitloom_code", None) for r in skipped} == {
        PYPI_RESPONSE_INVALID.code
    }


def test_a_name_answered_in_other_letters_is_refused(
    fake: FakePypi, caplog: pytest.LogCaptureFixture
) -> None:
    """``\u212a`` (Kelvin) lower-cases to ``k``: an answer naming it is not
    the project ``k``."""
    fake.routes["/pypi/k/1.0/json"] = _answer({"name": "\u212a", "version": "1.0"})
    error = _refused(f"{_PAGE}k/1.0/", caplog)
    assert str(error) == "PYPI=k: PyPI answered for project '\\u212a'; not read"


def test_a_file_name_listed_twice_is_one_warning(
    fake: FakePypi, caplog: pytest.LogCaptureFixture
) -> None:
    publish(
        fake, "x", {"1.0": [Dist(_ANY), Dist(_ANY), Dist("x-1.0-1-py3-none-any.whl")]}
    )
    with (
        caplog.at_level(logging.WARNING),
        fetch_pypi_file(f"{_PAGE}x/1.0/", kind=WHEEL) as got,
    ):
        assert got.filename == "x-1.0-1-py3-none-any.whl"
    warnings = [m for m in caplog.messages if "more than once" in m]
    assert warnings == [
        f"PYPI=x FILE={_ANY}: the answer lists the file name more than once; skipped"
    ]


class _FullDisk:
    """A download directory whose file cannot be written (a full disk)."""

    def __truediv__(self, _name: str) -> _FullDisk:
        return self

    def open(self, _mode: str) -> Any:
        """Refuse, as a full disk does."""
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))


def test_a_file_that_cannot_be_saved_is_no_network_failure(
    fake: FakePypi, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    publish(fake, "x", {"1.0": [Dist(_ANY)]})

    @contextmanager
    def full_disk(_prefix: str, *, log_prefix: str) -> Iterator[_FullDisk]:
        del log_prefix
        yield _FullDisk()

    monkeypatch.setattr(pypi, "temp_dir", full_disk)
    error = _refused(f"{_PAGE}x/1.0/", caplog)
    assert (error.code, error.pitloom_code) == (
        "pypi.save-failed",
        TEMP_DIR_UNUSABLE.code,
    )
    assert str(error) == (
        f"FILE={_ANY}: could not be saved in the temporary directory "
        f"({os.strerror(errno.ENOSPC)}); not downloaded"
    )
