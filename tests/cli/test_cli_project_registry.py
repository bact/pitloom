# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""CLI-level regression for the id-registry mint collision: ``loom project``
run repeatedly with an auto-harvested registry must never mint a duplicate
``spdxId``.

See also: tests/core/generator/test_generator_registry_sync.py for the same
repro at the library-API level, and tests/cli/test_cli_project.py for main()
config/pyproject behaviour generally.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.id_registry import IdRegistry

from ..conftest import _assert_no_duplicate_spdx_ids


def test_loom_project_repeated_runs_never_duplicate_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Three consecutive ``loom project`` runs against an unchanged project
    directory, with an auto-harvested registry carried over between them,
    must never mint a duplicate spdxId -- and must produce byte-identical
    output every time, since neither the project nor the registry's
    externally-visible content differs run to run."""
    project_dir = tmp_path / "proj"
    pkg_dir = project_dir / "src" / "collisiondemo"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "a.py").write_text("# a\n", encoding="utf-8")
    sub_dir = pkg_dir / "sub"
    sub_dir.mkdir()
    (sub_dir / "b.py").write_text("# b\n", encoding="utf-8")
    (project_dir / "pyproject.toml").write_text(
        '[project]\nname = "collisiondemo"\nversion = "1.0.0"\n\n'
        '[tool.hatch.build.targets.wheel]\npackages = ["src/collisiondemo"]\n',
        encoding="utf-8",
    )
    registry_path = tmp_path / "loom-ids.json"
    IdRegistry.new("collisiondemo", path=registry_path).save()
    output_path = tmp_path / "out.spdx3.json"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "project",
            str(project_dir),
            "-o",
            str(output_path),
            "--registry",
            str(registry_path),
            "--creation-datetime",
            "2026-01-01T00:00:00Z",
        ],
    )

    outputs = []
    for _ in range(3):
        assert __main__.main() == 0
        run_json = output_path.read_text(encoding="utf-8")
        _assert_no_duplicate_spdx_ids(run_json)
        outputs.append(run_json)

    registry_after_first = IdRegistry.load(registry_path)
    assert registry_after_first.files
    assert registry_after_first.entities

    assert outputs[0] == outputs[1] == outputs[2]
