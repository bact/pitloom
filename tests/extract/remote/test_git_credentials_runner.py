# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What :class:`pitloom.extract.remote._git_run.GitRunner` hands to ``git``:
no secret in the arguments, the credential in the environment of a server
call only, and a partial clone's checkout holding the credential.

See also: tests/extract/remote/test_git_credentials.py (the split) and
tests/extract/remote/test_git_credentials_real.py (real ``git``).
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from pitloom.extract.remote import _git_run
from pitloom.extract.remote._git_credentials import GitCredentials
from pitloom.extract.remote._git_run import GitRunner

pytestmark = pytest.mark.platform

SECRET = "PLANTSECRET"
_WINDOWS = sys.platform == "win32"


@pytest.mark.skipif(_WINDOWS, reason="a shell script stands in for git")
def test_git_gets_the_credential_by_helper_and_never_in_its_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stand-in ``git`` records its arguments and environment: no secret
    in the arguments, every helper reset first, the helper bound to the
    URL's origin alone and reading the child's environment."""
    record = tmp_path / "record"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "git"
    script.write_text(
        f'#!/bin/sh\nprintf "%s\\n" "$@" > "{record}.args"\n'
        'echo "$PITLOOM_GIT_USER:$PITLOOM_GIT_PASSWORD:[$GIT_ASKPASS]"'
        f' > "{record}.env"\n',
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    monkeypatch.setenv("GIT_ASKPASS", "/bin/evil")
    runner = GitRunner()
    runner.run(["ls-remote", "--", f"https://al%40ice:{SECRET}@h:8443/r?x=1"], "x")
    args = Path(f"{record}.args").read_text(encoding="utf-8").splitlines()
    assert SECRET not in "\n".join(args) and "https://h:8443/r?x=1" in args
    assert args.index("credential.helper=") < next(
        i for i, a in enumerate(args) if a.startswith("credential.https://h:8443.")
    )
    assert Path(f"{record}.env").read_text(encoding="utf-8") == (
        f"al@ice:{SECRET}:[]\n"
    )
    runner.run(["-C", "d", "fetch", "origin"], "x")  # a later call, no URL
    assert any(
        a.startswith("credential.https://h:8443.helper=")
        for a in Path(f"{record}.args").read_text(encoding="utf-8").splitlines()
    )
    assert os.environ["GIT_ASKPASS"] == "/bin/evil"  # the caller's is untouched


def test_the_password_is_in_the_environment_of_a_server_call_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = GitRunner()
    runner.credentials = GitCredentials("https://h", "u", SECRET)
    seen: list[dict[str, str]] = []

    def fake(
        _cmd: list[str], _left: float, _cap: object, creds: GitCredentials | None
    ) -> tuple[int, str, str]:
        seen.append(creds.environment() if creds else {})
        return 0, "", ""

    monkeypatch.setattr(_git_run, "_capture", fake)
    monkeypatch.setattr(_git_run, "_which", lambda _name: "git")
    runner.run(["-C", str(tmp_path), "rev-parse"], "rev-parse", echo=False)
    runner.run(["fetch", "origin"], "fetch", echo=False)
    assert seen[0] == {} and SECRET in seen[1].values()


def test_checkout_of_a_partial_clone_gets_the_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = GitRunner()
    runner.credentials = GitCredentials("https://h", "u", SECRET)
    seen: list[GitCredentials | None] = []

    def fake(
        _cmd: list[str], _left: float, _cap: object, creds: GitCredentials | None
    ) -> tuple[int, str, str]:
        seen.append(creds)
        return 0, "", ""

    monkeypatch.setattr(_git_run, "_capture", fake)
    monkeypatch.setattr(_git_run, "_which", lambda _name: "git")
    runner.run(["-C", str(tmp_path), "checkout", "FETCH_HEAD"], "checkout", echo=False)
    assert seen == [runner.credentials]
