# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A loom model whose ``path=`` gives no path key (outside the registry's
project root, or gone once hashed) is keyed by its name, with one
``INFO:`` per model per run (:data:`pitloom._loom_model.NAME_KEY_INFO`).

See also: test_loom_model.py (the model's lookup and record),
test_loom_dataset.py (the dataset's same message).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from pitloom import loom
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    Alias,
    IdRegistry,
    LookupKey,
    artifact_key,
)
from tests.registry_helpers import make_registry

_KEYED = "keyed by its name"


@pytest.fixture(name="project")
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "m.bin").write_bytes(b"in")
    (tmp_path / "out.bin").write_bytes(b"out")
    monkeypatch.chdir(root)
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: None
    )
    return root


def _infos(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if _KEYED in r.getMessage()]


def test_a_model_outside_the_root_says_so_once(
    project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = project / "reg.json"
    make_registry(path=path)
    outside = str(project.parent / "out.bin")

    with caplog.at_level(logging.INFO, logger="pitloom"):
        with loom.run(project / "out.json", id_registry=path):
            loom.set_model("m", path=outside)
            loom.set_model("m", path=outside)
            loom.set_model("n", path=outside)
            loom.set_model("m", path="m.bin")  # in the root: its path key

    assert _infos(caplog) == [
        f"ID registry: model {name} {_KEYED}: outside the project root"
        for name in ("m", "n")
    ]
    keys = {name for _, name in IdRegistry.load(path).elements}
    assert keys == {"m", "n", "m.bin"}


def test_a_model_gone_once_hashed_is_not_found(
    project: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = project / "reg.json"
    make_registry(path=path)

    def removed_first(
        registry: IdRegistry,
        *,
        path: str | os.PathLike[str] | None,
        name: str,
        alias: Alias,
    ) -> LookupKey:
        os.remove(project / "m.bin")
        return artifact_key(registry, path=path, name=name, alias=alias)

    monkeypatch.setattr("pitloom._loom_model.artifact_key", removed_first)

    with caplog.at_level(logging.INFO, logger="pitloom"):
        with loom.run(project / "out.json", id_registry=path):
            loom.set_model("m", path="m.bin")

    assert _infos(caplog) == [f"ID registry: model m {_KEYED}: not found"]
    assert IdRegistry.load(path).get(AI_PACKAGE_TYPE, "m") is not None


def test_no_registry_says_nothing(
    project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="pitloom"):
        with loom.run(project / "out.json"):
            loom.set_model("m", path=str(project.parent / "out.bin"))

    assert not _infos(caplog)
