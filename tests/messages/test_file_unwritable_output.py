# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An SBOM write the system refuses is ``file-unwritable`` for the file as
given, on every surface: the ``-o`` file of a command, the ``output_path``
of the library, the SBOM the Hatchling hook stages. The directory is
missing (every platform) or read-only (POSIX, not root).

See also: tests/messages/test_file_unwritable_embed.py (an embed's wheel
and its ``-o`` copy).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble import generate_model_sbom, generate_project_sbom
from pitloom.messages import CodedOSError, code_of, trusted_message
from pitloom.plugins import hatch
from tests.extract.ai_model.gguf_builders import gguf_file
from tests.extract.conftest import make_hook, write_pyproject

pytestmark = pytest.mark.platform

_CODE = "file-unwritable"
# Evaluated at import on every platform: a mode is not a refusal on Windows,
# nor for root.
_READ_ONLY_DIRS = os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0
_KINDS = ["missing", "read-only"]


@pytest.fixture(name="refusing", params=_KINDS)
def _refusing(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Path]:
    """A directory the system refuses a new file in, by name: missing, or
    read-only (skipped where a mode refuses nothing)."""
    directory = tmp_path / "out"
    if request.param == "read-only":
        if not _READ_ONLY_DIRS:
            pytest.skip("needs POSIX modes, not root")
        directory.mkdir()
        directory.chmod(0o555)
    yield directory
    if directory.exists():
        directory.chmod(0o755)


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    (project / "testpkg").mkdir(parents=True)
    (project / "testpkg" / "__init__.py").write_bytes(b"")
    write_pyproject(project)
    return project


def _model(tmp_path: Path) -> Path:
    model = tmp_path / "m.gguf"
    model.write_bytes(gguf_file(0, 0))
    return model


_INPUTS: dict[str, Callable[[Path], Path]] = {"model": _model, "project": _project}


def _assert_coded(text: str, file: object) -> None:
    assert text.startswith(f"FILE={file}: could not write for the SBOM; "), text
    if text.startswith("ERROR: "):
        found = trusted_message(text)
        assert found is not None and found.code == _CODE


@pytest.mark.parametrize("command", sorted(_INPUTS))
def test_a_command_s_output_file(
    tmp_path: Path,
    refusing: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    source = _INPUTS[command](tmp_path)
    monkeypatch.chdir(tmp_path)
    target = os.path.join(refusing.name, "sbom.json")
    argv = ["loom", command, str(source), "-o", target]
    monkeypatch.setattr(sys, "argv", [*argv, "--creation-datetime", "2026-01-01"])
    assert __main__.main() == 1
    err = capsys.readouterr().err.splitlines()
    (line,) = [ln for ln in err if ln.startswith("ERROR: ")]
    prefix = f"ERROR: loom {command}: "
    assert line.startswith(prefix) and line.endswith(f" [{_CODE}]")
    assert trusted_message(line) is not None
    _assert_coded(line.removeprefix(prefix), target)


@pytest.mark.parametrize("call", sorted(_INPUTS))
def test_the_library_s_output_path(tmp_path: Path, refusing: Path, call: str) -> None:
    source = _INPUTS[call](tmp_path)
    target = refusing / "sbom.json"
    generate = generate_model_sbom if call == "model" else generate_project_sbom
    with pytest.raises(OSError) as caught:
        generate(source, output_path=target)
    assert isinstance(caught.value, CodedOSError)
    assert code_of(caught.value) == _CODE
    _assert_coded(str(caught.value), target)


def test_the_hook_s_staged_sbom(
    tmp_path: Path,
    refusing: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The staging directory refuses the SBOM: said for the staged file by
    its name, as the staged-SBOM line names it."""
    project = _project(tmp_path)
    monkeypatch.setattr(hatch, "mkdtemp", lambda **_: str(refusing))
    hook = make_hook(str(project), {})
    with pytest.raises(OSError) as caught:
        hook.initialize("standard", {})
    assert code_of(caught.value) == _CODE
    (line,) = [
        ln for ln in capsys.readouterr().err.splitlines() if ln.startswith("ERROR: ")
    ]
    prefix = "ERROR: Pitloom build hook: "
    assert line.startswith(prefix) and line.endswith(f" [{_CODE}]")
    assert trusted_message(line) is not None
    _assert_coded(line.removeprefix(prefix), "testpkg-0.1.0.spdx3.json")
