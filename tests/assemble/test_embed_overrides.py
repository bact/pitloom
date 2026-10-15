# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.embed configuration overrides and standalone-wheel SBOM paths.

See also:
- :mod:`tests.assemble.test_embed_cli` for CLI embed-wheel commands.
- :mod:`tests.assemble.test_embed_core` for core embed logic.
- :mod:`tests.assemble.test_embed_internals` for low-level ZIP manipulation.
- :mod:`tests.assemble.test_embed_cleanup` for when the discovery cleanup
  runs.
- :mod:`tests.test_build_flag_warnings` for the "build flag has no effect"
  warnings (``ConfigOverrides.build_options``) on every embed path.
"""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest
from installer.sources import WheelFile

from pitloom import __main__
from pitloom.core.models import _build_merkle_tree, merkle_root_of_files
from pitloom.embed import (
    ConfigOverrides,
    embed_wheel_sbom,
)
from pitloom.id_registry import DEFAULT_ID_REGISTRY_FILENAME, FILE_TYPE, IdRegistry

from .conftest import _make_dummy_wheel


def test_cli_and_api_produce_identical_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify CLI and Python API produce bit-for-bit identical wheels and SBOMs."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    monkeypatch.chdir(tmp_path)

    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "identpkg"
version = "1.0.0"

[tool.pitloom]
creation-comment = "shared-comment"
creation-datetime = "2026-08-14T12:00:00Z"

[[tool.pitloom.creator]]
name = "Test Author"
type = "person"
""",
        encoding="utf-8",
    )

    dir_cli = tmp_path / "cli"
    dir_api = tmp_path / "api"
    w_cli = _make_dummy_wheel(dir_cli, "identpkg", "1.0.0")
    w_api = _make_dummy_wheel(dir_api, "identpkg", "1.0.0")

    monkeypatch.setattr(
        sys, "argv", ["loom", "embed-wheel", str(w_cli), "--project-dir", str(tmp_path)]
    )
    assert __main__.main() == 0

    _, arcname_api, sbom_json_api, _, _ = embed_wheel_sbom(w_api, project_dir=tmp_path)

    with zipfile.ZipFile(w_cli, "r") as z_cli, zipfile.ZipFile(w_api, "r") as z_api:
        assert z_cli.namelist() == z_api.namelist()
        cli_sbom_bytes = z_cli.read(arcname_api)
        api_sbom_bytes = z_api.read(arcname_api)
        assert cli_sbom_bytes == api_sbom_bytes
        assert cli_sbom_bytes.decode("utf-8") == sbom_json_api

        cli_record = z_cli.read("identpkg-1.0.0.dist-info/RECORD")
        api_record = z_api.read("identpkg-1.0.0.dist-info/RECORD")
        assert cli_record == api_record

    assert w_cli.read_bytes() == w_api.read_bytes()


def test_embed_wheel_content_type_reaches_sbom_files(tmp_path: Path) -> None:
    """content-type detection must reach the Build SBOM's file list.

    ``_build_sbom_from_project_and_wheel`` merges ``get_wheel_files()``'s
    content-type/file-header data onto ``wheel_metadata``'s file records
    (see ``_merge_file_extras``); this guards against a regression where
    that data is computed but never reaches the assembled SBOM.
    """
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "ctpkg"
version = "1.0.0"

[tool.hatch.build.targets.wheel]
packages = ["ctpkg"]
""",
        encoding="utf-8",
    )
    pkg_dir = tmp_path / "ctpkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("x = 1\n", encoding="utf-8")

    wheel_path = _make_dummy_wheel(tmp_path / "dist", "ctpkg", "1.0.0")

    _, _, sbom_json, _, _ = embed_wheel_sbom(
        wheel_path,
        project_dir=tmp_path,
        overrides=ConfigOverrides(content_type=True),
    )

    doc = json.loads(sbom_json)
    files = [n for n in doc["@graph"] if n.get("type") == "software_File"]
    assert files, "expected at least one software_File in the SBOM"
    assert any(f.get("contentType") for f in files), (
        "content-type override did not reach the SBOM's file list"
    )


def _sbom_files_by_name(sbom_json: str) -> dict[str, dict[str, Any]]:
    """Map ``name`` -> node for every file-kind ``software_File`` in *sbom_json*."""
    doc = json.loads(sbom_json)
    return {
        n["name"]: n
        for n in doc["@graph"]
        if n.get("type") == "software_File" and n.get("software_fileKind") == "file"
    }


def test_embed_wheel_preserves_wheel_truth_and_merges_content_type(
    tmp_path: Path,
) -> None:
    """Merging must keep the wheel's own file list and hashes intact.

    ``_build_sbom_from_project_and_wheel`` must not replace
    ``wheel_metadata.files`` outright with a project-dir rescan: that would
    report hashes of the *current* source tree instead of the wheel's own
    already-built bytes. This checks the wheel's bytes are kept (and its
    own ``.dist-info``, not payload, is not listed) while content-type
    still reaches the matching file (see ``_merge_file_extras``).
    """
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "ctpkg"
version = "1.0.0"

[tool.hatch.build.targets.wheel]
packages = ["ctpkg"]
""",
        encoding="utf-8",
    )
    pkg_dir = tmp_path / "ctpkg"
    pkg_dir.mkdir()
    # Deliberately differs from the wheel's own __init__.py (see
    # _make_dummy_wheel) so a hash mix-up between "source on disk" and
    # "bytes actually in the wheel" would be caught.
    (pkg_dir / "__init__.py").write_text("x = 1\n", encoding="utf-8")

    wheel_path = _make_dummy_wheel(tmp_path / "dist", "ctpkg", "1.0.0")

    _, _, sbom_json, _, _ = embed_wheel_sbom(
        wheel_path,
        project_dir=tmp_path,
        overrides=ConfigOverrides(content_type=True),
    )

    files_by_name = _sbom_files_by_name(sbom_json)
    assert not [n for n in files_by_name if ".dist-info/" in n]  # not payload

    init_file = files_by_name["ctpkg/__init__.py"]
    (hash_obj,) = init_file["verifiedUsing"]
    expected_digest = hashlib.sha256(b"__version__ = '1.0.0'\n").hexdigest()
    assert hash_obj["hashValue"] == expected_digest
    assert init_file.get("contentType")


def test_merkle_root_of_files_empty_returns_none() -> None:
    """No files means no Merkle root to assert, not a computed one over nothing."""
    assert merkle_root_of_files([]) is None


def test_embed_wheel_merkle_root_reflects_wheel_not_rescan(
    tmp_path: Path,
) -> None:
    """The document's Merkle root must be computed from the wheel's own
    (post-merge) file hashes, not a fresh rescan of ``project_dir``.

    Regression test: ``_build_sbom_from_project_and_wheel`` used to pass
    through ``get_wheel_files()``'s own ``merkle_root`` -- computed by
    hashing ``project_dir``'s on-disk bytes -- straight into the exported
    document, even though ``_merge_file_extras`` had already fixed the
    *per-file* hashes to prefer the wheel's own truth. Whenever
    ``project_dir`` diverges from the already-built wheel (as it
    deliberately does here, mirroring
    ``test_embed_wheel_preserves_wheel_truth_and_merges_content_type``),
    that left the package's ``verifiedUsing`` Merkle root -- and every
    SPDX ID derived from it via ``compute_doc_uuid`` -- describing a
    different file set than the one actually reported.
    """
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "ctpkg"
version = "1.0.0"

[tool.hatch.build.targets.wheel]
packages = ["ctpkg"]
""",
        encoding="utf-8",
    )
    pkg_dir = tmp_path / "ctpkg"
    pkg_dir.mkdir()
    # Deliberately differs from the wheel's own __init__.py (see
    # _make_dummy_wheel) so a Merkle root computed from this rescan would
    # differ from one computed from the wheel's own bytes.
    (pkg_dir / "__init__.py").write_text("x = 1\n", encoding="utf-8")

    wheel_path = _make_dummy_wheel(tmp_path / "dist", "ctpkg", "1.0.0")

    # Capture the wheel's own bytes *before* embedding mutates it (adds the
    # SBOM entry and rewrites RECORD) -- this is the file set
    # merkle_root_of_files should be reproducible from.
    with zipfile.ZipFile(wheel_path, "r") as zf:
        wheel_contents = {
            name: zf.read(name)
            for name in zf.namelist()
            if ".dist-info/" not in name  # not payload
        }

    _, _, sbom_json, _, _ = embed_wheel_sbom(
        wheel_path,
        project_dir=tmp_path,
        overrides=ConfigOverrides(content_type=True),
    )

    doc = json.loads(sbom_json)
    (main_pkg,) = [
        n
        for n in doc["@graph"]
        if n.get("type") == "software_Package" and n.get("name") == "ctpkg"
    ]
    (verified,) = main_pkg["verifiedUsing"]

    ordered_payloads = [p for _, p in sorted(wheel_contents.items())]
    expected_root = _build_merkle_tree(
        [hashlib.sha256(p).digest() for p in ordered_payloads]
    )
    assert verified["hashValue"] == expected_root

    # Sanity check that this fixture actually exercises divergence: a root
    # over the *rescanned* project_dir bytes (which differ only in
    # ctpkg/__init__.py) must NOT equal the wheel-derived root above, or
    # this test would pass even with the old, buggy code.
    rescan_contents = dict(wheel_contents)
    rescan_contents["ctpkg/__init__.py"] = b"x = 1\n"
    rescan_root = _build_merkle_tree(
        [hashlib.sha256(p).digest() for _, p in sorted(rescan_contents.items())]
    )
    assert rescan_root != expected_root


def test_embed_wheel_scan_failure_keeps_wheel_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A get_wheel_files() scan failure must not empty the SBOM's file list.

    ``get_wheel_files()`` returns ``(None, [], <no-op cleanup>)`` on any
    scan failure; the merge in ``_build_sbom_from_project_and_wheel``
    must fall back to the wheel's own files rather than propagating
    that empty result.
    """
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "ctpkg"
version = "1.0.0"

[tool.hatch.build.targets.wheel]
packages = ["ctpkg"]
""",
        encoding="utf-8",
    )
    pkg_dir = tmp_path / "ctpkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("x = 1\n", encoding="utf-8")

    wheel_path = _make_dummy_wheel(tmp_path / "dist", "ctpkg", "1.0.0")

    monkeypatch.setattr(
        "pitloom._embed_build_sbom.get_wheel_files",
        lambda *a, **k: (None, [], lambda: None),
    )

    _, _, sbom_json, _, _ = embed_wheel_sbom(
        wheel_path,
        project_dir=tmp_path,
        overrides=ConfigOverrides(content_type=True),
    )

    files_by_name = _sbom_files_by_name(sbom_json)
    assert files_by_name.keys() == {"ctpkg/__init__.py"}
    assert not files_by_name["ctpkg/__init__.py"].get("contentType")


def test_embed_standalone_wheel_uses_only_an_explicit_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no project directory, a ``loom-id-registry.json`` near the current
    directory belongs to whatever project that is: it is never adopted. An
    explicit registry is -- which also proves the seeded registry would
    have shown up in the SBOM."""
    wheel_path = _make_dummy_wheel(tmp_path / "dist", "standalonereg", "1.0.0")
    namespace = "https://example.invalid/cwd-registry"
    registry = IdRegistry(namespace=namespace)
    member = "standalonereg/__init__.py"
    with zipfile.ZipFile(wheel_path) as archive:
        digest = hashlib.sha256(archive.read(member)).hexdigest()
    registry.register(FILE_TYPE, member, sha256=digest)
    registry.save(tmp_path / DEFAULT_ID_REGISTRY_FILENAME)
    monkeypatch.chdir(tmp_path)

    *_, implicit, _, _ = embed_wheel_sbom(wheel_path)
    *_, explicit, _, _ = embed_wheel_sbom(
        wheel_path, id_registry=tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    )

    assert namespace not in implicit
    assert namespace in explicit


def test_cli_wheel_embed_ignores_cwd_project(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ensure loom wheel <wheel> --embed ignores cwd pyproject.toml."""
    wheel_path = _make_dummy_wheel(tmp_path, "flagpkg", "1.0.0")

    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "cwdpkg"
version = "2.0.0"

[tool.pitloom]
creation-comment = "from-cwd"
""",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["loom", "wheel", str(wheel_path), "--embed"])

    assert __main__.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("WHEEL=") and " SBOM=" in captured.out

    with WheelFile.open(wheel_path) as wf:
        wf.validate_record()

    with zipfile.ZipFile(wheel_path, "r") as zf:
        sbom_bytes = zf.read("flagpkg-1.0.0.dist-info/sboms/flagpkg-1.0.0.spdx3.json")
        assert b"from-cwd" not in sbom_bytes
