# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The two confinement helpers never raise: a directory that cannot be listed
spells nothing, and a path the file system cannot resolve is not inside.

See also: test_path_confine.py (the rest of the module).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pitloom.core import path_confine


def test_a_directory_that_cannot_be_listed_spells_nothing(tmp_path: Path) -> None:
    assert not path_confine.spelled_as_on_disk(tmp_path / "missing", "a")


@pytest.mark.parametrize("error", [OSError, ValueError], ids=["os", "value"])
def test_a_path_that_cannot_be_resolved_is_not_a_regular_file_inside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: type[Exception]
) -> None:
    (tmp_path / "m.gguf").write_bytes(b"GGUF")
    assert path_confine.regular_file_inside(tmp_path, "m.gguf")

    def realpath(_path: object) -> str:
        raise error("cannot resolve")

    monkeypatch.setattr(
        path_confine, "os", SimpleNamespace(path=SimpleNamespace(realpath=realpath))
    )
    assert not path_confine.regular_file_inside(tmp_path, "m.gguf")
