# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``loom model`` on a file that is no regular file (a FIFO), and on a
folder whose only model file cannot be read: each ends with its own cause,
at once, not a hang or a "not a model".

See also: tests/cli/test_cli_model.py (the command) and
tests/core/models_wheel/test_models_wheel_unreadable.py (an unreadable
file in a project).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pitloom.__main__ import main
from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract import scanner_project
from pitloom.extract.ai_model import read_ai_model_header
from tests._model_fixtures import fixture_path
from tests.build_and_read_shared import pitloom_subprocess_env

#: ``os.mkfifo`` is POSIX only.
_NO_FIFO = sys.platform == "win32" or not hasattr(os, "mkfifo")
#: ``chmod 000`` denies nothing to root.
_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0


@pytest.mark.skipif(_NO_FIFO, reason="needs os.mkfifo")
@pytest.mark.parametrize("name", ["lone.gguf", "lone.dat"])
def test_a_fifo_named_as_a_model_is_refused_at_once(tmp_path: Path, name: str) -> None:
    """No writer ever opens it: the run ends, refusing it, instead of
    waiting on the open."""
    os.mkfifo(tmp_path / name)
    (tmp_path / "d").mkdir()
    os.mkfifo(tmp_path / "d" / "m.gguf")
    for target in (name, "d"):
        done = subprocess.run(
            [sys.executable, "-m", "pitloom", "model", target, "-o", "-"],
            capture_output=True,
            check=False,
            cwd=tmp_path,
            env=pitloom_subprocess_env(),
            timeout=15,
        )
        err = done.stderr.decode("utf-8")
        assert done.returncode != 0
        assert "[model-wrong-format]" in err, err


def _model_folder(tmp_path: Path, *names: str) -> Path:
    folder = tmp_path / "d"
    folder.mkdir()
    for name in names:
        shutil.copyfile(fixture_path(AiModelFormat.GGUF), folder / name)
    return folder


def _deny_header(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """Make the header of the file *name* unreadable, as for root too."""
    real = read_ai_model_header

    def denied(path: Path) -> bytes:
        if Path(path).name == name:
            raise PermissionError(13, "Permission denied")
        return real(path)

    monkeypatch.setattr(scanner_project, "read_ai_model_header", denied)


def _run(
    monkeypatch: pytest.MonkeyPatch, folder: Path, capsys: pytest.CaptureFixture[str]
) -> tuple[int, str, str]:
    monkeypatch.chdir(folder.parent)
    monkeypatch.setattr(sys, "argv", ["loom", "model", folder.name, "-o", "-"])
    try:
        code = main()
    except SystemExit as exc:
        code = int(exc.code or 0)
    out, err = capsys.readouterr()
    return code, out, err


def _assert_ends_unreadable(code: int, err: str) -> None:
    lines = err.splitlines()
    assert code != 0
    assert lines[-1].startswith("ERROR: ") and lines[-1].endswith("[file-unreadable]")
    assert "FILE=only.gguf: could not read header; Permission denied" in lines[-1]
    assert "model-wrong-format" not in err


def test_a_folders_only_model_unreadable_ends_with_its_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _model_folder(tmp_path, "only.gguf")
    _deny_header(monkeypatch, "only.gguf")
    code, _out, err = _run(monkeypatch, folder, capsys)
    _assert_ends_unreadable(code, err)


@pytest.mark.skipif(_ROOT or sys.platform == "win32", reason="chmod 000 denies")
def test_a_folders_only_model_without_read_permission_ends_with_its_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _model_folder(tmp_path, "only.gguf")
    (folder / "only.gguf").chmod(0)
    try:
        code, _out, err = _run(monkeypatch, folder, capsys)
    finally:
        (folder / "only.gguf").chmod(0o600)
    _assert_ends_unreadable(code, err)


def test_a_readable_model_beside_an_unreadable_one_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The readable file is the folder's model; the warning names the
    other."""
    folder = _model_folder(tmp_path, "a.gguf", "only.gguf")
    _deny_header(monkeypatch, "only.gguf")
    code, out, err = _run(monkeypatch, folder, capsys)
    assert code == 0 and '"ai_AIPackage"' in out
    warnings = [line for line in err.splitlines() if line.startswith("WARNING: ")]
    assert warnings == [
        "WARNING: FORMAT=gguf FILE=only.gguf: could not read header; "
        "Permission denied [file-unreadable]"
    ]


@pytest.mark.skipif(_NO_FIFO, reason="needs os.mkfifo")
def test_the_header_of_a_fifo_is_empty_at_once(tmp_path: Path) -> None:
    """Every reader's sniff: a FIFO is no regular file, never opened."""
    os.mkfifo(tmp_path / "m.gguf")
    code = (
        "import sys; from pathlib import Path; "
        "from pitloom.extract.ai_model import read_ai_model_header; "
        "print(read_ai_model_header(Path(sys.argv[1])))"
    )
    done = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path / "m.gguf")],
        capture_output=True,
        check=True,
        env=pitloom_subprocess_env(),
        timeout=15,
    )
    assert done.stdout.strip() == b"b''"
