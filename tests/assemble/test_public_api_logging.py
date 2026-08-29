# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regression: every public library-API entry point (``pitloom/__init__.py``'s
exported ``generate_*``/``enrich_model``) must call
:func:`pitloom.logging_config.configure_logging` before doing anything else,
so ``log.warning(...)`` output gets the same ``WARNING: `` prefix regardless
of whether Pitloom is invoked via the CLI, the Hatchling build hook, or as a
plain library import -- ``__main__.py`` and ``plugins/hatch.py`` already did
this; these were the one entry point still missing it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.assemble import (
    enrich_model,
    generate_env_sbom,
    generate_model_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)


def test_generate_project_sbom_configures_logging(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []
    monkeypatch.setattr(
        "pitloom.assemble._generators.configure_logging", lambda: calls.append(True)
    )
    with pytest.raises(FileNotFoundError):
        generate_project_sbom(tmp_path / "does-not-exist")
    assert calls == [True]


def test_generate_wheel_sbom_configures_logging(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []
    monkeypatch.setattr(
        "pitloom.assemble._generators.configure_logging", lambda: calls.append(True)
    )
    with pytest.raises(FileNotFoundError):
        generate_wheel_sbom(tmp_path / "does-not-exist.whl")
    assert calls == [True]


def test_generate_env_sbom_configures_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(
        "pitloom.assemble._generators.configure_logging", lambda: calls.append(True)
    )

    class _Sentinel(Exception):
        pass

    def _raise() -> None:
        raise _Sentinel

    monkeypatch.setattr("pitloom.assemble._generators.read_environment", _raise)
    with pytest.raises(_Sentinel):
        generate_env_sbom()
    assert calls == [True]


def test_generate_model_sbom_configures_logging(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []
    monkeypatch.setattr(
        "pitloom.assemble._model_generator.configure_logging",
        lambda: calls.append(True),
    )
    with pytest.raises(FileNotFoundError):
        generate_model_sbom(tmp_path / "does-not-exist.gguf")
    assert calls == [True]


def test_enrich_model_configures_logging(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []
    monkeypatch.setattr(
        "pitloom.assemble._model_generator.configure_logging",
        lambda: calls.append(True),
    )
    with pytest.raises(FileNotFoundError):
        enrich_model(tmp_path / "does-not-exist.gguf")
    assert calls == [True]
