# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A secret planted in a URL reaches no sink: the log formatter, a traceback,
``KEY=VALUE`` stdout, the SBOM, the ID registry and the arguments of ``git``.

See also: tests/core/url_masking (the maskers) and
tests/extract/remote/test_git_edges.py (the git runner).
"""

from __future__ import annotations

import json
import logging
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from pitloom.cli.kv_output import kv_line
from pitloom.core.iri import require_namespace_iri
from pitloom.core.url_masking import masked_given_path, strip_url_secrets
from pitloom.export import spdx3_json
from pitloom.extract.remote._git_credentials import split_credentials
from pitloom.extract.remote._git_redirect import _probe_url
from pitloom.extract.remote._git_run import GitRunner
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.id_registry import IdRegistry
from pitloom.logging_config import escape_controls, print_traceback

pytestmark = pytest.mark.platform

SECRET = "PLANTSECRET"
_SHAPES = [
    f"https://u:{SECRET}@once.example/p",
    f"https://h/p?token={SECRET}",
    f"https://h/p?code={SECRET}&session={SECRET}&ticket={SECRET}",
    f"https://h/p?token%3D={SECRET}",
    f"alice:{SECRET}@host:o/r",
]
_IDS = ["userinfo", "token", "code-session-ticket", "encoded-name", "scp-password"]


@pytest.mark.parametrize("shape", _SHAPES, ids=_IDS)
def test_every_sink_masks_a_secret_the_caller_forgot(
    shape: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """The formatter's escape, a traceback line and a ``KEY=VALUE`` value
    mask a URL whatever site wrote it (they once only escaped controls)."""
    assert SECRET not in escape_controls(f"failed on {shape}")
    assert SECRET not in kv_line(PATH=shape)
    try:
        raise ValueError(f"cannot read {shape}")
    except ValueError:
        print_traceback()
    assert SECRET not in capsys.readouterr().err


@pytest.mark.parametrize(
    "shape", _SHAPES[:2] + _SHAPES[3:4], ids=["userinfo", "token", "encoded-name"]
)
def test_the_stripped_url_keeps_what_is_not_secret(shape: str) -> None:
    plain, changed = strip_url_secrets(f"see {shape}, ok")
    assert SECRET not in plain and plain.startswith("see ") and changed
    assert SECRET not in "".join(changed)


@pytest.mark.parametrize(
    ("text", "plain"),
    [
        ("https://u:p@h/x?token=T&a=1", "https://h/x?a=1"),
        ("https://h/x?a=1&key=K", "https://h/x?a=1"),
        ("https://h/x?token=T&b=2&sig=S", "https://h/x?b=2"),
        ("https://h/x?token=T", "https://h/x"),
        ("https://h/p?x=1#frag", "https://h/p?x=1#frag"),
        ("foo @ https://u:p@h/x.whl#sig=Q", "foo @ https://h/x.whl"),
        ("https://h/p?token=T#frag", "https://h/p#frag"),
        ('{"n":"https://h/x?token=T"}', '{"n":"https://h/x"}'),
    ],
)
def test_a_secret_parameter_is_dropped_whole(text: str, plain: str) -> None:
    assert strip_url_secrets(text)[0] == plain
    assert not strip_url_secrets(plain)[1]  # idempotent, nothing to report


@pytest.mark.parametrize(
    "text",
    [
        "ssh://git@github.com/o/r.git",
        "git+ssh://git@github.com/o/r.git@main",
        "https://h/x?code=utf8&country_code=TH&session=2024",
        "https://docs.example?contact=me@x.org",
        "python:3.11@sha256:deadbeef and sip:alice@example.org:5060",
    ],
)
def test_the_sbom_strip_leaves_what_is_no_credential(text: str) -> None:
    assert strip_url_secrets(text) == (text, [])


def test_the_provenance_json_of_a_stripped_url_still_parses() -> None:
    note = json.dumps({"note": f"foo @ https://a:{SECRET}@h/x.whl?token={SECRET}"})
    plain, changed = strip_url_secrets(note)
    assert json.loads(plain) == {"note": "foo @ https://h/x.whl"} and changed
    assert SECRET not in "".join(changed)


def test_an_ordinary_path_and_address_stay_as_they_are() -> None:
    for text in ["C:\\a\\b.txt", "a@b.org: bad", "https://h:80/x", "key=value"]:
        assert masked_given_path(text, line=True) == text


def test_the_port_error_names_no_password() -> None:
    with pytest.raises(RemoteSourceError) as caught:
        _probe_url(f"https://u:{SECRET}host:99x/r")
    assert SECRET not in str(caught.value)


def _project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "pyproject.toml").write_text(
        "[project]\nname = 'demo2'\nversion = '1.0'\n"
        f"dependencies = ['foo @ https://a:{SECRET}@h.example/x.whl?"
        f"token={SECRET}']\n[project.urls]\n"
        f"Homepage = 'https://b:{SECRET}@e.example/h?api_key={SECRET}'\n",
        encoding="utf-8",
    )
    return proj


@pytest.mark.parametrize("verbose", [False, True], ids=["default", "verbose"])
def test_a_project_with_planted_secrets_writes_none_anywhere(
    tmp_path: Path, verbose: bool
) -> None:
    """The SBOM, stdout and stderr (also under ``-v``) hold no secret, and
    the removal is said once per URL, coded."""
    out = tmp_path / "out.json"
    cmd = [sys.executable, "-m", "pitloom", "generate", str(_project(tmp_path))]
    cmd += ["-o", str(out)] + (["-v"] if verbose else [])
    done = subprocess.run(  # nosec B603
        cmd, capture_output=True, check=False, timeout=120, cwd=tmp_path
    )
    assert done.returncode == 0, done.stderr
    assert SECRET not in done.stdout.decode() + done.stderr.decode()
    sbom = out.read_text(encoding="utf-8")
    assert SECRET not in sbom and "h.example/x.whl" in sbom
    err = done.stderr.decode()
    assert err.count("[credentials-unsafe]") == 2
    json.loads(sbom)


@pytest.mark.parametrize(
    "namespace",
    [f"https://u:{SECRET}@ids.example/ns", f"https://ids.example/ns?token={SECRET}"],
)
def test_a_namespace_with_a_secret_is_refused_masked(namespace: str) -> None:
    with pytest.raises(ValueError, match="carries a user name") as caught:
        require_namespace_iri(namespace)
    assert SECRET not in str(caught.value)
    assert require_namespace_iri("https://ids.example/ns") == "https://ids.example/ns"


def test_a_registry_key_with_a_secret_is_refused_and_not_stored() -> None:
    registry = IdRegistry(namespace="https://ids.example/ns")
    with pytest.raises(ValueError, match="registry key") as caught:
        registry.register("ai_AIPackage", f"https://u:{SECRET}@h/m")
    assert SECRET not in str(caught.value)
    assert not registry.elements


@pytest.mark.skipif(sys.platform == "win32", reason="a shell script stands in for git")
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


@pytest.mark.parametrize(
    "arg",
    ["https://u:p@[bad/r", "https://u:p@h:99x/r", "https://u:p@/r", "plain", "x://h/r"],
    ids=["bad-bracket", "bad-port", "no-host", "no-url", "no-userinfo"],
)
def test_an_argument_git_cannot_split_is_left_as_given(arg: str) -> None:
    assert split_credentials([arg]) == ([arg], None)


def test_a_line_break_in_a_git_password_is_not_sent_and_said(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        plain, found = split_credentials([f"https://u:a%0Ab{SECRET}@h/r"])
    assert plain == ["https://h/r"] and found is None
    assert "not sent to git" in caplog.text and SECRET not in caplog.text


def test_the_stripped_url_warning_is_said_once_per_url(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The in-process SBOM export: numbers pass, each URL is said once."""
    graph: list[dict[str, Any]] = [
        {
            "spdxId": f"https://u:{SECRET}@h/x#a",
            "n": 3,
            "d": f"https://u:{SECRET}@once.example/p",
        },
        {"c": [f"https://u:{SECRET}@once.example/p"]},
    ]
    with caplog.at_level(logging.WARNING):
        spdx3_json._strip_url_credentials(graph)  # pylint: disable=protected-access
        spdx3_json._strip_url_credentials(graph)  # pylint: disable=protected-access
    assert graph[0]["spdxId"].startswith("https://u:")
    assert graph[0]["n"] == 3 and SECRET not in json.dumps(graph[1:])
    said = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(said) == 1 and SECRET not in said[0].getMessage()
