# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""End-to-end integration tests for the installed-metadata source: through
:func:`pitloom.extract.project.read_project`,
:func:`pitloom.extract.project.resolve_project_with_lockfile`, and
:func:`pitloom.assemble.generate_project_sbom` (full G2 conflict
Annotation assembly).

See also: test_installed.py (discovery/parsing unit tests) and
test_installed_reconcile.py (reconciliation unit tests) -- this module
covers only the fixture-dir/tmp_path end-to-end wiring: sdist targets,
``include_installed_metadata=False`` (embed-wheel's own leakage guard),
peek/reread warning dedup, and full-document determinism.
"""

from __future__ import annotations

import io
import json
import logging
import tarfile
from pathlib import Path
from unittest import mock

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.core.creation import CreationMetadata
from pitloom.extract.project import read_project, resolve_project_with_lockfile

_FIXTURES = Path(__file__).parents[2] / "fixtures" / "projects"


def test_read_project_name_mismatch_rejected_entirely(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Case 1: a name-mismatched in-tree candidate is rejected entirely,
    not even used for gap-fill; field_conflicts stays empty; one WARNING;
    metadata is otherwise identical to what static-only resolution would
    have produced."""
    fixture = _FIXTURES / "installed-metadata-name-mismatch"

    with caplog.at_level(logging.WARNING):
        metadata, _cfg, _path = read_project(fixture)
    with_egg_info_warnings = caplog.text

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        static_only, _cfg2, _path2 = read_project(
            fixture, include_installed_metadata=False
        )

    assert metadata.name == "sampleproject-installed-realname"
    assert metadata.version == "1.0.0"
    assert metadata.field_conflicts == {}
    assert metadata.version == static_only.version
    assert metadata.description == static_only.description
    assert "does not match the resolved project name" in with_egg_info_warnings


def test_read_project_version_conflict_recorded(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Case 2/8: a genuine version *and* requires_python conflict --
    static wins both, both recorded, one WARNING per field."""
    fixture = _FIXTURES / "installed-metadata-conflict"

    with caplog.at_level(logging.WARNING):
        metadata, _cfg, _path = read_project(fixture)

    assert metadata.version == "1.0.0"
    assert metadata.requires_python == ">=3.10"
    version_conflict = metadata.field_conflicts["version"]
    assert [c["value"] for c in version_conflict] == ["1.0.0", "1.0.1"]
    assert {c["role"] for c in version_conflict} == {"declared"}
    assert "requires_python" in metadata.field_conflicts
    assert caplog.text.count("disagrees on version") == 1
    assert caplog.text.count("disagrees on requires_python") == 1


def test_read_project_pep440_equivalent_no_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Case 3/9: PEP 440-equivalent version and spec-equivalent
    requires_python -- zero conflicts, no WARNING; static's own
    description/keywords win unconditionally (gap-fill-only fields, both
    declared)."""
    fixture = _FIXTURES / "installed-metadata-agree"

    with caplog.at_level(logging.WARNING):
        metadata, _cfg, _path = read_project(fixture)

    assert metadata.field_conflicts == {}
    assert "disagrees on" not in caplog.text
    assert metadata.description == "Static description, always wins over Summary."
    assert metadata.keywords == ["static-keyword"]


def test_read_project_installed_marker_read_exactly_once() -> None:
    """The winning candidate's marker file is read from disk once per
    read_project() call: discovery's parse (kept on the winning _Candidate)
    is reused for reconciliation."""
    fixture = _FIXTURES / "installed-metadata-conflict"
    marker_path = next(fixture.glob("*.egg-info/PKG-INFO"))
    original_read_bytes = Path.read_bytes
    read_count = 0

    def counting_read_bytes(self: Path) -> bytes:
        nonlocal read_count
        if self == marker_path:
            read_count += 1
        return original_read_bytes(self)

    with mock.patch.object(Path, "read_bytes", counting_read_bytes):
        metadata, _cfg, _path = read_project(fixture)

    assert metadata.field_conflicts
    assert read_count == 1


def test_read_project_dynamic_version_gap_fill() -> None:
    """Case 4: dynamic = ["version"] with no statically-resolvable value
    -- gap-filled from the in-tree egg-info, no conflict recorded."""
    fixture = _FIXTURES / "installed-metadata-dynamic-gap-fill"

    metadata, _cfg, _path = read_project(fixture)

    assert metadata.version == "2.5.0"
    assert "egg-info" in metadata.provenance["version"]
    assert metadata.field_conflicts == {}


def test_read_project_missing_marker_warns_and_is_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Case 13: .egg-info exists with no PKG-INFO -- its own distinct
    WARNING, candidate skipped, no crash."""
    fixture = _FIXTURES / "installed-metadata-missing-marker"

    with caplog.at_level(logging.WARNING):
        metadata, _cfg, _path = read_project(fixture)

    assert metadata.version == "1.0.0"
    assert metadata.field_conflicts == {}
    assert "exists but has no 'PKG-INFO'" in caplog.text


def test_read_project_include_installed_metadata_false_prevents_leakage(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Case 14, flag mechanism only: with include_installed_metadata=False,
    read_project() never looks at an in-tree conflicting egg-info. A
    unit-level check of the flag; the end-to-end embed-wheel check is
    tests/assemble/test_embed_core.py::
    test_embed_wheel_sbom_ignores_conflicting_in_tree_egg_info."""
    fixture = _FIXTURES / "installed-metadata-conflict"

    with caplog.at_level(logging.WARNING):
        metadata, _cfg, _path = read_project(fixture, include_installed_metadata=False)

    assert metadata.version == "1.0.0"
    assert metadata.field_conflicts == {}
    assert "disagrees on" not in caplog.text
    assert "egg-info" not in caplog.text


def test_read_project_sdist_target_no_installed_metadata(tmp_path: Path) -> None:
    """Case 17: an sdist archive target never reaches the installed-
    metadata integration point at all (the early sdist branch returns
    first) -- field_conflicts stays empty, no crash."""
    sdist_path = tmp_path / "demo-1.0.0.tar.gz"
    pkg_info = b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0.0\n"
    with tarfile.open(sdist_path, "w:gz") as tf:
        ti = tarfile.TarInfo(name="demo-1.0.0/PKG-INFO")
        ti.size = len(pkg_info)
        tf.addfile(ti, io.BytesIO(pkg_info))

    metadata, _cfg, _path = read_project(sdist_path)

    assert metadata.name == "demo"
    assert metadata.field_conflicts == {}


def test_resolve_project_with_lockfile_peek_reread_single_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Case 15: with `[tool.pitloom] use-lockfile = true` and no explicit
    --use-lockfile (so resolve_project_with_lockfile peeks then
    re-reads), an installed-metadata conflict must be warned about
    exactly once across the whole call, not twice."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "pkg"\nversion = "1.0.0"\n'
        "[tool.pitloom]\nuse-lockfile = true\n",
        encoding="utf-8",
    )
    egg_info = tmp_path / "pkg.egg-info"
    egg_info.mkdir()
    (egg_info / "PKG-INFO").write_text("Name: pkg\nVersion: 1.0.1\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        metadata, _cfg, _path = resolve_project_with_lockfile(tmp_path, None)

    assert metadata.version == "1.0.0"
    assert "version" in metadata.field_conflicts
    assert caplog.text.count("disagrees on version") == 1


def test_generate_project_sbom_field_conflict_byte_identical_across_runs() -> None:
    """Case 16: determinism -- two independent full-document generations
    from the same conflicting input produce byte-identical output,
    including the G2 conflict Annotation's fixed [static, installed]
    candidate order."""
    fixture = _FIXTURES / "installed-metadata-conflict"
    creation_metadata = CreationMetadata(creation_datetime="2026-01-01T00:00:00Z")

    sbom_json_1 = generate_project_sbom(fixture, creation_metadata=creation_metadata)
    sbom_json_2 = generate_project_sbom(fixture, creation_metadata=creation_metadata)

    assert sbom_json_1 == sbom_json_2

    graph = json.loads(sbom_json_1)["@graph"]
    main_package = next(
        e
        for e in graph
        if e.get("type") == "software_Package"
        and e["name"] == "sampleproject-installed-conflict"
    )
    annotations = [e for e in graph if e.get("type") == "Annotation"]
    conflict_anns = [
        a
        for a in annotations
        if a.get("subject") == main_package["spdxId"]
        and json.loads(a["statement"]).get("kind") == "conflict"
        and json.loads(a["statement"]).get("field") == "version"
    ]
    assert len(conflict_anns) == 1
    statement = json.loads(conflict_anns[0]["statement"])
    assert [c["value"] for c in statement["candidates"]] == ["1.0.0", "1.0.1"]


def test_generate_project_sbom_no_conflict_no_annotation() -> None:
    """No installed-metadata source at all -- no conflict Annotation, no
    field_conflicts entries (guards against an "always emits an
    Annotation" implementation)."""
    fixture = _FIXTURES / "installed-metadata-agree"

    sbom_json = generate_project_sbom(fixture)
    graph = json.loads(sbom_json)["@graph"]
    annotations = [e for e in graph if e.get("type") == "Annotation"]
    conflict_anns = [
        a for a in annotations if json.loads(a["statement"]).get("kind") == "conflict"
    ]
    assert conflict_anns == []
