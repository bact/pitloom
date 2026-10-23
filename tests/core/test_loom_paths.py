# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""How the loom SDK spells the files it names: a model's ``path=`` is opened
as the OS opens it, and the run's script is named like any other source.

See also: test_loom_model.py (the model's hash and registry lookup),
test_loom_caller.py (the caller's provenance).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pitloom import loom
from tests._symlink import CAN_SYMLINK


def _graph(output: Path) -> list[dict[str, str]]:
    graph: list[dict[str, str]] = json.loads(output.read_text(encoding="utf-8"))[
        "@graph"
    ]
    return graph


@pytest.mark.skipif(not CAN_SYMLINK, reason="needs a symlink")
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
    sha256 = hashlib.sha256(b"the real weights").hexdigest()
    assert any(h["hashValue"] == sha256 for h in model["verifiedUsing"])  # type: ignore[attr-defined]


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
    sha256 = hashlib.sha256(b"the script\n").hexdigest()
    assert any(h["hashValue"] == sha256 for h in found["verifiedUsing"])  # type: ignore[attr-defined]
