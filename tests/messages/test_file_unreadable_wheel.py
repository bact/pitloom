# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A wheel of ``verify-wheel``, ``validate-wheel`` or ``embed-wheel`` that
the system refuses: an ``OSError`` that carries no code of ours is said at
the per-wheel handler as ``file-unreadable`` for the wheel (``input-not-found``
when the system says it is gone), the wheel named by its file name, the
system's words only; a coded error keeps its own line. That wheel fails
alone.

See also: :func:`pitloom.cli.commands.utils.report_wheel_failure`.
"""

from __future__ import annotations

import errno
import os
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble import embed_wheel_sbom
from pitloom.cli.commands import _embed_wheel_batch, utils, verify_wheel
from pitloom.messages import code_of, trusted_message
from pitloom.messages.files import SBOM_USE, file_unreadable_error, system_failure
from pitloom.messages.targets import input_not_found
from tests.assemble.conftest import _make_dummy_wheel

pytestmark = pytest.mark.platform

_WHEEL = "unreadable-1.0.0-py3-none-any.whl"
_COMMANDS = {
    "verify-wheel": (utils, "find_embedded_sbom"),
    "validate-wheel": (utils, "find_embedded_sbom"),
    "verify-wheel-metadata": (verify_wheel, "read_wheel_name_version_from_path"),
    "embed-wheel": (_embed_wheel_batch, "embed_wheel_sbom"),
}


def _raiser(exc: BaseException) -> Callable[..., object]:
    def raises(*_: object, **__: object) -> object:
        raise exc

    return raises


def _run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    wheels: list[Path],
) -> tuple[int, list[str]]:
    name = command.removesuffix("-metadata")
    argv = ["loom", name, *map(str, wheels)]
    if name == "verify-wheel" and command.endswith("-metadata"):
        monkeypatch.setattr(
            verify_wheel, "_locate_and_detect", lambda *_: (object(), "spdx3-jsonld")
        )
        monkeypatch.setattr(verify_wheel, "_check_location", lambda *_: True)
    monkeypatch.setattr(sys, "argv", argv)
    status = __main__.main()
    err = capsys.readouterr().err.splitlines()
    return status, [line for line in err if not line.startswith("INFO: ")]


_FAILURES = {
    "permission": (
        PermissionError(errno.EACCES, "Permission denied", f"/abs/{_WHEEL}"),
        f"FILE={_WHEEL}: could not read for the SBOM; Permission denied",
        "file-unreadable",
    ),
    "io-error": (
        OSError(errno.EIO, "Input/output error"),
        f"FILE={_WHEEL}: could not read for the SBOM; Input/output error",
        "file-unreadable",
    ),
    "gone": (
        FileNotFoundError(errno.ENOENT, "No such file", f"/abs/{_WHEEL}"),
        str(input_not_found("wheel file", _WHEEL)),
        "input-not-found",
    ),
    "gone-no-errno": (
        FileNotFoundError(f"gone /abs/{_WHEEL}"),
        str(input_not_found("wheel file", _WHEEL)),
        "input-not-found",
    ),
    "no-errno": (
        OSError(f"boom /abs/{_WHEEL}"),
        f"FILE={_WHEEL}: could not read for the SBOM; OSError",
        "file-unreadable",
    ),
    "no-errno-subclass": (
        IsADirectoryError(f"/abs/{_WHEEL}"),
        f"FILE={_WHEEL}: could not read for the SBOM; IsADirectoryError",
        "file-unreadable",
    ),
}


@pytest.mark.parametrize("command", _COMMANDS, ids=_COMMANDS)
@pytest.mark.parametrize("failure", _FAILURES.values(), ids=_FAILURES.keys())
def test_an_uncoded_os_error_is_said_coded_for_the_wheel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    failure: tuple[OSError, str, str],
) -> None:
    exc, text, code = failure
    wheel = _make_dummy_wheel(tmp_path, "unreadable", "1.0.0")
    module, name = _COMMANDS[command]
    monkeypatch.setattr(module, name, _raiser(exc))
    status, err = _run(monkeypatch, capsys, command, [wheel])
    assert status == 1
    frame = command.removesuffix("-metadata")
    assert err == [f"ERROR: loom {frame}: {text} [{code}]"]
    trusted = trusted_message(err[0])
    assert trusted is not None and trusted.code == code


@pytest.mark.parametrize("command", _COMMANDS, ids=_COMMANDS)
def test_a_coded_error_keeps_its_own_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    """An ``OSError`` that carries a code (``input-not-found`` raised by the
    reader) is not said again as another."""
    wheel = _make_dummy_wheel(tmp_path, "unreadable", "1.0.0")
    coded = input_not_found("wheel file", "elsewhere.whl")
    module, name = _COMMANDS[command]
    monkeypatch.setattr(module, name, _raiser(coded))
    status, err = _run(monkeypatch, capsys, command, [wheel])
    frame = command.removesuffix("-metadata")
    assert status == 1
    assert err == [f"ERROR: loom {frame}: {coded} [{code_of(coded)}]"]


def test_one_unreadable_wheel_of_a_batch_fails_alone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bad = _make_dummy_wheel(tmp_path / "a", "unreadable", "1.0.0")
    good = _make_dummy_wheel(tmp_path / "b", "readable", "1.0.0")
    real = embed_wheel_sbom

    def embed(wheel: Path, **kwargs: object) -> object:
        if wheel.name == bad.name:
            raise PermissionError(errno.EACCES, "Permission denied", str(wheel))
        return real(wheel, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(_embed_wheel_batch, "embed_wheel_sbom", embed)
    status, err = _run(monkeypatch, capsys, "embed-wheel", [bad, good])
    assert status == 1
    assert err[0] == (
        f"ERROR: loom embed-wheel: FILE={_WHEEL}: could not read for the "
        "SBOM; Permission denied [file-unreadable]"
    )
    assert not [line for line in err[1:] if line.startswith("ERROR: ")]


_POSIX_UNREADABLE = os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0


@pytest.mark.skipif(not _POSIX_UNREADABLE, reason="needs POSIX permissions, not root")
def test_a_wheel_without_read_permission_is_file_unreadable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The real system's refusal, no stand-in: named by file name, no path."""
    wheel = _make_dummy_wheel(tmp_path, "unreadable", "1.0.0")
    wheel.chmod(0)
    try:
        status, err = _run(monkeypatch, capsys, "verify-wheel", [wheel])
    finally:
        wheel.chmod(0o600)
    assert status == 1
    assert err == [
        f"ERROR: loom verify-wheel: FILE={_WHEEL}: could not read for the "
        "SBOM; Permission denied [file-unreadable]"
    ]
    assert str(tmp_path) not in err[0]


class _PickyError(OSError):
    """An ``OSError`` that cannot be built bare (an argument required)."""

    def __init__(self, path: str) -> None:
        super().__init__(f"refused {path}")


def test_an_os_error_with_no_description_is_said_by_its_class() -> None:
    """Never the exception's text (it quotes the path); a class that cannot
    be built bare is said as ``OSError``."""
    assert str(
        file_unreadable_error(_PickyError("/abs/x"), file="x", use=SBOM_USE)
    ) == ("FILE=x: could not read for the SBOM; OSError")
    described = PermissionError(errno.EACCES, "Permission denied", "/abs/x")
    assert system_failure(described) is described
    assert system_failure(ValueError("/abs/x")).args == ("/abs/x",)
