# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Loom's model registry-miss ``WARNING:`` lines read the one typed table:
a model name held under another type is ``registry-conflict/type``,
anything else ``registry-entry-missing``. A model declared without
``path=`` says so first.

See also: tests/core/test_loom_caller.py and tests/core/test_loom_registry.py
(loom's registry use at large).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom import loom
from pitloom._loom_caller import warn_registry_miss
from pitloom.id_registry import AI_PACKAGE_TYPE, FILE_TYPE, PACKAGE_TYPE
from pitloom.logging_config import CODE_ATTR
from tests.registry_helpers import make_registry

_NS = "https://spdx.org/spdxdocs/test-1"


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


@pytest.mark.parametrize(
    ("entries", "code"),
    [
        (
            {(PACKAGE_TYPE, "My_Model"): (f"{_NS}#Package-1", None)},
            "registry-conflict/type",
        ),
        (
            {(FILE_TYPE, "my-model"): (f"{_NS}#File-1", "0" * 64)},
            "registry-conflict/type",
        ),
        ({}, "registry-entry-missing"),
    ],
    ids=["package", "file", "absent"],
)
def test_model_miss_warning(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    entries: dict[tuple[str, str], tuple[str, str | None]],
    code: str,
) -> None:
    name = "my-model" if (FILE_TYPE, "my-model") in entries else "my_model"
    registry = make_registry(entries)

    with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
        with loom.run(tmp_path / "out.spdx3.json", id_registry=registry) as run:
            run.set_model(name)

    # Declared without path=: the no-path warning, then the name lookup's.
    no_path, warning = [w for w in _warnings(caplog) if name in w]
    assert "has no path=" in no_path
    (coded,) = [r for r in caplog.records if r.getMessage() == warning]
    assert getattr(coded, CODE_ATTR) == code
    expected = {
        "registry-conflict/type": f"ID registry: {name} is held under another type",
        "registry-entry-missing": f"ID registry: model {name} not found",
    }[code]
    assert warning == f"{expected}; minting a new spdxId"


@pytest.mark.parametrize(
    ("type_name", "word"),
    [(AI_PACKAGE_TYPE, "model"), (PACKAGE_TYPE, "entity")],
    ids=["model", "other-type"],
)
def test_changed_content_warning_names_the_element_type(
    caplog: pytest.LogCaptureFixture, type_name: str, word: str
) -> None:
    registry = make_registry({(type_name, "m"): (f"{_NS}#X-1", "0" * 64)})

    with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
        warn_registry_miss(registry, type_name, "m")

    (warning,) = _warnings(caplog)
    assert warning == (
        f"ID registry: {word} m: its SHA-256 no longer matches the entry; "
        "minting a new spdxId"
    )
