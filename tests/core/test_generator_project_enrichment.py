# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.assemble.generate_project_sbom project-level README
enrichment and license-conflict-detection (G2: declared-vs-detected
disagreement).

See also: tests/core/test_generator_project.py for basic generation,
main-package PURL, output path, creation comment/tool summary, and
createdBy creator-type handling. tests/core/test_generator_project_structure.py
for creator/tool multiplicity, sentimentdemo structure, dependency-name
parsing, fragments, setup.cfg, and preparsed-metadata tests.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from pitloom.assemble import generate_project_sbom
from pitloom.core.creation import CreationMetadata

from .conftest import _AI_MODEL_ROOT, _license_relationships


def test_generate_project_sbom_enrichment_end_to_end() -> None:
    """A discovered AI model with an adjacent README.md gap-fillable via
    YAML frontmatter, plus [tool.pitloom] enrich = true, must produce
    the same enrichment artifacts at the project level that
    generate_model_sbom's single-model path already produces -- closing
    the gap where loom project/loom generate never ran enrichment at all."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pkg_dir = tmppath / "src" / "smoke_project"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "__init__.py").write_text("")
        fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
        (pkg_dir / "model.safetensors").write_bytes(fixture.read_bytes())
        (pkg_dir / "README.md").write_text(
            "---\nlicense: apache-2.0\ndatasets:\n  - tiny-imagenet\n---\n"
        )
        (tmppath / "pyproject.toml").write_text(
            "[build-system]\n"
            'requires = ["hatchling"]\n'
            'build-backend = "hatchling.build"\n\n'
            "[project]\n"
            'name = "smoke-project"\n'
            'version = "0.1.0"\n\n'
            "[tool.hatch.build.targets.wheel]\n"
            'packages = ["src/smoke_project"]\n\n'
            "[tool.pitloom]\n"
            "enrich = true\n"
        )

        sbom_json = generate_project_sbom(tmppath)
        graph = json.loads(sbom_json)["@graph"]

        assert [e for e in graph if e.get("type") == "ai_AIPackage"]
        ds_pkgs = [e for e in graph if e.get("type") == "dataset_DatasetPackage"]
        assert len(ds_pkgs) == 1
        assert ds_pkgs[0]["name"] == "tiny-imagenet"

        annotations = [e for e in graph if e.get("type") == "Annotation"]
        enrichment_anns = [
            a
            for a in annotations
            if a.get("statement")
            and json.loads(a["statement"]).get("kind") == "enrichment"
        ]
        assert len(enrichment_anns) == 1


def test_generate_project_sbom_no_enrichment_by_default() -> None:
    """Same fixture as above but with no [tool.pitloom] enrich config:
    project-level enrichment must stay off by default, same as every
    other surface."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pkg_dir = tmppath / "src" / "smoke_project"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "__init__.py").write_text("")
        fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
        (pkg_dir / "model.safetensors").write_bytes(fixture.read_bytes())
        (pkg_dir / "README.md").write_text(
            "---\nlicense: apache-2.0\ndatasets:\n  - tiny-imagenet\n---\n"
        )
        (tmppath / "pyproject.toml").write_text(
            "[build-system]\n"
            'requires = ["hatchling"]\n'
            'build-backend = "hatchling.build"\n\n'
            "[project]\n"
            'name = "smoke-project"\n'
            'version = "0.1.0"\n\n'
            "[tool.hatch.build.targets.wheel]\n"
            'packages = ["src/smoke_project"]\n'
        )

        sbom_json = generate_project_sbom(tmppath)
        graph = json.loads(sbom_json)["@graph"]

        assert not [e for e in graph if e.get("type") == "dataset_DatasetPackage"]


def test_generate_project_sbom_enrich_true_overrides_config() -> None:
    """enrich=True passed to generate_project_sbom() must turn on
    enrichment even with no [tool.pitloom] enrich config present."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pkg_dir = tmppath / "src" / "smoke_project"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "__init__.py").write_text("")
        fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
        (pkg_dir / "model.safetensors").write_bytes(fixture.read_bytes())
        (pkg_dir / "README.md").write_text("---\ndatasets:\n  - tiny-imagenet\n---\n")
        (tmppath / "pyproject.toml").write_text(
            "[build-system]\n"
            'requires = ["hatchling"]\n'
            'build-backend = "hatchling.build"\n\n'
            "[project]\n"
            'name = "smoke-project"\n'
            'version = "0.1.0"\n\n'
            "[tool.hatch.build.targets.wheel]\n"
            'packages = ["src/smoke_project"]\n'
        )

        sbom_json = generate_project_sbom(tmppath, enrich=True)
        graph = json.loads(sbom_json)["@graph"]

        ds_pkgs = [e for e in graph if e.get("type") == "dataset_DatasetPackage"]
        assert len(ds_pkgs) == 1
        assert ds_pkgs[0]["name"] == "tiny-imagenet"


def test_generate_project_sbom_license_conflict_end_to_end() -> None:
    """Declared MIT + an independently-detected Apache-2.0 LICENSE file:
    both hasDeclaredLicense and hasConcludedLicense are emitted (pointing at
    two distinct license elements), plus one G2 conflict Annotation on the
    main package."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"
license = "MIT"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)
        (tmppath / "LICENSE").write_text("Apache License\nVersion 2.0" + "x" * 200)

        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="Apache-2.0",
        ):
            sbom_json = generate_project_sbom(tmppath)

        graph = json.loads(sbom_json)["@graph"]
        main_package = next(
            e
            for e in graph
            if e.get("type") == "software_Package" and e["name"] == "test-package"
        )
        declared, concluded = _license_relationships(graph, main_package["spdxId"])
        assert len(declared) == 1
        assert len(concluded) == 1

        license_elems = {
            e["spdxId"]: e
            for e in graph
            if e.get("type") == "simplelicensing_SimpleLicensingText"
        }
        declared_license = license_elems[declared[0]["to"][0]]
        concluded_license = license_elems[concluded[0]["to"][0]]
        assert declared_license["simplelicensing_licenseText"] == "MIT"
        assert concluded_license["simplelicensing_licenseText"] == "Apache-2.0"
        assert declared_license["spdxId"] != concluded_license["spdxId"]

        annotations = [e for e in graph if e.get("type") == "Annotation"]
        conflict_anns = [
            a
            for a in annotations
            if a.get("subject") == main_package["spdxId"]
            and json.loads(a["statement"]).get("kind") == "conflict"
        ]
        assert len(conflict_anns) == 1
        statement = json.loads(conflict_anns[0]["statement"])
        assert statement["field"] == "license"
        roles = {c["role"] for c in statement["candidates"]}
        assert roles == {"declared", "detected"}


def test_generate_project_sbom_license_conflict_flags_declared_normalization() -> None:
    """Declared "mit" (valid but non-canonically cased) + a genuinely
    conflicting detected Apache-2.0: the conflict Annotation's declared
    candidate ``source`` is flagged with the raw value normalize_license_
    expression() rewrote it from, plus the py-spdx-license version that did
    it -- wiring the previously-dead _PY_SPDX_LICENSE_VERSION into actual
    output (not just the case-only-agreement path, which never reaches the
    conflict branch at all)."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"
license = "mit"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)
        (tmppath / "LICENSE").write_text("Apache License\nVersion 2.0" + "x" * 200)

        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="Apache-2.0",
        ):
            sbom_json = generate_project_sbom(tmppath)

        graph = json.loads(sbom_json)["@graph"]
        main_package = next(
            e
            for e in graph
            if e.get("type") == "software_Package" and e["name"] == "test-package"
        )
        annotations = [e for e in graph if e.get("type") == "Annotation"]
        conflict_anns = [
            a
            for a in annotations
            if a.get("subject") == main_package["spdxId"]
            and json.loads(a["statement"]).get("kind") == "conflict"
        ]
        assert len(conflict_anns) == 1
        statement = json.loads(conflict_anns[0]["statement"])
        declared_candidate = next(
            c for c in statement["candidates"] if c["role"] == "declared"
        )
        assert declared_candidate["value"] == "MIT"
        assert "Normalized-From: mit" in declared_candidate["source"]
        assert "Normalizer: py-spdx-license==" in declared_candidate["source"]


def test_generate_project_sbom_license_agrees_no_conflict_annotation() -> None:
    """Declared and independently-detected license agree: both relationships
    still emitted, pointing at the *same* element, but no conflict Annotation."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"
license = "MIT"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)
        (tmppath / "LICENSE").write_text("MIT License\n\nPermission" + "x" * 200)

        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="MIT",
        ):
            sbom_json = generate_project_sbom(tmppath)

        graph = json.loads(sbom_json)["@graph"]
        main_package = next(
            e
            for e in graph
            if e.get("type") == "software_Package" and e["name"] == "test-package"
        )
        declared, concluded = _license_relationships(graph, main_package["spdxId"])
        assert len(declared) == 1
        assert len(concluded) == 1
        assert declared[0]["to"][0] == concluded[0]["to"][0]


def test_generate_project_sbom_license_case_only_difference_not_a_conflict() -> None:
    """Regression: a declared `license = "mit"` (valid but non-canonically
    cased -- kept verbatim since Pitloom never rewrites a bare SPDX id) and
    an independently-detected canonical "MIT" from the LICENSE file must be
    recognized as the *same* license, not flagged as G2 conflict. Before the
    canonicalization fix, this produced a spurious conflict Annotation and
    two separate license elements for what is one license."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"
license = "mit"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)
        (tmppath / "LICENSE").write_text("MIT License\n\nPermission" + "x" * 200)

        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="MIT",
        ):
            sbom_json = generate_project_sbom(tmppath)

        graph = json.loads(sbom_json)["@graph"]
        main_package = next(
            e
            for e in graph
            if e.get("type") == "software_Package" and e["name"] == "test-package"
        )
        declared, concluded = _license_relationships(graph, main_package["spdxId"])
        assert len(declared) == 1
        assert len(concluded) == 1
        assert declared[0]["to"][0] == concluded[0]["to"][0]

        license_elems = [
            e for e in graph if e.get("type") == "simplelicensing_SimpleLicensingText"
        ]
        assert len(license_elems) == 1
        assert license_elems[0]["simplelicensing_licenseText"] == "MIT"

        annotations = [e for e in graph if e.get("type") == "Annotation"]
        conflict_anns = [
            a
            for a in annotations
            if json.loads(a["statement"]).get("kind") == "conflict"
        ]
        assert conflict_anns == []

        annotations = [e for e in graph if e.get("type") == "Annotation"]
        conflict_anns = [
            a
            for a in annotations
            if json.loads(a["statement"]).get("kind") == "conflict"
        ]
        assert conflict_anns == []


def test_generate_project_sbom_license_declared_only_no_license_file() -> None:
    """Declared license, no LICENSE file in the project: unchanged
    single-relationship behavior (regression check against pre-G2 output)."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"
license = "MIT"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        sbom_json = generate_project_sbom(tmppath)

        graph = json.loads(sbom_json)["@graph"]
        main_package = next(
            e
            for e in graph
            if e.get("type") == "software_Package" and e["name"] == "test-package"
        )
        declared, concluded = _license_relationships(graph, main_package["spdxId"])
        assert len(declared) == 1
        assert len(concluded) == 0


def test_generate_project_sbom_license_conflict_byte_identical_across_runs() -> None:
    """Determinism: two independent generations from the same input produce
    byte-identical output, including the new conflict Annotation."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"
license = "MIT"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)
        (tmppath / "LICENSE").write_text("Apache License\nVersion 2.0" + "x" * 200)

        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="Apache-2.0",
        ):
            creation_metadata = CreationMetadata(
                creation_datetime="2026-01-01T00:00:00Z"
            )
            sbom_json_1 = generate_project_sbom(
                tmppath, creation_metadata=creation_metadata
            )
            sbom_json_2 = generate_project_sbom(
                tmppath, creation_metadata=creation_metadata
            )

        assert sbom_json_1 == sbom_json_2
