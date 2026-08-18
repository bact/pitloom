# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for assembly subsystem edge cases, fallbacks, and error recovery.

See also:
- :mod:`tests.assemble.test_deps_enrichment_names_versions`
- :mod:`tests.assemble.test_deps_enrichment_supplier_license`
- :mod:`tests.assemble.test_annotation_provenance_core`
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest
from packaging.requirements import InvalidRequirement
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._provenance_encoders import ProvenanceEncoder
from pitloom.assemble.spdx3.deps import _enrich_from_pypi
from pitloom.assemble.spdx3.deps_installed import (
    _enrich_from_installed,
    _parse_dep_name,
    _resolve_version,
)
from pitloom.assemble.spdx3.deps_originator import (
    _apply_originator,
    _collect_originator_agents,
    _find_license_copyright,
    _read_candidate_copyright,
)
from pitloom.assemble.spdx3.fragments import (
    _add_fragment_imports,
    _add_model_sbom,
    _emit_unification_annotations,
    merge_fragments,
)
from pitloom.export.spdx3_json import Spdx3JsonExporter


def _make_ci() -> spdx3.CreationInfo:
    return spdx3.CreationInfo(
        specVersion="3.0.1",
        created=datetime.fromtimestamp(1_700_000_000, tz=timezone.utc),
        createdBy=["http://spdx.org/spdxdocs/actor"],
    )


def test_provenance_encoder_protocol_raises_not_implemented() -> None:
    """ProvenanceEncoder.encode raises NotImplementedError when invoked directly."""
    with pytest.raises(NotImplementedError):
        ProvenanceEncoder.encode(None, {})  # type: ignore[arg-type]


def test_parse_dep_name_invalid_requirement_fallbacks() -> None:
    """_parse_dep_name falls back to operator split or strip on InvalidRequirement."""
    with patch(
        "pitloom.assemble.spdx3.deps_installed.Requirement",
        side_effect=InvalidRequirement("invalid syntax"),
    ):
        assert _parse_dep_name("pkg-name>=1.0.0") == "pkg-name"
        assert _parse_dep_name("  simple-name  ") == "simple-name"


def test_resolve_version_invalid_requirement_fallbacks() -> None:
    """_resolve_version returns version after == or unknown on invalid requirement."""
    with patch(
        "pitloom.assemble.spdx3.deps_installed.get_package_version",
        side_effect=PackageNotFoundError("not found"),
    ):
        with patch(
            "pitloom.assemble.spdx3.deps_installed.Requirement",
            side_effect=InvalidRequirement("syntax error"),
        ):
            ver1, src1 = _resolve_version("mypkg", "mypkg == 2.3.4")
            assert ver1 == "2.3.4"
            assert src1 is None

            ver2, src2 = _resolve_version("mypkg", "mypkg >= 1.0")
            assert ver2 == "unknown"
            assert src2 is None


def test_enrich_from_installed_unknown_version_skips_purl() -> None:
    """_enrich_from_installed skips purl assignment when package version is unknown."""
    exporter = Spdx3JsonExporter()
    creation_info = _make_ci()
    dep_pkg = spdx3.software_Package(
        spdxId="http://spdx.org/spdxdocs/pkg",
        creationInfo=creation_info,
        name="foo",
    )
    dep_pkg.software_packageVersion = "unknown"

    mock_meta = MagicMock()
    mock_meta.get_all.return_value = []
    meta_dict = {
        "Summary": "Foo package",
        "Home-page": "https://example.com/foo",
        "Download-URL": None,
        "Author": "Alice",
        "Author-email": "alice@example.com",
    }
    mock_meta.__getitem__.side_effect = lambda k: meta_dict.get(k, None)

    with patch(
        "pitloom.assemble.spdx3.deps_installed.get_pkg_metadata",
        return_value=mock_meta,
    ):
        _enrich_from_installed(
            "foo",
            dep_pkg,
            creation_info,
            "test_doc",
            "test_uuid",
            exporter,
        )
    assert getattr(dep_pkg, "software_packageUrl", None) is None


def test_deps_originator_candidate_copyright_and_find_license() -> None:
    """_read_candidate_copyright and _find_license_copyright handle errors."""

    class MockDecodeErrFile:
        def __str__(self) -> str:
            return "foo-1.0.dist-info/LICENSE"

        def read_text(self, encoding: str = "utf-8") -> str:
            raise UnicodeDecodeError("utf-8", b"", 0, 1, "err")

    class MockEmptyFile:
        def __str__(self) -> str:
            return "foo-1.0.dist-info/LICENSE"

        def read_text(self, encoding: str = "utf-8") -> str:
            return ""

    assert _read_candidate_copyright(MockDecodeErrFile()) is None
    assert _read_candidate_copyright(MockEmptyFile()) is None

    # Package not found in _find_license_copyright
    mock_pkg_meta = MagicMock()
    mock_pkg_meta.get_all.return_value = ["LICENSE"]
    with patch(
        "pitloom.assemble.spdx3.deps_originator.get_pkg_distribution",
        side_effect=PackageNotFoundError("not found"),
    ):
        assert _find_license_copyright("nonexistent", mock_pkg_meta) is None


def test_collect_originator_agents_and_apply_originators() -> None:
    """_collect_originator_agents appends attribution and handles empties."""
    exporter = Spdx3JsonExporter()
    creation_info = _make_ci()
    dep_pkg = spdx3.software_Package(
        spdxId="http://spdx.org/spdxdocs/pkg",
        creationInfo=creation_info,
        name="mypkg",
    )
    dep_pkg.software_attributionText = ["Existing attribution"]

    # All empty originators
    assert not _apply_originator([], dep_pkg, creation_info, "doc", "uuid", exporter)
    assert not _apply_originator(
        [(None, None)], dep_pkg, creation_info, "doc", "uuid", exporter
    )

    # Valid originators appending to attribution
    agent_ids = _collect_originator_agents(
        [("Alice", "alice@example.com")],
        dep_pkg,
        creation_info,
        "doc",
        "uuid",
        exporter,
        repo_url="https://github.com/example/mypkg",
        offline=True,
        content_type_method="auto",
    )
    assert len(agent_ids) == 1
    assert len(dep_pkg.software_attributionText) >= 1


def test_fragments_imports_unification_and_errors() -> None:
    """_add_fragment_imports, unification, and invalid fragment error handling."""
    creation_info = _make_ci()
    main_doc = spdx3.SpdxDocument(
        spdxId="http://spdx.org/spdxdocs/doc",
        creationInfo=creation_info,
        name="doc",
    )
    main_doc.import_ = [
        "http://spdx.org/spdxdocs/old-import",
        spdx3.ExternalMap(
            externalSpdxId="http://spdx.org/spdxdocs/frag-1",
            locationHint="frag1.json",
        ),
    ]

    new_imports = [
        spdx3.ExternalMap(
            externalSpdxId="http://spdx.org/spdxdocs/frag-1",
            locationHint="dup.json",
        ),
        spdx3.ExternalMap(
            externalSpdxId="http://spdx.org/spdxdocs/frag-2",
            locationHint="frag2.json",
        ),
    ]
    _add_fragment_imports(main_doc, new_imports)
    assert len(main_doc.import_) == 3

    # Empty / None spdxId guards in _emit_unification_annotations and _add_model_sbom
    exporter = Spdx3JsonExporter()
    bad_doc = MagicMock()
    bad_doc.spdxId = None
    bad_doc.creationInfo = None
    _emit_unification_annotations(
        {"sub": {"crit": {"unified": set(), "fragments": set()}}}, bad_doc, exporter
    )
    _add_model_sbom(bad_doc, exporter)

    # Invalid JSON-LD fragment file in merge_fragments
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        frag = p / "invalid.json"
        frag.write_bytes(b"not json ld at all")
        merge_fragments(p, ["invalid.json"], exporter)


def test_enrich_from_pypi_already_filled_and_home_page() -> None:
    """_enrich_from_pypi skips already_filled fields and resolves home_page fallback."""
    exporter = Spdx3JsonExporter()
    creation_info = _make_ci()
    dep_pkg = spdx3.software_Package(
        spdxId="http://spdx.org/spdxdocs/pkg",
        creationInfo=creation_info,
        name="pypipkg",
    )
    release_info = {
        "info": {
            "home_page": "https://example.com/pypi",
            "author": "Bob",
            "license": "MIT",
        },
        "urls": [
            {
                "digests": {
                    "sha256": (
                        "abcdef1234567890abcdef1234567890"
                        "abcdef1234567890abcdef1234567890"
                    )
                }
            }
        ],
    }
    # Already filled with originator and license
    filled = _enrich_from_pypi(
        "pypipkg",
        "1.0.0",
        dep_pkg,
        creation_info,
        "doc",
        "uuid",
        exporter,
        already_filled={"originator", "license"},
        release_info_cache={("pypipkg", "1.0.0"): release_info},
    )
    assert "hash" in filled
    assert "originator" not in filled
    assert "license" not in filled


@pytest.mark.pypi_network
def test_deps_pypi_fetch_release_info_mocked() -> None:
    """_fetch_pypi_release_info handles success and catches ValueError."""
    from pitloom.assemble.spdx3.deps_pypi import _fetch_pypi_release_info

    with patch(
        "pitloom.assemble.spdx3.deps_pypi.fetch_json",
        return_value={"info": {"name": "foo"}},
    ):
        assert _fetch_pypi_release_info("foo", None) == {"info": {"name": "foo"}}
        assert _fetch_pypi_release_info("foo", "1.0.0") == {"info": {"name": "foo"}}

    with patch(
        "pitloom.assemble.spdx3.deps_pypi.fetch_json",
        side_effect=ValueError("bad json"),
    ):
        assert _fetch_pypi_release_info("badpkg", None) is None


def test_deps_originator_edge_branches() -> None:
    """_extract_name_email_pairs, _parse_project_urls, remote authors edge branches."""
    from pitloom.assemble.spdx3.deps_originator import (
        _extract_name_email_pairs,
        _get_or_create_originator_agent,
        _parse_project_urls,
        _resolve_remote_authors_file,
    )

    # _extract_name_email_pairs with empty name/email or commas with spaces
    assert _extract_name_email_pairs("", "  ") == []
    assert len(_extract_name_email_pairs("Alice, , and Bob", "")) == 2

    # A single address's display name can itself be a comma-separated list
    # of names sharing one address (seen in the wild on PyPI for a real
    # package, where the address belongs to a person not even in the name
    # list). The shared address can't be fairly attributed to any one
    # listed name, so it splits into name-only tuples plus one extra
    # email-only tuple that keeps the address on its own anonymous Person.
    assert _extract_name_email_pairs(
        "",
        '"Author One, Author Two, Author Three" <x@example.com>',
    ) == [
        ("Author One", None),
        ("Author Two", None),
        ("Author Three", None),
        (None, "x@example.com"),
    ]

    # _parse_project_urls with malformed entry without comma
    mock_pkg = MagicMock()
    mock_pkg.get_all.return_value = ["no_comma_here", "Home, https://example.com"]
    urls = _parse_project_urls(mock_pkg)
    assert urls == {"home": "https://example.com"}

    # _resolve_remote_authors_file with an unrecognized host: no known
    # blob/raw URL scheme, so it returns the bare repo URL with no fetch.
    loc, ctype, text = _resolve_remote_authors_file(
        "https://bitbucket.org/foo/bar",
        "AUTHORS",
        offline=False,
        content_type_method="auto",
    )
    assert loc == "https://bitbucket.org/foo/bar"
    assert ctype is None
    assert text is None

    # _resolve_remote_authors_file falls back to a locator-only result when
    # the raw-content fetch fails, without making a real network call.
    with patch(
        "urllib.request.urlopen", side_effect=URLError("simulated network failure")
    ):
        loc2, ctype2, text2 = _resolve_remote_authors_file(
            "https://github.com/foo/bar",
            "AUTHORS",
            offline=False,
            content_type_method="auto",
        )
    assert loc2 == "https://github.com/foo/bar/blob/HEAD/AUTHORS"
    assert text2 is None

    # _find_license_copyright where files exist but no copyright matches
    class MockNoMatchFile:
        name = "LICENSE"

        def __str__(self) -> str:
            return "pkg-1.0.dist-info/LICENSE"

        def read_text(self, encoding: str = "utf-8") -> str:
            return "No copyright statement here at all."

    mock_dist = MagicMock()
    mock_dist.files = [MockNoMatchFile()]
    mock_pkg_with_lic = MagicMock()
    mock_pkg_with_lic.get_all.return_value = ["LICENSE"]
    with patch(
        "pitloom.assemble.spdx3.deps_originator.get_pkg_distribution",
        return_value=mock_dist,
    ):
        assert _find_license_copyright("mypkg", mock_pkg_with_lic) is None

    # _get_or_create_originator_agent with remote authors contentType
    exporter = Spdx3JsonExporter()
    creation_info = _make_ci()
    with patch(
        "pitloom.assemble.spdx3.deps_originator._resolve_remote_authors_file",
        return_value=("https://raw.../AUTHORS", "text/plain", "Author text"),
    ):
        aid, attr_text = _get_or_create_originator_agent(
            "and others (see AUTHORS.txt)",
            None,
            creation_info,
            "doc",
            "uuid",
            exporter,
            repo_url="https://github.com/foo/bar",
        )
        assert aid
        assert attr_text == "Author text"

    # _collect_originator_agents appends to existing attributionText
    dep_pkg = spdx3.software_Package(
        spdxId="http://spdx.org/spdxdocs/pkg",
        creationInfo=creation_info,
        name="mypkg",
    )
    dep_pkg.software_attributionText = ["Initial attribution"]
    with patch(
        "pitloom.assemble.spdx3.deps_originator._get_or_create_originator_agent",
        return_value=("http://spdx.org/spdxdocs/aid", "Second attribution"),
    ):
        _collect_originator_agents(
            [("Alice", "a@a.com")],
            dep_pkg,
            creation_info,
            "doc",
            "uuid",
            exporter,
            repo_url="https://github.com/foo/bar",
            offline=True,
            content_type_method="auto",
        )
    assert len(dep_pkg.software_attributionText) == 2


def test_fragments_and_ai_model_edge_branches() -> None:
    """_find_fragment_document_id and AI model relationship unmapped files."""
    from pitloom.assemble.spdx3.ai import _add_ai_model_file_relationships
    from pitloom.assemble.spdx3.fragments import _find_fragment_document_id
    from pitloom.core.ai_metadata import AiModelFormatInfo, AiModelMetadata

    # Fragment document without spdxId
    frag_set = spdx3.SHACLObjectSet()
    frag_doc = MagicMock()
    frag_doc.spdxId = None
    frag_set.objects = {frag_doc}
    assert _find_fragment_document_id(frag_set) is None

    # AI model with usage_files not present in file_spdx_ids
    exporter = Spdx3JsonExporter()
    creation_info = _make_ci()
    meta = AiModelMetadata(
        format_info=AiModelFormatInfo(file_path_relative="model.onnx"),
        usage_files=["missing_script.py"],
    )
    _add_ai_model_file_relationships(
        meta,
        "http://spdx.org/spdxdocs/ai-pkg",
        {"model.onnx": "http://spdx.org/spdxdocs/file-1"},
        creation_info,
        "doc",
        "uuid",
        exporter,
    )
    rels = [o for o in exporter.object_set.objects if isinstance(o, spdx3.Relationship)]
    assert len(rels) >= 1
