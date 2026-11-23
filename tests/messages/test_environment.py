# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``environment-unreadable``: ``loom env`` (``generate_env_sbom``) when
pipdeptree exits with an error, cannot be started, or prints what is not
its flat ``--json`` list. One coded ``ERROR:`` line on the command line; a
coded ``RuntimeError`` for a library caller; pipdeptree's own text masked,
cut and escaped on one line.

See also: :mod:`pitloom.messages._environment` and
:mod:`pitloom.extract.env`.
"""

from __future__ import annotations

import copy
import pickle  # nosec B403
import subprocess  # nosec B404
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble import generate_env_sbom
from pitloom.core.internal_error import InternalError
from pitloom.messages import CodedRuntimeError, code_of, trusted_message
from pitloom.messages.dependencies import (
    ENVIRONMENT_UNREADABLE,
    NO_OUTPUT,
    SHAPE_PROBLEMS,
    pipdeptree_exited,
    pipdeptree_shape,
)

_CODE = ENVIRONMENT_UNREADABLE.code
_SECRET = "s3cr3t-value"


def _exits(stderr: bytes) -> Callable[..., object]:
    """A ``subprocess.run`` whose pipdeptree exits 3, printing *stderr*."""

    def run(*_: object, **__: object) -> object:
        raise subprocess.CalledProcessError(3, ["pipdeptree"], stderr=stderr)

    return run


def _raises(exc: OSError) -> Callable[..., object]:
    def run(*_: object, **__: object) -> object:
        raise exc

    return run


def _prints(stdout: bytes) -> Callable[..., object]:
    def run(*_: object, **__: object) -> object:
        return subprocess.CompletedProcess(["pipdeptree"], 0, stdout, b"")

    return run


_CASES = {
    "exited": (
        _exits(b"Traceback\nNo module named pipdeptree\n"),
        "pipdeptree exited with code 3; last output: No module named pipdeptree",
    ),
    "exited-silent": (
        _exits(b"  \n"),
        f"pipdeptree exited with code 3; last output: {NO_OUTPUT}",
    ),
    "not-run": (
        _raises(PermissionError(13, "Permission denied", "/usr/bin/python")),
        "could not run pipdeptree; Permission denied",
    ),
    "not-json": (
        _prints(b"Traceback (most recent call last)"),
        "pipdeptree output is not JSON; Expecting value: line 1 column 1 (char 0)",
    ),
    "not-a-list": (
        _prints(b"{}"),
        "pipdeptree output is not its --json list: expected a JSON list",
    ),
}


@pytest.mark.parametrize(("run", "text"), _CASES.values(), ids=_CASES.keys())
def test_the_library_raises_a_coded_runtime_error(
    monkeypatch: pytest.MonkeyPatch, run: Callable[..., object], text: str
) -> None:
    """A ``RuntimeError`` as before, now carrying the code; the line names
    no path (an ``OSError`` by what the system reports)."""
    monkeypatch.setattr("subprocess.run", run)
    with pytest.raises(RuntimeError) as caught:
        generate_env_sbom(offline=True)
    assert str(caught.value) == text
    assert code_of(caught.value) == _CODE
    assert trusted_message(f"ERROR: {text} [{_CODE}]") is not None


@pytest.mark.parametrize(("run", "text"), _CASES.values(), ids=_CASES.keys())
def test_the_command_prints_one_coded_line_and_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    run: Callable[..., object],
    text: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("subprocess.run", run)
    monkeypatch.setattr(sys, "argv", ["loom", "env", "--offline", "-o", "out.json"])

    assert __main__.main() == 1

    err = [line for line in capsys.readouterr().err.splitlines() if line]
    assert err == [f"ERROR: loom env: {text} [{_CODE}]"]
    assert trusted_message(err[0]) is not None
    assert not (tmp_path / "out.json").exists()


_HOSTILE = {
    "newline-forged-line": b"boom\nERROR: forged [config-invalid]\n",
    "ansi": b"\x1b[31mred\x1b[0m [config-invalid]",
    "url-credential": f"see https://user:{_SECRET}@h.example/x".encode(),
    "huge": b"x" * 1_000_000,
    "quotes": b'it\'s "quoted"',
    "not-utf8": b"\xff\xfe bad",
}


@pytest.mark.parametrize("stderr", _HOSTILE.values(), ids=_HOSTILE.keys())
def test_pipdeptrees_text_is_one_masked_cut_escaped_line(
    monkeypatch: pytest.MonkeyPatch, stderr: bytes
) -> None:
    """pipdeptree's stderr is third-party text: its last line only, a
    credential masked, cut, control characters escaped, and the code read
    back is ours, never one it printed."""
    monkeypatch.setattr("subprocess.run", _exits(stderr))
    with pytest.raises(RuntimeError) as caught:
        generate_env_sbom(offline=True)
    text = str(caught.value)
    line = f"ERROR: loom env: {text} [{_CODE}]"
    assert "\n" not in text and "\r" not in text and "\x1b" not in text
    assert _SECRET not in text
    assert len(text) < 1_000
    trusted = trusted_message(line)
    assert trusted is not None and trusted.code == _CODE


def test_a_credential_across_the_cut_is_masked_before_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The credential starts before character 200 and ends after it: masked
    first, so no start of it survives the cut."""
    secret = "Zq7" + "w" * 40
    stderr = ("x" * 180 + f" https://user:{secret}@h.example/x").encode()
    assert stderr.index(secret.encode()) < 200 < stderr.index(b"@h.example")
    monkeypatch.setattr("subprocess.run", _exits(stderr))
    with pytest.raises(RuntimeError) as caught:
        generate_env_sbom(offline=True)
    text = str(caught.value)
    assert "Zq7" not in text and "user:" not in text
    assert "***" in text


def test_the_error_keeps_its_class_text_and_code_through_copy_and_pickle() -> None:
    exc = pipdeptree_exited(1, "No module named pipdeptree")
    for again in (copy.copy(exc), pickle.loads(pickle.dumps(exc))):  # nosec B301
        assert isinstance(again, CodedRuntimeError)
        assert isinstance(again, RuntimeError)
        assert str(again) == str(exc) and code_of(again) == _CODE


def test_a_shape_problem_is_one_of_the_closed_table() -> None:
    assert [str(pipdeptree_shape(p)) for p in SHAPE_PROBLEMS] == [
        f"pipdeptree output is not its --json list: {p}" for p in SHAPE_PROBLEMS
    ]
    with pytest.raises(InternalError):
        pipdeptree_shape("anything else")
