# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Setuptools auto-discovery with no ``pyproject.toml``/``setup.cfg`` config:
when :func:`pitloom.core._models_wheel_setuptools.discover` lists files
from auto-discovery alone, and when it gives up (``None``).

See also: tests/core/models_wheel/test_models_wheel_setuptools.py (the
discoverer), tests/test_setuptools_default_backend_surfaces.py (parity
with a real build).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.core._models_wheel_setuptools import discover

_FOUND = {"demo/__init__.py"}


@pytest.mark.parametrize(
    ("setup_py", "pyproject", "expected"),
    [
        ('setup(name="demo")', None, _FOUND),
        ('setup(name="demo")', "", _FOUND),
        (None, '[build-system]\nrequires = ["setuptools"]\n', _FOUND),
        (None, None, None),
        ('setup(name="demo", ext_modules=[ext])', None, None),
        ('setup(name="demo", packages=["demo"])', None, None),
        ("setup(**config)", None, None),
        ("print('no setup call')", None, None),
        ("setup(", None, None),
    ],
    ids=[
        "setup-py",
        "setup-py-empty-pyproject",
        "pyproject-only",
        "nothing",
        "ext-modules",
        "packages",
        "unpacked",
        "no-call",
        "syntax-error",
    ],
)
def test_discover_auto_discovery_alone(
    tmp_path: Path,
    setup_py: str | None,
    pyproject: str | None,
    expected: set[str] | None,
) -> None:
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "__init__.py").write_text("", encoding="utf-8")
    if setup_py is not None:
        (tmp_path / "setup.py").write_text(setup_py + "\n", encoding="utf-8")
    if pyproject is not None:
        (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")

    result = discover(tmp_path)

    found = None if result is None else {f.distribution_path for f in result}
    assert found == expected
