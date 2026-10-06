# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI main entry point behaviour."""

from __future__ import annotations

import shutil
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
SAFETENSORS_FIXTURE = (
    FIXTURE_DIR / "aimodels" / "safetensors" / "whisper-tiny-random.safetensors"
)
ONNX_FIXTURE = FIXTURE_DIR / "aimodels" / "onnx" / "squeezenet1.1-7.onnx"
FRAGMENT_FIXTURE = FIXTURE_DIR / "fragments" / "dataset-fragment.spdx3.json"


def fragments_dir(tmp_path: Path) -> str:
    """A ``fragments`` directory under *tmp_path* holding one fragment."""
    fragments = tmp_path / "fragments"
    fragments.mkdir()
    shutil.copy(FRAGMENT_FIXTURE, fragments / "a.json")
    return str(fragments)


def _make_simple_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "1.0.0"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return project_dir


def effective_setting(value: object, config: object, name: str) -> object:
    """The value a library generator resolves a CLI flag to: the flag when
    given, else *config*'s own setting. The CLI passes an omitted flag as
    ``None`` and leaves this resolution to the library, so a fake standing
    in for a generator applies it to assert on the effective setting."""
    return value if value is not None else getattr(config, name)
