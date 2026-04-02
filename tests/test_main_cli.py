# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI main entry point behaviour."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pitloom import __main__


def test_main_uses_pretty_from_pyproject(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When --pretty is absent, main must pass pyproject pretty setting through."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    pyproject_path = project_dir / "pyproject.toml"
    pyproject_path.write_text(
        """
[project]
name = "demo"
version = "1.0.0"

[tool.pitloom]
pretty = true
""".strip()
        + "\n",
        encoding="utf-8",
    )

    output_path = project_dir / "out.spdx3.json"
    captured: dict[str, object] = {}

    def _fake_generate_sbom(
        project_dir: Path,
        output_path: Path | None = None,
        creation_info: object | None = None,
        pretty: bool | None = None,
        describe_relationship: bool | None = None,
    ) -> str:
        captured["project_dir"] = project_dir
        captured["output_path"] = output_path
        captured["creation_info"] = creation_info
        captured["pretty"] = pretty
        captured["describe_relationship"] = describe_relationship
        return "{}"

    monkeypatch.setattr(__main__, "generate_sbom", _fake_generate_sbom)
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", str(project_dir), "-o", str(output_path)],
    )

    exit_code = __main__.main()

    assert exit_code == 0
    assert captured["pretty"] is True
