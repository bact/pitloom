# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""How a Git URL's user information reaches ``git``: out of the arguments,
through Pitloom's own helper, with the user's helpers reset only when a URL
carried some; never traced, never in a representation, refused when it
cannot be split off.

See also: tests/extract/remote/test_git_credentials_real.py (real ``git``),
tests/extract/remote/test_git_credentials_runner.py (the runner's arguments
and environment) and tests/test_credential_surfaces.py (every surface).
"""

from __future__ import annotations

import logging
import stat
import sys
from pathlib import Path

import pytest

from pitloom.extract.remote import _git_run
from pitloom.extract.remote._git_credentials import GitCredentials, split_credentials
from pitloom.extract.remote._git_redirect import _probe_url
from pitloom.extract.remote._git_run import GitRunner
from pitloom.extract.remote.errors import RemoteSourceError

pytestmark = pytest.mark.platform

SECRET = "PLANTSECRET"
TOKEN = "PLANTTOKEN"

_TRACES = (
    "GIT_TRACE",
    "GIT_TRACE2",
    "GIT_TRACE2_EVENT",
    "GIT_TRACE2_PERF",
    "GIT_TRACE_CURL",
    "GIT_TRACE_CURL_NO_DATA",
    "GIT_TRACE_PACKET",
    "GIT_TRACE_SETUP",
    "GIT_TRACE_REDACT",
    "GIT_CURL_VERBOSE",
    "GIT_REDACT_COOKIES",
)


def _codes(caplog: pytest.LogCaptureFixture) -> list[str | None]:
    """The catalogued codes of the ``WARNING`` records captured."""
    return [
        getattr(r, "pitloom_code", None)
        for r in caplog.records
        if r.levelno == logging.WARNING
    ]


def test_no_trace_setting_of_the_caller_reaches_git(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A trace writes what git sends, the ``Authorization`` header with
    ``GIT_TRACE_REDACT=0``; what is not a trace stays."""
    for name in _TRACES:
        monkeypatch.setenv(name, "0" if name.endswith("REDACT") else "1")
    monkeypatch.setenv("GIT_SSL_CAINFO", "ca.pem")
    env = _git_run._environment()  # pylint: disable=protected-access
    assert not set(_TRACES) & set(env)
    assert env["GIT_SSL_CAINFO"] == "ca.pem"


@pytest.mark.parametrize(
    "name",
    [
        "GIT_SSL_NO_VERIFY",
        "GIT_SSH",
        "GIT_SSH_COMMAND",
        "GIT_SSH_VARIANT",
        "GIT_PROXY_COMMAND",
        "GIT_EXEC_PATH",
        "GIT_TEMPLATE_DIR",
        "GIT_CONFIG",
        "GIT_REDIRECT_STDIN",
        "GIT_REDIRECT_STDOUT",
        "GIT_REDIRECT_STDERR",
    ],
)
def test_a_caller_setting_that_runs_a_program_or_drops_tls_is_scrubbed(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another ``git-remote-https`` (``GIT_EXEC_PATH``), an ssh program, a
    template hook, TLS checks off or git's output moved: none reaches the
    fetch; the files naming the user's own configuration stay."""
    kept = {
        "GIT_CONFIG_GLOBAL": "g",
        "GIT_CONFIG_SYSTEM": "s",
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": "h",
    }
    for key, value in {name: "x", **kept}.items():
        monkeypatch.setenv(key, value)
    env = _git_run._environment()  # pylint: disable=protected-access
    assert name not in env
    assert {key: env.get(key) for key in kept} == kept


def test_no_representation_holds_the_credential() -> None:
    _, found = split_credentials([f"https://{TOKEN}:{SECRET}@h/r"])
    assert found is not None and SECRET in found.environment().values()
    for shown in (repr(found), repr(GitRunner(credentials=found))):
        assert SECRET not in shown and TOKEN not in shown
        assert "https://h" in shown


_USERINFO = "credentials-unsafe/git-userinfo"
_HOST = "url-unsafe/host-spelling"


@pytest.mark.parametrize(
    ("url", "code"),
    [
        (f"https://u:{SECRET}@[bad/r", _USERINFO),
        (f"https://u:{SECRET}@h:99x/r", _USERINFO),
        (f"https://u:{SECRET}@/r", _USERINFO),
        (f"https://h?x=u:{SECRET}@b/r", _USERINFO),
        (f"https://u:{SECRET}@h?q@x/r", _USERINFO),
        (f"https://u:a%00{SECRET}@h/r", _USERINFO),
        (f"https://u%00{TOKEN}:{SECRET}@h/r", _USERINFO),
        (f"https://u:{SECRET}@a=b/r", _HOST),
        (f"https://u:{SECRET}@-oProxyCommand=x/r", _HOST),
        (f"https://u:{SECRET}@!cmd/r", _HOST),
        (f"https://u:{SECRET}@a%20b/r", _HOST),
        (f"https://u:{SECRET}@[v1.evil.com]/r", _HOST),
        (f"https://u:{SECRET}@[v1.x]:8443/r", _HOST),
        (f"https://u:{SECRET}@[fe80::1%25eth0]/r", _HOST),
    ],
    ids=[
        "bad-ipv6",
        "bad-port",
        "no-host",
        "query-at",
        "two-at",
        "nul-password",
        "nul-user",
        "host-equals",
        "host-option",
        "host-bang",
        "host-space",
        "bracketed-name",
        "ipvfuture-port",
        "zone-id",
    ],
)
def test_a_url_whose_userinfo_cannot_be_split_off_is_refused_masked(
    url: str, code: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Git reads user information up to an ``@`` before the first ``/``;
    a URL Python cannot split the same way never reaches git, nor does a
    NUL (no environment variable holds one: ``Popen`` raised a bare
    ``ValueError``); a host whose ``=`` would end the helper's ``-c`` key
    early, or no host name spells, is refused for its spelling."""

    def started(*_args: object) -> tuple[int, str, str]:
        raise AssertionError("git started")

    monkeypatch.setattr(_git_run, "_capture", started)
    monkeypatch.setattr(_git_run, "_which", lambda _name: "git")
    with pytest.raises(RemoteSourceError) as caught:
        GitRunner().run(["ls-remote", "--", url], "ls-remote", echo=False)
    assert caught.value.code == "git.url-invalid"
    assert caught.value.pitloom_code == code
    assert SECRET not in str(caught.value) and TOKEN not in str(caught.value)
    assert ("the host is not plain ASCII" in str(caught.value)) == (code == _HOST)


@pytest.mark.parametrize(
    "url",
    ["https://h/r?x=a@b", "https://h/a@b/r", "x://h/r", "plain@thing"],
    ids=["query-after-path", "path", "no-userinfo", "no-url"],
)
def test_an_at_sign_git_reads_as_no_userinfo_is_left_as_given(url: str) -> None:
    assert split_credentials([url]) == ([url], None)


@pytest.mark.parametrize(
    ("url", "user", "password"),
    [
        (f"https://u:p#{SECRET}@h/r", "u", f"p#{SECRET}"),
        (f"https://u:p?{SECRET}@h/r", "u", f"p?{SECRET}"),
        (f"https://a@b:{SECRET}@h/r", "a@b", SECRET),
        (f"https://{SECRET}@h/r", SECRET, ""),
        (f"https://u:a%09%1B%7F{SECRET}@h/r", "u", f"a\t\x1b\x7f{SECRET}"),
    ],
    ids=["hash", "question-mark", "at-in-user", "token-as-user", "control"],
)
def test_user_information_is_split_where_git_and_the_masker_end_it(
    url: str, user: str, password: str
) -> None:
    assert split_credentials([url]) == (
        ["https://h/r"],
        GitCredentials("https://h", user, password),
    )


@pytest.mark.parametrize(
    ("urls", "user"),
    [
        (["https://first:a@h/r", "https://last:b@h/r"], "last"),
        (["https://first:a@h/r", "https://h/r"], "first"),
    ],
    ids=["last-wins", "a-plain-url-keeps-it"],
)
def test_the_credentials_are_the_last_urls_that_had_some(
    urls: list[str], user: str
) -> None:
    plain, found = split_credentials(urls)
    assert plain == ["https://h/r"] * 2
    assert found is not None and found.user == user


@pytest.mark.parametrize(
    ("url", "origin", "plain"),
    [
        ("https://u:p@[::1]:8443/r", "https://[::1]:8443", "https://[::1]:8443/r"),
        ("https://u:p@[::1]/r", "https://[::1]", "https://[::1]/r"),
        ("https://u:p@h:443/r", "https://h", "https://h/r"),
        ("http://u:p@h:80/r", "http://h", "http://h/r"),
        ("http://u:p@h:443/r", "http://h:443", "http://h:443/r"),
        ("https://u:p@h:80/r", "https://h:80", "https://h:80/r"),
        (
            "https://u:p@[::ffff:1.2.3.4]/r",
            "https://[::ffff:1.2.3.4]",
            "https://[::ffff:1.2.3.4]/r",
        ),
    ],
    ids=[
        "ipv6-port",
        "ipv6",
        "https-443",
        "http-80",
        "http-443",
        "https-80",
        "ipv4-mapped",
    ],
)
def test_the_helper_origin_is_the_one_git_matches(
    url: str, origin: str, plain: str
) -> None:
    """An IPv6 host keeps its brackets; only the scheme's own default port
    is left out."""
    args, found = split_credentials([url])
    assert args == [plain] and found == GitCredentials(origin, "u", "p")


@pytest.mark.parametrize(
    ("url", "code", "sent"),
    [
        (f"http://u:{SECRET}@clear.example/r", "credentials-unsafe/http-clear", True),
        (
            f"https://u:a%0Ab{SECRET}@break.example/r",
            "credentials-unsafe/git-line-break",
            False,
        ),
        (f"https://u:{SECRET}@quiet.example/r", None, True),
    ],
    ids=["http", "line-break", "https"],
)
def test_an_unsafe_credential_is_said_once_masked(
    url: str, code: str | None, sent: bool, caplog: pytest.LogCaptureFixture
) -> None:
    """Plain http goes on with the credential; a line break goes on without
    it; https says nothing."""
    with caplog.at_level(logging.WARNING):
        results = [split_credentials([url]) for _ in range(2)]
    plain, found = results[1]
    assert SECRET not in plain[0] and (found is not None) == sent
    assert _codes(caplog) == ([code] if code else [])
    assert SECRET not in caplog.text


def _commands(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[list[str], GitCredentials | None]]:
    """The commands and credentials each later call of ``_capture`` gets."""
    seen: list[tuple[list[str], GitCredentials | None]] = []

    def fake(
        cmd: list[str], _left: float, _cap: object, creds: GitCredentials | None
    ) -> tuple[int, str, str]:
        seen.append((cmd, creds))
        return 0, "", ""

    monkeypatch.setattr(_git_run, "_capture", fake)
    monkeypatch.setattr(_git_run, "_which", lambda _name: "git")
    return seen


@pytest.mark.parametrize(
    ("url", "reset", "helper"),
    [
        ("https://h/r", False, False),
        (f"https://u:{SECRET}@h/r", True, True),
        (f"https://u:a%0D{SECRET}@h/r", True, False),
    ],
    ids=["plain", "userinfo", "line-break"],
)
def test_the_users_helpers_are_reset_only_after_a_url_with_userinfo(
    url: str, reset: bool, helper: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plain URL is fetched as ``git clone`` would, with the user's own
    helpers; once a URL carried user information (sent or not), every call
    of the runner resets them, and only a call to the server gets Pitloom's."""
    seen = _commands(monkeypatch)
    runner = GitRunner()
    runner.run(["clone", "--", url, "d"], "clone", echo=False)
    runner.run(["-C", "d", "rev-parse", "HEAD"], "rev-parse", echo=False)
    for (cmd, _), server in zip(seen, (True, False), strict=True):
        assert "credential.interactive=false" in cmd
        assert ("credential.helper=" in cmd) == reset
        assert ("core.askPass=" in cmd) == reset
        assert any(a.startswith("credential.https://h.helper=") for a in cmd) == (
            helper and server
        )
        assert SECRET not in " ".join(cmd)
    assert (seen[0][1] is not None) == helper and seen[1][1] is None


_WINDOWS = sys.platform == "win32"


@pytest.mark.skipif(_WINDOWS, reason="a shell script stands in for git")
@pytest.mark.parametrize(
    ("url", "reset", "sent"),
    [
        (f"https://u:{SECRET}@h/r", True, True),
        ("https://h/r", False, False),
        (f"https://u:a%0A{SECRET}@h/r", True, False),
    ],
    ids=["userinfo", "plain", "line-break"],
)
def test_a_clone_gets_the_environment_its_settings_name(
    url: str,
    reset: bool,
    sent: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ask-pass programs of the caller are emptied exactly when the
    helpers are reset, and the password is in a clone's environment."""
    seen = tmp_path / "seen"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "git"
    script.write_text(
        f'#!/bin/sh\nprintf "%s\\n" "$@" > "{seen}.args"\nenv > "{seen}.env"\n',
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    monkeypatch.setenv("GIT_ASKPASS", "/bin/mine")
    monkeypatch.setenv("SSH_ASKPASS", "/bin/mine-too")
    GitRunner().run(["clone", "--", url, "d"], "clone", echo=False)
    args = Path(f"{seen}.args").read_text(encoding="utf-8").splitlines()
    env = dict(
        line.split("=", 1)
        for line in Path(f"{seen}.env").read_text(encoding="utf-8").splitlines()
        if "=" in line
    )
    assert ("credential.helper=" in args) == reset
    want = ("", "") if reset else ("/bin/mine", "/bin/mine-too")
    assert (env["GIT_ASKPASS"], env["SSH_ASKPASS"]) == want
    assert ("PITLOOM_GIT_PASSWORD" in env) == sent
    assert SECRET not in "\n".join(args)


@pytest.mark.parametrize("arg", ["plain", "x://h/r"], ids=["no-url", "no-userinfo"])
def test_an_argument_without_user_information_is_left_as_given(arg: str) -> None:
    assert split_credentials([arg]) == ([arg], None)


def test_a_line_break_in_a_git_password_is_not_sent_and_said(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        plain, found = split_credentials([f"https://u:a%0Ab{SECRET}@h/r"])
    assert plain == ["https://h/r"] and found is None
    assert "not sent to git" in caplog.text and SECRET not in caplog.text


def test_the_port_error_names_no_password() -> None:
    with pytest.raises(RemoteSourceError) as caught:
        _probe_url(f"https://u:{SECRET}host:99x/r")
    assert SECRET not in str(caught.value)
