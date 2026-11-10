# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""A Git URL's temporary checkout that cannot be fully removed (a file still
held open on Windows) is one ``WARNING:``, not a failure: the library returns
and writes its SBOM, ``loom project <url>`` exits 0 and writes it, as the PyPI
route does. A normal run leaves no checkout behind.

The real fetch runs against a local smart-HTTP server (``loopback``); only
the removal is made to fail.

See also: tests/core/test_temp_dirs.py (the directory itself),
tests/extract/remote/test_pypi_fetch.py (the PyPI route's leftover).
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble import generate_git_project_sbom
from pitloom.core.creation import CreationMetadata
from pitloom.core.url_masking import CHECKOUT_DIR_PREFIX, CHECKOUT_PLACEHOLDER
from tests._git_http_server import backend_available, make_repo, serve_git
from tests._held_open import hold_open
from tests.build_and_read_shared import use_sys_tmp

#: The stand-in server runs ``git http-backend`` as a POSIX CGI program.
_WINDOWS = sys.platform == "win32"

pytestmark = [
    pytest.mark.loopback,
    pytest.mark.skipif(_WINDOWS, reason="git http-backend CGI server is POSIX-only"),
    pytest.mark.skipif(
        not _WINDOWS and not backend_available(), reason="needs git http-backend"
    ),
]

_DEMO = '[project]\nname = "demo"\nversion = "1.0"\n'
_WHEN = "2026-01-01T00:00:00Z"
#: The one ``WARNING:`` a checkout left behind gives.
_LEFT = (
    f"Git source: could not fully remove temporary directory "
    f"'{CHECKOUT_PLACEHOLDER}' (in the system temp directory)"
)


@pytest.fixture(name="url")
def _url(tmp_path: Path) -> Iterator[str]:
    """The URL of a repository holding one project, on a local server."""
    root = tmp_path / "srv"
    make_repo(root, "g/p", {"main": {"pyproject.toml": _DEMO}})
    with serve_git(root) as base:
        yield base + "/g/p.git"


@pytest.fixture(name="sys_tmp")
def _sys_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return use_sys_tmp(tmp_path, monkeypatch)


@pytest.fixture(name="held_open")
def _held_open(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The checkout cannot be removed (a file held open on Windows)."""
    return hold_open(monkeypatch, CHECKOUT_DIR_PREFIX)


def _checkouts(sys_tmp: Path) -> list[Path]:
    return sorted(sys_tmp.glob(f"{CHECKOUT_DIR_PREFIX}*"))


def test_the_library_writes_its_sbom_when_the_checkout_stays(
    url: str,
    sys_tmp: Path,
    held_open: list[str],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    out = tmp_path / "out.spdx3.json"
    with caplog.at_level(logging.WARNING):
        sbom = generate_git_project_sbom(
            url,
            output_path=out,
            creation_metadata=CreationMetadata(creation_datetime=_WHEN),
        )
    assert held_open  # the removal was tried, and failed
    assert out.read_text(encoding="utf-8") == sbom and '"demo"' in sbom
    assert [r.getMessage() for r in caplog.records] == [_LEFT]
    left = _checkouts(sys_tmp)
    assert len(left) == 1
    for text in (caplog.text, sbom):
        assert str(sys_tmp) not in text and CHECKOUT_DIR_PREFIX not in text


def test_loom_project_exits_0_when_the_checkout_stays(
    url: str,
    sys_tmp: Path,
    held_open: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = tmp_path / "out.spdx3.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "project", url, "-o", str(out), "--creation-datetime", _WHEN],
    )
    assert __main__.main() == 0
    err = capsys.readouterr().err
    assert held_open and len(_checkouts(sys_tmp)) == 1
    assert '"demo"' in out.read_text(encoding="utf-8")
    assert [e for e in err.splitlines() if e.startswith("WARNING: ")] == [
        f"WARNING: {_LEFT}"
    ]
    assert str(sys_tmp) not in err and CHECKOUT_DIR_PREFIX not in err


def test_a_normal_run_leaves_no_checkout(
    url: str, sys_tmp: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        generate_git_project_sbom(url)
    assert not _checkouts(sys_tmp)
    assert not caplog.records
