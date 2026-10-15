# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Loom's model registry-miss ``WARNING:`` lines read the one typed table:
a model name held under another type is "different type", anything else
is untracked. A model declared without ``path=`` says so first.

See also: tests/core/test_loom_caller.py and tests/core/test_loom_registry.py
(loom's registry use at large).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom import loom
from pitloom.id_registry import FILE_TYPE, PACKAGE_TYPE
from tests.registry_helpers import make_registry

_NS = "https://spdx.org/spdxdocs/test-1"


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


@pytest.mark.parametrize(
    ("entries", "needle"),
    [
        ({(PACKAGE_TYPE, "My_Model"): (f"{_NS}#Package-1", None)}, "different type"),
        ({(FILE_TYPE, "my-model"): (f"{_NS}#File-1", "0" * 64)}, "different type"),
        ({}, "untracked entity"),
    ],
    ids=["package", "file", "absent"],
)
def test_model_miss_warning(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    entries: dict[tuple[str, str], tuple[str, str | None]],
    needle: str,
) -> None:
    name = "my-model" if (FILE_TYPE, "my-model") in entries else "my_model"
    registry = make_registry(entries)

    with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
        with loom.run(tmp_path / "out.spdx3.json", id_registry=registry) as run:
            run.set_model(name)

    # Declared without path=: the no-path warning, then the name lookup's.
    no_path, warning = [w for w in _warnings(caplog) if repr(name) in w]
    assert "has no path=" in no_path
    assert needle in warning
