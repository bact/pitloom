# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The order-matrix sequence (manual check ``O5``) through the CLI: an id
a `project` run retired is not minted again by the next `id generate`.

See also: test_registry_counters.py (the same rule in the library, I8).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pitloom.id_registry import FILE_TYPE
from tests.id_registry.surfaces_base import _run_cli

_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "demo"
version = "0.1"

[tool.hatch.build.targets.wheel]
packages = ["demo"]
"""


def _file_ids(registry: Path) -> dict[str, str]:
    files = json.loads(registry.read_bytes())["elements"][FILE_TYPE]
    return {name: entry["spdxId"] for name, entry in files.items()}


def test_id_generate_after_project_mints_no_retired_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`id generate`, edit ``b.py``, `project` (its document id replaces
    ``b.py``'s entry), edit ``__init__.py``, `id generate`: the new id of
    ``__init__.py`` is none the first run issued."""
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "demo" / "b.py").write_text("b = 1\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    registry = tmp_path / "reg.json"
    generate = ["id", "generate", str(tmp_path / "demo")]
    generate += ["--project-dir", str(tmp_path), "-o", str(registry)]

    assert _run_cli(monkeypatch, [*generate, "--namespace", "https://e.org/x"]) == 0
    first = _file_ids(registry)
    with open(tmp_path / "demo" / "b.py", "a", encoding="utf-8") as f:
        f.write("# edit\n")
    project = ["project", str(tmp_path), "--id-registry", str(registry)]
    project += ["-o", str(tmp_path / "p.json"), "--offline"]
    assert _run_cli(monkeypatch, project) == 0
    assert _file_ids(registry)["demo/b.py"] != first["demo/b.py"]  # retired
    with open(tmp_path / "demo" / "__init__.py", "a", encoding="utf-8") as f:
        f.write("# edit\n")
    assert _run_cli(monkeypatch, generate) == 0

    minted = _file_ids(registry)["demo/__init__.py"]
    assert minted not in first.values()
    assert minted == "https://e.org/x#File-3"
