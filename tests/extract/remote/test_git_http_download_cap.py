# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""``max-download-bytes`` on a Git URL from end to end: a local server over
smart HTTP (``git http-backend``) holds a repository larger than the cap,
and the library, ``generate()`` and ``loom project`` stop the fetch with
``git.too-large`` (``over-cap``), naming the setting.

See also: tests/extract/remote/test_git_http_e2e.py (the same server) and
tests/cli/test_cli_git_url_download_cap.py (the CLI cascade).
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble import generate, generate_git_project_sbom
from pitloom.extract.remote import RemoteSourceError
from pitloom.messages.files import (
    OVER_CAP,
)
from tests._git_http_server import backend_available, make_repo, serve_git

_WINDOWS = sys.platform == "win32"

pytestmark = [
    pytest.mark.loopback,
    pytest.mark.skipif(_WINDOWS, reason="git http-backend CGI server is POSIX-only"),
    pytest.mark.skipif(
        not _WINDOWS and not backend_available(), reason="needs git http-backend"
    ),
]

_CAP = 4096
_STOPPED = (
    f"the repository is larger than the {_CAP}-byte max-download-bytes cap; "
    "git clone was stopped"
)


@pytest.fixture(name="url")
def _url(tmp_path: Path) -> Iterator[str]:
    """A project with a 256 KiB file: larger than :data:`_CAP`, far smaller
    than the default."""
    root = tmp_path / "srv"
    files: dict[str, str | bytes] = {
        "pyproject.toml": '[project]\nname = "demo"\nversion = "1.0"\n',
        # Not compressible, so the checkout's disk use passes the cap.
        "data.bin": bytes(range(256)) * 1024,
    }
    make_repo(root, "g/big", {"main": files})
    with serve_git(root) as base:
        yield f"{base}/g/big.git"


@pytest.mark.parametrize(
    "call",
    [generate_git_project_sbom, generate],
    ids=["generate_git_project_sbom", "generate"],
)
def test_the_library_stops_a_fetch_over_the_cap(
    url: str, call: Callable[..., str]
) -> None:
    with pytest.raises(RemoteSourceError) as caught:
        call(url, max_download_bytes=_CAP)
    assert caught.value.code == "git.too-large"
    assert getattr(caught.value, "pitloom_code", None) == OVER_CAP.code
    assert _STOPPED in str(caught.value)


def test_the_default_cap_lets_a_small_repository_through(url: str) -> None:
    assert '"demo"' in generate_git_project_sbom(url)


@pytest.mark.parametrize("by_config", [False, True], ids=["flag", "config"])
def test_loom_project_stops_a_fetch_over_the_cap(
    url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    by_config: bool,
) -> None:
    if by_config:
        config = tmp_path / "pitloom.toml"
        config.write_text(f"[tool.pitloom]\nmax-download-bytes = {_CAP}\n", "utf-8")
        given = ["--config", str(config)]
    else:
        given = ["--max-download-bytes", str(_CAP)]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["loom", "project", url, *given])
    assert __main__.main() == 1
    err = capsys.readouterr().err
    (line,) = [ln for ln in err.splitlines() if ln.startswith("ERROR:")]
    assert _STOPPED in line and line.endswith(f"[{OVER_CAP.code}]")
    assert not list(tmp_path.glob("*.spdx3.json"))
