# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Fetching a PyPI release's wheel or sdist
(:func:`pitloom.extract.remote.pypi.fetch_pypi_file`): what it downloads, the
decisions it says, the temporary directory, and one live check.

The JSON API and the file host are a local server (``loopback``); the
environment's tag order is patched.

See also: tests/extract/remote/test_pypi_fetch_refusals.py (every refusal),
tests/_fake_pypi_server.py.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from packaging.tags import Tag

from pitloom.core import temp_dirs
from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.core.url_masking import DOWNLOAD_PLACEHOLDER
from pitloom.extract.remote import fetch_pypi_file, pypi_select
from pitloom.extract.remote.pypi import (
    DEFAULT_MAX_DOWNLOAD_BYTES,
    SDIST,
    WHEEL,
    sdist_hint,
)
from pitloom.logging_config import configure_logging
from pitloom.messages.pypi import (
    FILE_AMBIGUOUS,
    RELEASE_UNPINNED,
    RELEASE_UNPINNED_PRERELEASE,
    RELEASE_UNPINNED_YANKED,
    RELEASE_YANKED,
)
from tests._fake_pypi_server import (
    Dist,
    FakePypi,
    point_at,
    publish,
    serving,
    sha256_of,
)
from tests._network import skip_on_network_error

_ANY = "x-1.0-py3-none-any.whl"
_TAGS = [Tag("cp313", "cp313", "linux_x86_64"), Tag("py3", "none", "any")]
_PAGE = "https://pypi.org/project/"


@pytest.fixture(name="temp")
def _temp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """The system temporary directory, a fresh one for this test."""
    temp = tmp_path / "temp"
    temp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    return temp


@pytest.fixture(name="fake")
def _fake(monkeypatch: pytest.MonkeyPatch, temp: Path) -> Iterator[FakePypi]:
    """A fake PyPI the resolver asks, the tag order patched."""
    del temp
    monkeypatch.setattr(pypi_select, "_environment_tags", lambda: list(_TAGS))
    with serving() as fake:
        point_at(monkeypatch, fake)
        yield fake


def _codes(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [getattr(r, "pitloom_code", "") for r in caplog.records]


@pytest.mark.loopback
def test_a_pinned_wheel_is_downloaded_and_verified(fake: FakePypi, temp: Path) -> None:
    data = b"wheel bytes" * 100
    publish(fake, "x", {"1.0": [Dist(_ANY, data), Dist("x-1.0.tar.gz")]})
    with fetch_pypi_file(f"{_PAGE}X/1.0/", kind=WHEEL) as got:
        assert got.path.read_bytes() == data
        assert got.path.name == _ANY and got.path.parent.parent == temp
        assert got.path.parent.name.startswith("pitloom-pypi-")
        folder = got.path.parent
    assert not folder.exists() and not any(temp.iterdir())
    assert (got.filename, got.kind, got.name, got.version) == (_ANY, WHEEL, "x", "1.0")
    assert got.project_url == f"{_PAGE}x/1.0/"
    assert got.file_url == fake.url(f"/files/{_ANY}")
    assert (got.sha256, got.size) == (sha256_of(data), len(data))
    assert got.tags == ("py3-none-any",) and got.chosen_by == "running-environment"
    assert (got.status, got.compatible_skipped) == ((), 0)
    assert got.requested_version == "1.0"
    assert fake.seen == ["/pypi/x/1.0/json", f"/files/{_ANY}"]


@pytest.mark.loopback
def test_an_sdist_is_downloaded(fake: FakePypi) -> None:
    publish(fake, "x", {"1.0": [Dist(_ANY), Dist("x-1.0.tar.gz", b"sdist")]})
    with fetch_pypi_file(f"{_PAGE}x/1.0", kind=SDIST) as got:
        assert got.path.read_bytes() == b"sdist"
    assert (got.kind, got.tags, got.chosen_by, got.compatible_skipped) == (
        SDIST,
        (),
        None,
        0,
    )


@pytest.mark.loopback
def test_a_directory_left_behind_warns_once_and_never_raises(
    fake: FakePypi,
    temp: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A removal that fails (a file held open on Windows) is no error: the
    caller has its result, and one ``WARNING:`` names the directory."""
    publish(fake, "x", {"1.0": [Dist(_ANY)]})
    monkeypatch.setattr(temp_dirs, "rmtree_quietly", lambda _path, _prefix: None)
    with caplog.at_level(logging.WARNING):
        with fetch_pypi_file(f"{_PAGE}x/1.0/", kind=WHEEL) as got:
            folder = got.path.parent
    assert folder.is_dir() and folder.parent == temp
    assert [r.getMessage() for r in caplog.records] == [
        f"PyPI source: could not fully remove temporary directory "
        f"'{DOWNLOAD_PLACEHOLDER}' (in the system temp directory)"
    ]


@pytest.mark.loopback
def test_every_url_requested_is_checked_first(fake: FakePypi) -> None:
    publish(fake, "x", {"1.0": [Dist(_ANY)]})
    checked: list[str] = []
    policy = RemoteFetchPolicy(check_url=checked.append)
    with fetch_pypi_file(f"{_PAGE}x/1.0/", kind=WHEEL, policy=policy):
        pass
    assert checked == [fake.url("/pypi/x/1.0/json"), fake.url(f"/files/{_ANY}")]


@pytest.mark.loopback
@pytest.mark.parametrize(
    ("releases", "version", "code", "status"),
    [
        (
            {
                "0.9": [Dist("x-0.9.tar.gz")],
                "1.0": [Dist("x-1.0.tar.gz")],
                "2.0b1": [Dist("x-2.0b1.tar.gz")],
            },
            "1.0",
            RELEASE_UNPINNED.code,
            (),
        ),
        (
            {
                "2.0b1": [Dist("x-2.0b1.tar.gz")],
                "1.0": [Dist("x-1.0.tar.gz", yanked=True)],
            },
            "2.0b1",
            RELEASE_UNPINNED_PRERELEASE.code,
            ("prerelease",),
        ),
        (
            {"1.0": [Dist("x-1.0.tar.gz", yanked=True, reason="broken\nbuild")]},
            "1.0",
            RELEASE_UNPINNED_YANKED.code,
            ("yanked",),
        ),
    ],
    ids=["latest", "prerelease-only", "yanked-only"],
)
def test_no_version_reads_the_cascades_pick_and_says_so(
    fake: FakePypi,
    caplog: pytest.LogCaptureFixture,
    releases: dict[str, list[Dist]],
    version: str,
    code: str,
    status: tuple[str, ...],
) -> None:
    publish(fake, "x", releases)
    with (
        caplog.at_level(logging.INFO),
        fetch_pypi_file(f"{_PAGE}x/", kind=SDIST) as got,
    ):
        pass
    assert (got.version, got.status, got.requested_version) == (version, status, None)
    assert got.project_url == f"{_PAGE}x/{version}/"
    assert fake.seen[:2] == ["/pypi/x/json", f"/pypi/x/{version}/json"]
    assert _codes(caplog).count(code) == 1
    assert all("\n" not in m for m in caplog.messages)
    if "yanked" in status:
        assert got.yanked_reason == "broken\nbuild"
        assert "broken\\nbuild" in caplog.text


@pytest.mark.loopback
def test_a_named_yanked_or_prerelease_is_read_and_said(
    fake: FakePypi, caplog: pytest.LogCaptureFixture
) -> None:
    publish(
        fake,
        "x",
        {
            "1.0": [Dist("x-1.0.tar.gz", yanked=True)],
            "2.0rc1": [Dist("x-2.0rc1.tar.gz")],
        },
    )
    with caplog.at_level(logging.INFO):
        with fetch_pypi_file(f"{_PAGE}x/1.0/", kind=SDIST) as yanked:
            pass
        with fetch_pypi_file(f"{_PAGE}x/2.0rc1/", kind=SDIST) as pre:
            pass
    assert (yanked.status, yanked.yanked_reason) == (("yanked",), None)
    assert pre.status == ("prerelease",)
    assert _codes(caplog).count(RELEASE_YANKED.code) == 1
    assert (
        "PYPI=x VERSION=1.0 FILE=x-1.0.tar.gz: the file is yanked (no reason given)"
        in caplog.text
    )
    assert not any("2.0rc1" in m for m in caplog.messages)  # as asked: no line


@pytest.mark.loopback
def test_a_yanked_file_of_a_stable_release_is_said_as_a_file(
    fake: FakePypi, caplog: pytest.LogCaptureFixture
) -> None:
    """No version given; the release counts as stable (its other wheel is
    not yanked), but the one wheel this environment takes is yanked: the
    yanked line names that file, and the reason falls back to the
    release's own."""
    publish(
        fake,
        "x",
        {"1.0": [Dist(_ANY, yanked=True), Dist("x-1.0-cp27-cp27m-win32.whl")]},
        yanked_reason="broken metadata",
    )
    with (
        caplog.at_level(logging.INFO),
        fetch_pypi_file(f"{_PAGE}x/", kind=WHEEL) as got,
    ):
        pass
    assert (got.status, got.yanked_reason) == (("yanked",), "broken metadata")
    codes = _codes(caplog)
    assert codes.count(RELEASE_UNPINNED.code) == codes.count(RELEASE_YANKED.code) == 1
    assert (
        f"PYPI=x VERSION=1.0 FILE={_ANY}: the file is yanked (broken metadata); "
        "reading it anyway" in caplog.messages
    )


@pytest.mark.loopback
def test_an_equal_version_spelling_finds_the_release(fake: FakePypi) -> None:
    """PyPI lists ``1.0``; the URL says ``1.0.0``: equal by PEP 440."""
    publish(fake, "x", {"1.0": [Dist("x-1.0.tar.gz")]})
    with fetch_pypi_file(f"{_PAGE}x/1.0.0/", kind=SDIST) as got:
        pass
    assert got.version == "1.0"
    assert fake.seen[:3] == ["/pypi/x/1.0.0/json", "/pypi/x/json", "/pypi/x/1.0/json"]


@pytest.mark.loopback
@pytest.mark.parametrize(
    ("dists", "kind", "chosen", "number"),
    [
        (
            [
                Dist(_ANY),
                Dist("x-1.0-cp313-cp313-linux_x86_64.whl"),
                Dist("x-1.0-cp27-none-any.whl"),
            ],
            WHEEL,
            "x-1.0-cp313-cp313-linux_x86_64.whl",
            2,
        ),
        ([Dist("x-1.0.zip"), Dist("x-1.0.tar.gz")], SDIST, "x-1.0.tar.gz", 2),
    ],
    ids=["wheels", "sdists"],
)
def test_several_candidates_are_one_info(
    fake: FakePypi,
    caplog: pytest.LogCaptureFixture,
    dists: list[Dist],
    kind: str,
    chosen: str,
    number: int,
) -> None:
    publish(fake, "x", {"1.0": dists})
    with (
        caplog.at_level(logging.INFO),
        fetch_pypi_file(f"{_PAGE}x/1.0/", kind=kind) as got,
    ):
        pass
    assert got.filename == chosen
    assert got.compatible_skipped == (number - 1 if kind == WHEEL else 0)
    lines = [
        message
        for message, code in zip(caplog.messages, _codes(caplog), strict=True)
        if code == FILE_AMBIGUOUS.code
    ]
    assert len(lines) == 1 and f"{number} " in lines[0] and chosen in lines[0]


@pytest.mark.loopback
def test_a_query_is_cut_aloud(fake: FakePypi, caplog: pytest.LogCaptureFixture) -> None:
    publish(fake, "x", {"1.0": [Dist(_ANY)]})
    with (
        caplog.at_level(logging.INFO),
        fetch_pypi_file(f"{_PAGE}x/1.0/?a=1#f", kind=WHEEL),
    ):
        pass
    assert f"URL={_PAGE}x/1.0/?a=1#f: the query and fragment have no effect; cut" in (
        caplog.messages
    )
    assert all("?" not in path for path in fake.seen)


@pytest.mark.loopback
def test_the_temporary_directory_is_removed_on_error(
    fake: FakePypi, temp: Path
) -> None:
    publish(fake, "x", {"1.0": [Dist(_ANY)]})
    with pytest.raises(RuntimeError, match="reader failed"):
        with fetch_pypi_file(f"{_PAGE}x/1.0/", kind=WHEEL) as got:
            assert got.path.is_file()
            raise RuntimeError("reader failed")
    assert not any(temp.iterdir())


@pytest.mark.loopback
@pytest.mark.parametrize("sha256", ["", "00" * 32], ids=["ok", "mismatch"])
def test_stderr_never_names_the_download_directory(
    fake: FakePypi, capsys: pytest.CaptureFixture[str], sha256: str
) -> None:
    publish(
        fake,
        "x",
        {"1.0": [Dist(_ANY, sha256=sha256), Dist("x-1.0-py3-none-any-x.whl")]},
    )
    configure_logging()
    try:
        with fetch_pypi_file(f"{_PAGE}x/1.0/", kind=WHEEL) as got:
            logging.getLogger("pitloom.test").warning("read %s", got.path)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        assert "pitloom-pypi-" not in str(exc)
    err = capsys.readouterr().err
    assert "pitloom-pypi-" not in err and "PYPI=x" in err
    assert ("<download>" in err) is (not sha256)


def test_sdist_hint_names_loom_project(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        sdist_hint("https://pypi.org/project/X_y/1.0/?tab=files")
    assert caplog.messages == [
        "PYPI=x-y: loom generate reads the wheel; "
        "'loom project https://pypi.org/project/x-y/1.0/' reads the sdist"
    ]
    assert _codes(caplog) == [FILE_AMBIGUOUS.code]


def test_a_bad_kind_raises_before_anything() -> None:
    # A bad cap is refused where the policy is made
    # (tests/core/test_fetch_policy.py).
    with pytest.raises(ValueError, match="kind"):
        with fetch_pypi_file(f"{_PAGE}x/", kind="egg"):
            pass


def test_the_default_cap() -> None:
    assert DEFAULT_MAX_DOWNLOAD_BYTES == 512 * 1024 * 1024


@pytest.mark.network
def test_a_real_release_downloads_and_verifies() -> None:
    """A tiny pure-Python wheel and its sdist from the real PyPI."""
    with skip_on_network_error():
        with fetch_pypi_file(f"{_PAGE}six/1.16.0/", kind=WHEEL) as wheel:
            assert wheel.filename == "six-1.16.0-py2.py3-none-any.whl"
            assert sha256_of(wheel.path.read_bytes()) == wheel.sha256
        with fetch_pypi_file(f"{_PAGE}six/1.16.0/", kind=SDIST) as sdist:
            assert sdist.filename == "six-1.16.0.tar.gz" and sdist.size > 0
