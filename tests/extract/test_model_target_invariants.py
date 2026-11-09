# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model target without its model file is a programming error, not a
user error.

See also: test_model_target.py (the resolver).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.core.internal_error import InternalError
from pitloom.extract import model_target


def test_a_model_target_without_a_model_is_an_internal_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        model_target,
        "resolve_sbom_target",
        lambda *_a, **_k: model_target.SbomTarget(
            kind=model_target.MODEL, folder=tmp_path, model=None
        ),
    )
    with pytest.raises(InternalError):
        model_target.resolve_model_file(tmp_path, subject="x")
