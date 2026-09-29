# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regression: ``embed_wheel_sbom(project_dir=...)`` with no
``pitloom_config`` reads the project's config twice -- once in
``_resolve_embed_registry`` (an early peek used only to validate a
declared ``id_registry`` before the wheel is read) and once for real in
``_generate_embed_sbom_json``. The peek read must be quiet: only the
real read's ``WARNING:`` lines should reach the log, exactly once, and
the ``Build: ... has no effect`` warning (settled before the real
project-config read) must still come first -- same order as on HEAD
before the peek read existed.

See also: :mod:`tests.assemble.test_embed_wheel_registry_once` (the
sibling "resolved once, not once per wheel" invariant this shares a
root cause with).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom.core.build_options import BuildOptions
from pitloom.embed import ConfigOverrides, embed_wheel_sbom

from .conftest import _make_dummy_wheel

_PYPROJECT_WITH_LICENSE_CONFLICT = """\
[project]
name = "demo"
version = "1.0.0"
license = "MIT"
classifiers = [
    "License :: OSI Approved :: MIT License",
]
"""


def test_embed_wheel_sbom_warns_build_first_then_one_conflict_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A PEP 639 license/classifier conflict (recoverable, warns) plus a
    stray ``--build-timeout`` given without ``--allow-build`` (also
    warns, "has no effect"): exactly one conflict ``WARNING:`` (not two,
    from a duplicate, unquiet peek read), and the Build warning first."""
    project = tmp_path / "proj"
    (project / "demo").mkdir(parents=True)
    (project / "demo" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    (project / "pyproject.toml").write_text(
        _PYPROJECT_WITH_LICENSE_CONFLICT, encoding="utf-8"
    )
    wheel_path = _make_dummy_wheel(tmp_path / "dist", "demo", "1.0.0")

    with caplog.at_level(logging.WARNING):
        embed_wheel_sbom(
            wheel_path,
            project_dir=project,
            overrides=ConfigOverrides(build_options=BuildOptions(timeout=321)),
        )

    conflict_records = [
        r for r in caplog.records if "PEP 639 transitional state" in r.message
    ]
    assert len(conflict_records) == 1

    build_records = [r for r in caplog.records if "has no effect" in r.message]
    assert len(build_records) == 1

    build_index = caplog.records.index(build_records[0])
    conflict_index = caplog.records.index(conflict_records[0])
    assert build_index < conflict_index
