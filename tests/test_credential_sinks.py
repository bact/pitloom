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

import base64
import http.server
import json
import logging
import os
import shutil
import stat
import subprocess
import sys
import threading
import urllib.parse
from pathlib import Path
from typing import Any, ClassVar

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.__main__ import main
from pitloom.cli.kv_output import kv_line
from pitloom.core.iri import require_namespace_iri
from pitloom.core.url_masking import (
    holds_url_credentials,
    masked_given_path,
    strip_url_secrets,
)
from pitloom.export import spdx3_json
from pitloom.extract.remote import _git_run
from pitloom.extract.remote._git_credentials import GitCredentials, split_credentials
from pitloom.extract.remote._git_redirect import _probe_url
from pitloom.extract.remote._git_run import GitRunner
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.id_registry import IdRegistry
from pitloom.id_registry._harvest import _import_sbom_element
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
    """The in-process SBOM export: numbers pass, each URL is said once, an id
    that holds a secret and every reference to it become the same new id."""
    old = f"https://u:{SECRET}@id.example/doc?token={SECRET}#P-1"
    graph: list[dict[str, Any]] = [
        {"spdxId": old, "n": 3, "d": f"https://u:{SECRET}@once.example/p"},
        {"c": [f"https://u:{SECRET}@once.example/p"], "to": [old]},
    ]
    with caplog.at_level(logging.WARNING):
        spdx3_json._strip_url_credentials(graph)  # pylint: disable=protected-access
        spdx3_json._strip_url_credentials(graph)  # pylint: disable=protected-access
    assert graph[0]["spdxId"] == "https://id.example/doc#P-1"
    assert graph[1]["to"] == [graph[0]["spdxId"]] and graph[0]["n"] == 3
    assert SECRET not in json.dumps(graph)
    said = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(said) == 2 and SECRET not in caplog.text


@pytest.mark.parametrize(
    "value",
    [
        f"alice:{SECRET}@host:o/r",
        f"alice:{SECRET}@host:/srv/r",
        f"https://h/ns?hmac={SECRET}",
    ],
    ids=["scp", "scp-absolute", "hmac"],
)
def test_a_value_stored_as_written_refuses_every_credential_shape(value: str) -> None:
    """A namespace and a registry key are refused."""
    assert holds_url_credentials(value)
    with pytest.raises(ValueError) as caught:
        require_namespace_iri(value)
    assert SECRET not in str(caught.value)
    with pytest.raises(ValueError):
        IdRegistry.new("demo", namespace="https://ids.example/ns").register(
            "ai_AIPackage", value
        )


def test_a_weak_name_is_kept_in_a_namespace_and_a_key() -> None:
    """``code``, ``session``... are accepted as written (they are often no
    secret), the same rule as in an SBOM."""
    value = "https://h/ns?code=utf8&session=2024"
    assert not holds_url_credentials(value)
    assert require_namespace_iri(value) == value


def test_a_credential_key_is_refused_by_the_generate_command_in_process(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ``-e`` refusal, in process (the subprocess test cannot count)."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x\n", encoding="utf-8")
    args = ["id", "generate", "--project-dir", str(tmp_path), "-o"]
    args += [str(tmp_path / "r.json"), "-e", f"https://u:{SECRET}@h/m:ai_AIPackage"]
    monkeypatch.setattr(sys, "argv", ["loom", *args, str(tmp_path / "src")])
    assert main() == 1
    err = capsys.readouterr().err
    assert SECRET not in err and "[credentials-unsafe/registry]" in err


@pytest.mark.parametrize(
    "text",
    ["python:3.11@sha256:deadbeef", "C:\\a@b:c", "ns:x@y"],
    ids=["image", "drive", "one-colon"],
)
def test_no_credential_is_found_in_an_image_reference_or_a_drive(text: str) -> None:
    assert not holds_url_credentials(text)
    assert masked_given_path(text) == text


def test_an_id_import_route_and_the_generate_route_refuse_alike(
    tmp_path: Path,
) -> None:
    """``-e`` is refused before anything is said about the entity."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("x\n", encoding="utf-8")
    done = subprocess.run(  # nosec B603
        [sys.executable, "-m", "pitloom", "id", "generate", "-o", "reg.json"]
        + ["-e", f"https://u:{SECRET}@h/m:ai_AIPackage", "src"],
        capture_output=True,
        check=False,
        timeout=120,
        cwd=tmp_path,
    )
    err = done.stderr.decode()
    assert done.returncode == 1 and "[credentials-unsafe/registry]" in err
    assert "stored by name" not in err and SECRET not in err
    assert not (tmp_path / "reg.json").exists()


class _Recorder(http.server.BaseHTTPRequestHandler):
    """A server that asks for Basic credentials and records what it gets."""

    seen: ClassVar[list[str | None]] = []

    def do_GET(self) -> None:  # pylint: disable=invalid-name
        self.seen.append(self.headers.get("Authorization"))
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="x"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_args: object) -> None:
        """Keep the test output quiet."""


@pytest.mark.loopback
@pytest.mark.skipif(
    shutil.which("git") is None or sys.platform == "win32", reason="needs git and sh"
)
def test_real_git_receives_the_credential_through_the_helper_unmangled() -> None:
    """Real ``git`` runs the helper: a password with ``\\``, ``$`` and a
    quote reaches the server as typed, and a stored helper is not asked."""
    _Recorder.seen.clear()
    server = http.server.HTTPServer(("127.0.0.1", 0), _Recorder)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    password = 'p\\a$b"c'
    try:
        url = f"http://us%40er:{urllib.parse.quote(password, safe='')}@127.0.0.1:"
        url += f"{server.server_port}/r.git"
        with pytest.raises(RemoteSourceError):
            GitRunner().run(["ls-remote", "--", url], "ls-remote")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
    wanted = "Basic " + base64.b64encode(f"us@er:{password}".encode()).decode()
    assert wanted in _Recorder.seen and _Recorder.seen[0] is None


@pytest.mark.parametrize(
    "text",
    [
        "https://h/s?sort_key=name&primary-key=id&country_code=TH",
        "https://h/s?code=utf8&session=2024",
    ],
)
def test_the_sbom_strip_keeps_ordinary_parameters(text: str) -> None:
    assert strip_url_secrets(text) == (text, [])
    stripped = strip_url_secrets("https://h/s?api_key=K&access-token=T")
    assert stripped[0] == "https://h/s"


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
    monkeypatch.setattr(shutil, "which", lambda _name: "git")
    runner.run(["-C", str(tmp_path), "rev-parse"], "rev-parse", echo=False)
    runner.run(["fetch", "origin"], "fetch", echo=False)
    assert seen[0] == {} and SECRET in seen[1].values()


def test_a_default_port_is_not_part_of_the_helper_origin() -> None:
    _, found = split_credentials([f"https://u:{SECRET}@h:443/r"])
    assert found is not None and found.origin == "https://h"


def test_harvest_skips_an_sbom_element_whose_key_holds_a_secret(
    caplog: pytest.LogCaptureFixture,
) -> None:
    registry = IdRegistry.new("demo", namespace="https://ids.example/ns")
    package = spdx3.ai_AIPackage()
    package.spdxId = "https://ids.example/ns#Package-1"
    package.name = f"https://u:{SECRET}@skip.example/m"
    with caplog.at_level(logging.WARNING):
        _import_sbom_element(registry, package)
    assert "skipped" in caplog.text and SECRET not in caplog.text
    assert not registry.elements
