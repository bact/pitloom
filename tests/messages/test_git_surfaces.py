# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The Git URL refusals on every surface: ``loom project``, ``loom model``
and ``loom generate`` (a child process; one ``ERROR:`` line with the entry's
code, exit 1, nothing on standard output) and the library
(``generate_git_project_sbom``, ``generate_git_sbom``, ``generate`` and
``fetch_git_project``: a :class:`~pitloom.extract.remote.errors.RemoteSourceError`
with its ``.code`` unchanged and the entry's ``pitloom_code``, no ``WARNING:``
record). The failure is said once; a URL's credentials are never said.

The tests that fetch use a local smart-HTTP server (`loopback`).

See also: tests/messages/test_git.py (the entries),
tests/extract/remote/test_git_say_errors.py (the same errors, one by one) and
tests/extract/remote/test_git_http_e2e.py (a fetch that succeeds).
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom.assemble import generate, generate_git_project_sbom, generate_git_sbom
from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.extract.remote import _git_run
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.git import fetch_git_project
from pitloom.extract.remote.pypi import WHEEL, fetch_pypi_file
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import code_of, trusted_message
from pitloom.messages.git import (
    GIT_MISSING_LINE,
    GIT_URL_PATH_LINE,
    GIT_URL_SCHEME_LINE,
)
from pitloom.messages.network import OFFLINE_LINE
from tests._git_http_server import serve_git
from tests._git_say_repos import SERVER_MARKS, build_repos
from tests._loom_child import run_loom

pytestmark = pytest.mark.platform


def _needs_server(test: Callable[..., Any]) -> Callable[..., Any]:
    """Carry the marks of a test that fetches from the local server."""
    for mark in SERVER_MARKS:
        test = mark(test)
    return test


_SSH = "ssh://h.example/r.git"
_SCP = "u:s3cret@h.example:o/r.git"
_AT = ["--creation-datetime", "2026-01-01T00:00:00Z"]


@pytest.fixture(name="served", scope="module")
def _served(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    root = tmp_path_factory.mktemp("srv")
    build_repos(root)
    with serve_git(root, gitlab_style=True) as base:
        yield base


# -- the command line ---------------------------------------------------------------

#: The refusals made before anything is fetched: nothing else is said.
_BEFORE_ANY_FETCH = {"git-url-invalid", "offline-unusable"}

#: Each refusal: a URL (``{base}`` the local server), what to add to the
#: command, the code, and the line (or its start and end, for git's own text).
_REFUSALS = [
    pytest.param(
        (_SSH, [], "git-url-invalid", GIT_URL_SCHEME_LINE.render({"url": _SSH})),
        id="url-invalid",
    ),
    pytest.param(
        (
            "https://example.org/g/p",
            ["--offline"],
            "offline-unusable",
            OFFLINE_LINE.render({"url": "https://example.org/g/p"}),
        ),
        id="offline",
    ),
    pytest.param(
        (
            "{base}/g/p.git/-/tree/nope/x",
            [],
            "git-ref-not-found",
            "URL={base}/g/p.git: no branch or tag nope;",
        ),
        marks=SERVER_MARKS,
        id="ref-not-found",
    ),
    pytest.param(
        (
            "{base}/g/missing.git",
            [],
            "git-repository-unusable",
            "git clone: fatal: repository ",
        ),
        marks=SERVER_MARKS,
        id="repository-unusable",
    ),
]


@pytest.mark.parametrize("command", ["project", "model", "generate"])
@pytest.mark.parametrize("refusal", _REFUSALS)
def test_each_command_says_a_refusal_in_one_coded_line(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    command: str,
    refusal: tuple[str, list[str], str, str],
) -> None:
    url, extra, code, text = refusal
    base = request.getfixturevalue("served") if "{base}" in url else ""
    done = run_loom(
        [command, url.format(base=base), "-o", str(tmp_path / "o.json"), *extra],
        tmp_path,
    )
    lines = done.stderr.decode("utf-8").splitlines()
    assert done.returncode == 1 and done.stdout == b"", lines
    # The failure is said once: no relayed WARNING, one ERROR (a fetch that
    # got as far as git said INFO lines before it).
    assert [ln for ln in lines if not ln.startswith(("INFO: ", "ERROR: "))] == []
    (line,) = [ln for ln in lines if ln.startswith("ERROR: ")]
    assert lines == [line] or code not in _BEFORE_ANY_FETCH, lines
    prefix = f"ERROR: loom {command}: "
    assert line.startswith(prefix) and line.endswith(f" [{code}]"), line
    assert text.format(base=base) in line
    found = trusted_message(line)
    assert found is not None and found.code == code
    assert not (tmp_path / "o.json").exists()


@_needs_server
def test_a_missing_git_is_said_on_the_command_line(
    served: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(_git_run, "_which", lambda name: None)
    argv = ["loom", "project", served + "/g/p.git", "-o", str(tmp_path / "o.json")]
    monkeypatch.setattr(sys, "argv", argv)
    assert __main__.main() == 1
    (line,) = capsys.readouterr().err.splitlines()
    expected = f"ERROR: loom project: {GIT_MISSING_LINE.template} [git-missing]"
    assert line == expected
    assert trusted_message(line) is not None


# -- the library -----------------------------------------------------------------------


def _via_fetch(url: str) -> None:
    with fetch_git_project(url):
        pytest.fail("not fetched")


_ENTRY_POINTS: list[Callable[[str], Any]] = [
    generate_git_project_sbom,
    generate_git_sbom,
    generate,
    _via_fetch,
]
_ENTRY_IDS = ["project", "git-sbom", "generate", "fetch"]


@pytest.mark.parametrize("call", _ENTRY_POINTS, ids=_ENTRY_IDS)
@pytest.mark.parametrize(
    ("url", "tail"),
    [
        (_SSH, GIT_URL_SCHEME_LINE.template.split(": ", 1)[1]),
        (
            "https://h.example/g/p/-/tree/main/..",
            GIT_URL_PATH_LINE.template.split(": ", 1)[1],
        ),
    ],
    ids=["scheme", "path"],
)
def test_the_library_raises_the_error_it_always_did_with_its_code(
    caplog: pytest.LogCaptureFixture,
    call: Callable[[str], Any],
    url: str,
    tail: str,
) -> None:
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="pitloom"):
        with pytest.raises(RemoteSourceError) as raised:
            call(url)
    assert raised.value.code == "git.url-invalid"
    assert getattr(raised.value, CODE_ATTR) == "git-url-invalid"
    assert str(raised.value) == f"URL={url}: {tail}"
    assert "\n" not in str(raised.value)
    # the failure is raised, not also logged as a WARNING
    assert [r.levelname for r in caplog.records if r.levelno >= logging.WARNING] == []


@pytest.mark.parametrize(
    "segment",
    ["..", "%2F..", "a%00b", ".git/x", "a%5Cb", "a\\b", "%2e%2e"],
    ids=[
        "dots",
        "encoded-slash",
        "nul",
        "dot-git",
        "backslash",
        "raw-backslash",
        "enc",
    ],
)
def test_a_path_part_that_leaves_the_checkout_is_the_path_line(segment: str) -> None:
    url = f"https://h.example/g/p/-/tree/main/{segment}"
    with pytest.raises(RemoteSourceError) as raised:
        generate_git_project_sbom(url)
    assert raised.value.code == "git.url-invalid"
    assert str(raised.value).endswith(GIT_URL_PATH_LINE.template.split(": ", 1)[1])
    assert code_of(raised.value) == "git-url-invalid"


@pytest.mark.parametrize(
    "url",
    [
        "https://u:s3cret@h.example:abc/x",
        "https://u:s3cret@h.example:99999999/x",
        _SCP,
        "ssh://u:s3cret@h.example/r.git",
    ],
    ids=["port", "big-port", "scp", "ssh-user"],
)
@pytest.mark.parametrize("call", _ENTRY_POINTS, ids=_ENTRY_IDS)
def test_a_password_in_a_refused_url_is_never_said(
    caplog: pytest.LogCaptureFixture, call: Callable[[str], Any], url: str
) -> None:
    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        with pytest.raises((RemoteSourceError, ValueError, OSError)) as raised:
            call(url)
    assert "s3cret" not in str(raised.value) and "s3cret" not in caplog.text


@pytest.mark.parametrize(
    ("page", "code", "git_code"),
    [
        ("/g/p.git/-/tree/nope/x", "git-ref-not-found", "git.ref-not-found"),
        ("/g/missing.git", "git-repository-unusable", "git.clone-failed"),
        ("/g/empty.git", "git-repository-unusable/empty", "git.clone-failed"),
    ],
    ids=["ref", "unusable", "empty"],
)
@pytest.mark.parametrize("call", _ENTRY_POINTS, ids=_ENTRY_IDS)
@_needs_server
def test_a_fetch_failure_keeps_its_code_and_adds_the_entrys(
    served: str,
    caplog: pytest.LogCaptureFixture,
    call: Callable[[str], Any],
    page: str,
    code: str,
    git_code: str,
) -> None:
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="pitloom"):
        with pytest.raises(RemoteSourceError) as raised:
            call(served + page)
    assert raised.value.code == git_code
    assert getattr(raised.value, CODE_ATTR) == code
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []
    line = f"ERROR: {raised.value} [{code}]"
    assert trusted_message(line) is not None


@_needs_server
def test_a_missing_git_is_git_missing_in_the_library(
    served: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_git_run, "_which", lambda name: None)
    with pytest.raises(RemoteSourceError) as raised:
        generate_git_project_sbom(served + "/g/p.git")
    assert raised.value.code == "git.not-found"
    assert getattr(raised.value, CODE_ATTR) == "git-missing"


# -- PyPI: the same relays are gone ------------------------------------------


def test_a_pypi_refusal_is_raised_and_not_also_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Offline, and a URL the caller's check refuses: no ``WARNING:`` of the
    same text next to the error."""
    url = "https://pypi.org/project/demo/1.0/"

    def refuse(_url: str) -> None:
        raise RemoteSourceError("test.refused", "refused")

    for policy, code in (
        (RemoteFetchPolicy(offline=True), "pypi.offline"),
        (RemoteFetchPolicy(check_url=refuse), "test.refused"),
    ):
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="pitloom"):
            with pytest.raises(RemoteSourceError) as raised:
                with fetch_pypi_file(url, kind=WHEEL, policy=policy):
                    pytest.fail("not fetched")
        assert raised.value.code == code
        assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


# -- determinism ---------------------------------------------------------------


@_needs_server
def test_the_sbom_of_a_url_is_the_same_bytes_on_every_run(
    served: str, tmp_path: Path
) -> None:
    """Only the messages changed: one URL, one creation time, one document."""
    url = served + "/g/p.git/-/tree/main/svc/a"
    outs = []
    for name in ("a.json", "b.json"):
        done = run_loom(["project", url, "-o", str(tmp_path / name), *_AT], tmp_path)
        assert done.returncode == 0, done.stderr.decode("utf-8")
        outs.append((tmp_path / name).read_bytes())
    assert outs[0] == outs[1] and b"svc-a" in outs[0]
