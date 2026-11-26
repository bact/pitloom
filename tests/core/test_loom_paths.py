# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""How the loom SDK spells the files it names: a model's ``path=`` is opened
as the OS opens it, the run's script is named like any other source, and a
fragment or current directory the system refuses is coded.

See also: test_loom_model.py (the model's hash and registry lookup),
test_loom_caller.py (the caller's provenance).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from pitloom import loom
from pitloom.messages import code_of
from tests._symlink import CAN_SYMLINK


def _graph(output: Path) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = json.loads(output.read_text(encoding="utf-8"))[
        "@graph"
    ]
    return graph


def _has_sha256(element: dict[str, Any], data: bytes) -> bool:
    wanted = hashlib.sha256(data).hexdigest()
    return any(h["hashValue"] == wanted for h in element["verifiedUsing"])


#: Win32 collapses ``..`` in a path before it opens it, whatever a link says.
_DOTDOT_FOLLOWS_LINKS = sys.platform != "win32"


@pytest.mark.skipif(
    not (CAN_SYMLINK and _DOTDOT_FOLLOWS_LINKS),
    reason="needs a symlink and a .. that follows it (not Win32)",
)
def test_a_model_path_with_dotdot_is_opened_as_the_os_opens_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``link/..`` is the parent of what ``link`` leads to, not of the
    directory holding the link."""
    (tmp_path / "elsewhere" / "sub").mkdir(parents=True)
    (tmp_path / "work").mkdir()
    (tmp_path / "elsewhere" / "m.bin").write_bytes(b"the real weights")
    (tmp_path / "work" / "m.bin").write_bytes(b"a decoy")
    (tmp_path / "work" / "link").symlink_to(
        tmp_path / "elsewhere" / "sub", target_is_directory=True
    )
    monkeypatch.chdir(tmp_path / "work")
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: None
    )
    with loom.run(tmp_path / "out.json"):
        loom.set_model("m", path="link/../m.bin")

    (model,) = [e for e in _graph(tmp_path / "out.json") if e["type"] == "ai_AIPackage"]
    assert _has_sha256(model, b"the real weights")


def test_a_script_outside_the_current_directory_is_named_by_its_file_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No machine path in the SBOM, and the file that is hashed is still the
    script, not a file of the same name in the current directory."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "work").mkdir()
    (tmp_path / "scripts" / "train.py").write_bytes(b"the script\n")
    (tmp_path / "work" / "train.py").write_bytes(b"a decoy\n")
    monkeypatch.chdir(tmp_path / "work")
    script = str(tmp_path / "scripts" / "train.py")
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: script
    )
    (tmp_path / "work" / "m.bin").write_bytes(b"weights")
    with loom.run(tmp_path / "out.json"):
        loom.set_model("m", path="m.bin")

    (found,) = [
        e
        for e in _graph(tmp_path / "out.json")
        if e["type"] == "software_File" and e["name"] == "train.py"
    ]
    assert _has_sha256(found, b"the script\n")


#: A read-only directory mode refuses a write, and a process may remove its
#: own current directory: POSIX only.
_POSIX = sys.platform != "win32"


@pytest.mark.skipif(not _POSIX, reason="a read-only directory mode: POSIX only")
@pytest.mark.parametrize("name", ["frag.json", "sub/frag.json"], ids=["file", "dir"])
def test_a_fragment_the_system_refuses_is_file_unwritable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """The write, or the directory made for it, refused: coded, naming the
    fragment as given."""
    locked = tmp_path / "locked"
    locked.mkdir()
    monkeypatch.chdir(tmp_path)
    locked.chmod(0o555)
    try:
        if os.access(locked, os.W_OK):
            pytest.skip("the user may write a read-only directory (root)")
        with pytest.raises(OSError) as raised:
            with loom.run(f"locked/{name}"):
                loom.set_model("m")
    finally:
        locked.chmod(0o755)
    assert code_of(raised.value) == "file-unwritable"
    assert str(raised.value).startswith(
        f"FILE=locked/{name}: could not write for the SBOM fragment; "
    )


@pytest.mark.skipif(not _POSIX, reason="Windows cannot remove the cwd")
def test_a_run_in_a_removed_directory_is_refused_when_entered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Coded, before the run is active, even with an absolute output."""
    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()
    run = loom.run(tmp_path / "out.json")
    with pytest.raises(ValueError) as raised:
        run.__enter__()  # pylint: disable=unnecessary-dunder-call
    assert code_of(raised.value) == "file-unreadable"
    assert str(raised.value).startswith("DIR=.: could not read for resolving ")
    assert loom._active_run is None  # pylint: disable=protected-access
