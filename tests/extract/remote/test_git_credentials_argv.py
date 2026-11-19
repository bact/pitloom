# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""What reaches ``git`` of a Git URL holding a secret, spied on the real
command line and environment of each ``git`` process of a real fetch.

User information (``user:password@``, a token as the user) is taken out of
the arguments and handed over in the child's environment, to the calls that
contact the server only. A secret in the query or fragment (``?token=``,
``?access_token=``, ``#token=``) is never given to git at all: the page
parser and the redirect probe drop both before the clone URL is built
(``(query and fragment ignored)``), so git can neither use it nor write it
to ``.git/config``. An scp-style address is refused before git runs.

The server is on ``127.0.0.1`` (`loopback`); the secrets are fake.

See also: :mod:`tests.extract.remote.test_git_credentials_on_disk` (the
clone's files) and :mod:`tests.extract.remote.test_git_credentials` (the
split, with a stand-in ``git``).
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from pitloom.extract.remote import _git_run, fetch_git_project
from pitloom.extract.remote.errors import RemoteSourceError
from tests._git_http_server import backend_available, make_repo, serve_git

_WINDOWS = sys.platform == "win32"

pytestmark = [
    pytest.mark.platform,
    pytest.mark.loopback,
    pytest.mark.skipif(_WINDOWS, reason="git http-backend CGI server is POSIX-only"),
    pytest.mark.skipif(
        not _WINDOWS and not backend_available(), reason="needs git http-backend"
    ),
]

_SECRET = "S3CRETVALUE"
_TOKEN = "ghp_" + "a1B2" * 9

#: Each URL, ``{a}`` the server's ``127.0.0.1:<port>``; the secret it holds;
#: the variables of the helper that carry it (none: never sent).
_CASES = {
    "userinfo": (f"http://alice:{_SECRET}@{{a}}/g/p.git", _SECRET, {"PASSWORD"}),
    "token-user": (f"http://{_TOKEN}@{{a}}/g/p.git", _TOKEN, {"USER"}),
    "query-token": (f"http://{{a}}/g/p.git?token={_SECRET}", _SECRET, set()),
    "query-access-token": (
        f"http://{{a}}/g/p.git?access_token={_SECRET}",
        _SECRET,
        set(),
    ),
    "fragment-token": (f"http://{{a}}/g/p.git#token={_SECRET}", _SECRET, set()),
    "redirected-page-query": (
        f"http://{{a}}/g/p/-/tree/main?private_token={_SECRET}",
        _SECRET,
        set(),
    ),
}

_Calls = list[tuple[list[str], dict[str, str]]]


@pytest.fixture(name="calls")
def _calls(monkeypatch: pytest.MonkeyPatch) -> _Calls:
    """The command line and environment of every ``git`` process started."""
    seen: _Calls = []
    environment = _git_run._environment  # pylint: disable=protected-access
    capture = _git_run._capture  # pylint: disable=protected-access
    commands: list[list[str]] = []

    def spied_environment(*args: object, **kwargs: bool) -> dict[str, str]:
        env = environment(*args, **kwargs)  # type: ignore[arg-type]
        seen.append((commands[-1], env))
        return env

    def spied_capture(command: list[str], *args: object) -> object:
        commands.append(list(command))
        return capture(command, *args)  # type: ignore[arg-type]

    monkeypatch.setattr(_git_run, "_environment", spied_environment)
    monkeypatch.setattr(_git_run, "_capture", spied_capture)
    return seen


@pytest.fixture(name="address")
def _address(tmp_path: Path) -> Iterator[str]:
    """``127.0.0.1:<port>`` of a GitLab-like server holding ``g/p``."""
    make_repo(tmp_path / "srv", "g/p", {"main": {"a.txt": "a\n"}})
    with serve_git(tmp_path / "srv", gitlab_style=True) as base:
        yield base.removeprefix("http://")


def _holding(root: Path, secret: str) -> list[str]:
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and secret.encode() in path.read_bytes()
    )


@pytest.mark.parametrize("case", list(_CASES))
def test_a_secret_of_the_url_is_in_no_argument_and_no_file_of_the_clone(
    case: str, address: str, calls: _Calls
) -> None:
    url, secret, carriers = _CASES[case]
    with fetch_git_project(url.format(a=address)) as checkout:
        root = Path(checkout.root)
        assert (root / "a.txt").is_file() and (root / ".git" / "config").is_file()
        assert _holding(root, secret) == []
    assert calls, "no git process was spied on"
    for command, env in calls:
        assert not [arg for arg in command if secret in arg], command
        holders = {
            k.removeprefix("PITLOOM_GIT_") for k, v in env.items() if secret in v
        }
        assert holders <= carriers, holders
    servers = [env for command, env in calls if {"clone", "ls-remote"} & set(command)]
    assert all(
        {k.removeprefix("PITLOOM_GIT_") for k, v in env.items() if secret in v}
        == carriers
        for env in servers
    )


@pytest.mark.parametrize(
    "url",
    [f"oauth2:{_SECRET}@127.0.0.1:g/p.git", f"ssh://u:{_SECRET}@127.0.0.1/g/p.git"],
    ids=["scp", "ssh"],
)
def test_an_scp_or_ssh_address_starts_no_git_process_and_is_masked(
    url: str, calls: _Calls
) -> None:
    """The refusal's text masked the ``ssh://`` password but printed the
    scp-style one as given."""
    with pytest.raises(RemoteSourceError) as caught:
        with fetch_git_project(url):
            pytest.fail("fetched")  # pragma: no cover
    assert caught.value.code == "git.url-invalid"
    assert not calls and _SECRET not in str(caught.value)
