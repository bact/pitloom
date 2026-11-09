# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A build-file-list entry whose real path cannot be resolved is not inside
the clone, so it is dropped rather than raised on.

See also: test_models_wheel_outside_clone.py (the drop itself).
"""

from __future__ import annotations

from pathlib import Path, PurePath
from types import SimpleNamespace

import pytest

from pitloom.core import _models_wheel_clone as clone


@pytest.mark.parametrize("error", [OSError, ValueError], ids=["os", "value"])
def test_an_entry_that_cannot_be_resolved_is_not_inside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: type[Exception]
) -> None:
    root = PurePath(tmp_path)
    assert clone._inside(str(tmp_path / "a.py"), root)  # pylint: disable=W0212

    def realpath(_path: object) -> str:
        raise error("cannot resolve")

    monkeypatch.setattr(
        clone, "os", SimpleNamespace(path=SimpleNamespace(realpath=realpath))
    )
    assert not clone._inside(str(tmp_path / "a.py"), root)  # pylint: disable=W0212
