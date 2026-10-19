# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Offline SPDX 3 schema and SHACL validation for tests.

Runs ``spdx3_validate`` in-process against the vendored model snapshot, so
the socket block in ``tests/conftest.py`` proves no download happens.
Needs the ``spdx3-validate`` build with ``model_dir`` (see the
``conformance`` dependency group in ``pyproject.toml``).

See also: tests/fixtures/spdx-model/README.md, tests/_network.py.
"""

from __future__ import annotations

import functools
from pathlib import Path

import pytest
import spdx3_validate

SPDX_MODEL_DIR = Path(__file__).parent / "fixtures" / "spdx-model"


def spdx3_errors(*sbom_files: Path) -> list[str]:
    """Return one line per schema/SHACL violation in *sbom_files* (empty: valid)."""
    result = spdx3_validate.validate(
        [str(p) for p in sbom_files], model_dir=str(SPDX_MODEL_DIR)
    )
    return [f"{e.source}: [{e.kind}] {e.message}" for e in result.errors]


def assert_spdx3_valid(*sbom_files: Path) -> None:
    """Assert every SBOM in *sbom_files* passes schema and SHACL validation."""
    errors = spdx3_errors(*sbom_files)
    assert not errors, "spdx3-validate failed:\n" + "\n".join(errors)


def use_offline_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``spdx3_validate.validate`` read the vendored model snapshot.

    Covers code that calls ``spdx3_validate.validate(...)`` itself (the
    ``fragment validate`` and ``validate-wheel`` commands).
    """
    monkeypatch.setattr(
        spdx3_validate,
        "validate",
        functools.partial(spdx3_validate.validate, model_dir=str(SPDX_MODEL_DIR)),
    )
