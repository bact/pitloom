# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""The cap a Git URL's fetch gets on the command line: ``--max-download-bytes``
> ``--config``'s ``max-download-bytes`` > 512 MiB, for ``loom project``,
``loom model`` and ``loom generate`` alike, and no "has no effect" warning;
a fetch under the cap completes from a local smart-HTTP server with the
flag said nowhere, the temporary checkout named nowhere.

See also: tests/extract/remote/test_git_http_download_cap.py (the cap
stopping a real fetch) and tests/assemble/test_generate_git_url.py (the
library's cascade).
"""

from __future__ import annotations

import sys
from contextlib import AbstractContextManager
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.cli.commands import _remote
from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.core.model_extract_limit import DEFAULT_MAX_DOWNLOAD_BYTES
from pitloom.core.url_masking import CHECKOUT_DIR_PREFIX
from pitloom.extract.remote import RemoteSourceError
from tests._git_http_server import backend_available, make_repo, serve_git
from tests._model_fixtures import fixture_path

_URL = "https://example.invalid/g/p.git"


@pytest.fixture(name="caps")
def _caps(monkeypatch: pytest.MonkeyPatch) -> list[int | None]:
    """The cap each fetch is given; the fetch then fails, so nothing is read."""
    seen: list[int | None] = []

    def fetch(url: str, **kwargs: object) -> AbstractContextManager[None]:
        del url
        policy = kwargs["policy"]
        assert isinstance(policy, RemoteFetchPolicy)
        seen.append(policy.max_bytes)
        raise RemoteSourceError("git.clone-failed", "stopped by the test")

    monkeypatch.setattr(_remote, "fetch_git_project", fetch)
    return seen


#: (--max-download-bytes, the --config file's max-download-bytes) -> the cap.
_CASES = {
    "default": ((None, None), DEFAULT_MAX_DOWNLOAD_BYTES),
    "config": ((None, 1000), 1000),
    "flag-beats-config": ((2000, 1000), 2000),
    "flag": ((2000, None), 2000),
}


@pytest.mark.parametrize("case", _CASES)
@pytest.mark.parametrize("command", ["project", "model", "generate"])
def test_the_cap_cascades_to_the_fetch(
    caps: list[int | None],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    case: str,
) -> None:
    (flag, configured), expected = _CASES[case]
    argv = [command, _URL, "-o", str(tmp_path / "o.json")]
    if flag is not None:
        argv += ["--max-download-bytes", str(flag)]
    if configured is not None:
        config = tmp_path / "pitloom.toml"
        config.write_text(
            f"[tool.pitloom]\nmax-download-bytes = {configured}\n", "utf-8"
        )
        argv += ["--config", str(config)]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    assert __main__.main() == 1
    assert caps == [expected]
    assert "has no effect" not in capsys.readouterr().err


_WINDOWS = sys.platform == "win32"


@pytest.mark.loopback
@pytest.mark.skipif(_WINDOWS, reason="git http-backend CGI server is POSIX-only")
@pytest.mark.skipif(
    not _WINDOWS and not backend_available(), reason="needs git http-backend"
)
@pytest.mark.parametrize("command", ["project", "model"])
def test_a_fetch_under_the_cap_completes_and_the_flag_is_said_nowhere(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    """The fetch consumes ``--max-download-bytes``: the local read of the
    checkout is not given it, so it says no "has no effect" line against
    the checkout's temporary path."""
    model = fixture_path(AiModelFormat.KERAS)
    files: dict[str, str | bytes] = (
        {"pyproject.toml": '[project]\nname = "demo"\nversion = "1.0"\n'}
        if command == "project"
        else {model.name: model.read_bytes()}
    )
    make_repo(tmp_path / "srv", "g/r", {"main": files})
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    with serve_git(tmp_path / "srv") as base:
        argv = [command, f"{base}/g/r.git", "--max-download-bytes", "10000000"]
        monkeypatch.setattr(sys, "argv", ["loom", *argv])
        assert __main__.main() == 0
    err = capsys.readouterr().err
    assert list(work.glob("*.spdx3.json")), err
    assert "has no effect" not in err and "max-download-bytes" not in err
    # Only the echo of git's own command line names the checkout (masked).
    named = [
        ln
        for ln in err.splitlines()
        if (CHECKOUT_DIR_PREFIX in ln or "<checkout>" in ln)
        and not ln.startswith("INFO: Git source: $ ")
    ]
    assert not named, err
