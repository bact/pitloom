# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The registry summary lines: run auto-harvest's ``added N new id(s)`` /
``updated stale entries`` / ``failed to save``, and ``id generate``/``id
import``'s ``holds N id(s)``. N counts distinct ids, not keys (D4).

See also: tests/core/generator/test_generator_registry_sync.py (auto-sync
through the generators), test_registry_harvest.py (the ``harvest()``
return these lines report).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble._generators_shared import _sync_registry
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.id_registry import FILE_TYPE, IdRegistry, RegistryEntry
from tests.id_registry.surfaces_base import _run_cli
from tests.registry_helpers import make_registry

_NS = "https://spdx.org/spdxdocs/x-1"
_CI = spdx3.CreationInfo(
    specVersion="3.0.1", created=datetime(2026, 1, 1, tzinfo=timezone.utc)
)


def _exporter(*files: tuple[str, str, str]) -> Spdx3JsonExporter:
    """An exporter holding one hashed file per ``(name, spdxId, sha256)``."""
    exporter = Spdx3JsonExporter()
    exporter.add_creation_info(_CI)
    for name, spdx_id, sha256 in files:
        exporter.add_file(
            spdx3.software_File(
                spdxId=spdx_id,
                name=name,
                creationInfo=_CI,
                verifiedUsing=[
                    spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue=sha256)
                ],
            )
        )
    return exporter


def _infos(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.INFO and r.getMessage().startswith("ID registry: ")
    ]


def test_added_counts_distinct_ids(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A src-layout alias pair is two keys and one id."""
    path = tmp_path / "reg.json"
    registry = IdRegistry.new("x", path=path)
    exporter = _exporter(
        ("src/p/a.py", f"{_NS}#File-1", "a" * 64),
        ("p/a.py", f"{_NS}#File-1", "a" * 64),
        ("p/b.py", f"{_NS}#File-2", "b" * 64),
    )

    with caplog.at_level(logging.INFO, logger="pitloom"):
        _sync_registry(exporter, registry, True)

    assert len(registry.elements) == 3  # non-vacuous: three keys
    assert _infos(caplog) == [f"ID registry: added 2 new id(s) to {path}"]
    assert IdRegistry.load(path).id_count() == 2


@pytest.mark.parametrize(
    ("name", "spdx_id"),
    [("new.py", f"{_NS}#File-1"), ("old.py", "urn:doc-2#File-1")],
    ids=["key-moved", "id-replaced"],
)
def test_updated_stale_entries_when_no_entry_is_new(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, name: str, spdx_id: str
) -> None:
    """A known id under a new key, or a new (per-document) id under a known
    key: an update, not an addition."""
    path = tmp_path / "reg.json"
    registry = make_registry(
        {(FILE_TYPE, "old.py"): (f"{_NS}#File-1", "a" * 64)}, path=path
    )

    with caplog.at_level(logging.INFO, logger="pitloom"):
        _sync_registry(_exporter((name, spdx_id, "b" * 64)), registry, True)

    assert registry.get(FILE_TYPE, name) == RegistryEntry(spdx_id, "b" * 64)
    assert registry.id_count() == 1
    assert _infos(caplog) == [f"ID registry: updated stale entries in {path}"]


@pytest.mark.parametrize("error", [OSError("disk full"), ValueError("drives")])
def test_a_failed_save_is_one_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, error: Exception
) -> None:
    """``ValueError`` too: a project root with no path relative to the
    registry (two Windows drives) must not break SBOM generation."""
    path = tmp_path / "reg.json"
    registry = IdRegistry.new("x", path=path)
    exporter = _exporter(("a.py", f"{_NS}#File-1", "a" * 64))

    with patch("pitloom.id_registry._format.relpath", autospec=True) as fake:
        fake.side_effect = error
        with caplog.at_level(logging.INFO, logger="pitloom"):
            _sync_registry(exporter, registry, True)

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].startswith(f"ID registry: failed to save {path}")
    assert not _infos(caplog)


_SRC_LAYOUT_TOML = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
[project]
name = "demo"
version = "1.0.0"
[tool.hatch.build.targets.wheel]
packages = ["src/demo"]
"""


def test_id_generate_reports_distinct_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A project run harvests the src-layout alias (``demo/__init__.py``
    beside ``src/demo/__init__.py``): one more key than ids."""
    project = tmp_path / "proj"
    (project / "src" / "demo").mkdir(parents=True)
    (project / "pyproject.toml").write_text(_SRC_LAYOUT_TOML, encoding="utf-8")
    (project / "src" / "demo" / "__init__.py").write_bytes(b"x = 1\n")
    registry = tmp_path / "reg.json"
    generate = ["id", "generate", str(project / "src"), "--project-dir", str(project)]
    generate += ["-o", str(registry)]
    run = ["project", str(project), "--id-registry", str(registry)]

    assert _run_cli(monkeypatch, generate) == 0
    assert _run_cli(monkeypatch, [*run, "-o", str(tmp_path / "out.json")]) == 0
    capsys.readouterr()
    assert _run_cli(monkeypatch, generate) == 0

    loaded = IdRegistry.load(registry)
    alias = loaded.get(FILE_TYPE, "demo/__init__.py")
    assert alias == loaded.get(FILE_TYPE, "src/demo/__init__.py")  # one id, two keys
    assert len(loaded.elements) == loaded.id_count() + 1
    err = capsys.readouterr().err
    assert f"INFO: ID registry: holds {loaded.id_count()} id(s)\n" in err
