# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.embed's CLI surface (embed-wheel / wheel --embed),
config overrides, and the standalone-wheel SBOM build path.

See also: test_embed_core.py, test_embed_internals.py -- this module's
siblings, split from the original test_embed.py.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest
from installer.sources import WheelFile

from pitloom import __main__
from pitloom.core.config import PitloomConfig
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import ProvenanceConfig
from pitloom.embed import (
    ConfigOverrides,
    _apply_config_overrides,
    _build_sbom_standalone_wheel,
    embed_wheel_sbom,
)
from pitloom.ids import IdRegistry

from .conftest import _SAMPLE_SPDX3_JSON, _make_dummy_wheel


def test_cli_embed_wheel_absolute_glob(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test `loom embed-wheel <abs_path>/*.whl` with absolute glob patterns."""
    dist_dir = tmp_path / "abs_dist"
    w1 = _make_dummy_wheel(dist_dir, "abs_pkg", "1.0.0")

    monkeypatch.setattr(sys, "argv", ["loom", "embed-wheel", str(dist_dir / "*.whl")])
    assert __main__.main() == 0

    captured = capsys.readouterr()
    assert "abs_pkg-1.0.0-py3-none-any.whl" in captured.out

    with WheelFile.open(w1) as wf:
        wf.validate_record()


def test_cli_embed_wheel_multiple_with_output_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test `loom embed-wheel` fails when multiple wheels match with -o."""
    dist_dir = tmp_path / "dist"
    _make_dummy_wheel(dist_dir, "m1", "1.0.0")
    _make_dummy_wheel(dist_dir, "m2", "1.0.0")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "embed-wheel", "dist/*.whl", "-o", "out.spdx3.json"],
    )
    assert __main__.main() == 1

    captured = capsys.readouterr()
    assert "--output cannot be used when embedding multiple wheels" in captured.err


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

    # Run via CLI
    monkeypatch.setattr(sys, "argv", ["loom", "embed-wheel", str(w_cli)])
    assert __main__.main() == 0

    # Run via Python API
    _, arcname_api, sbom_json_api, _, _ = embed_wheel_sbom(w_api, project_dir=tmp_path)

    # Compare embedded SBOM contents
    with zipfile.ZipFile(w_cli, "r") as z_cli, zipfile.ZipFile(w_api, "r") as z_api:
        assert z_cli.namelist() == z_api.namelist()
        cli_sbom_bytes = z_cli.read(arcname_api)
        api_sbom_bytes = z_api.read(arcname_api)
        assert cli_sbom_bytes == api_sbom_bytes
        assert cli_sbom_bytes.decode("utf-8") == sbom_json_api

        # Compare RECORD contents
        cli_record = z_cli.read("identpkg-1.0.0.dist-info/RECORD")
        api_record = z_api.read("identpkg-1.0.0.dist-info/RECORD")
        assert cli_record == api_record

    # Compare entire wheel binary bytes
    assert w_cli.read_bytes() == w_api.read_bytes()


def test_apply_config_overrides_full() -> None:
    """Test _apply_config_overrides applies all CLI override parameters."""
    cfg = PitloomConfig()
    prov = ProvenanceConfig(
        format="fields",
        schema="https://example.com/schema",
        detail="full",
        preserve_source_metadata="always",
    )
    overridden = _apply_config_overrides(
        cfg,
        ConfigOverrides(
            provenance=prov,
            enrich=True,
            extract_file_header=False,
            content_type=True,
            content_type_method="extension",
            offline=True,
        ),
    )
    assert overridden.provenance_format == "fields"
    assert overridden.provenance_schema == "https://example.com/schema"
    assert overridden.provenance_detail == "full"
    assert overridden.provenance_preserve_source_metadata == "always"
    assert overridden.enrich_local is True
    assert overridden.extract_file_header is False
    assert overridden.content_type.enabled is True
    assert overridden.content_type.method == "extension"
    assert overridden.offline is True

    with pytest.raises(ValueError, match="content_type_method must be one of"):
        _apply_config_overrides(
            cfg,
            ConfigOverrides(content_type_method="invalid_method"),
        )


def test_build_sbom_standalone_wheel_registry_options(tmp_path: Path) -> None:
    """Test _build_sbom_standalone_wheel with various registry options."""
    meta = ProjectMetadata(name="standalonereg", version="1.0.0", files=[])

    # 1. IdRegistry instance with namespace
    reg = IdRegistry(namespace="https://example.com/spdx")
    sbom_1 = _build_sbom_standalone_wheel(meta, None, reg, None, False)
    assert "standalonereg" in sbom_1

    # 2. Path string to registry file
    reg_file = tmp_path / "custom_ids.json"
    reg.save(reg_file)
    sbom_2 = _build_sbom_standalone_wheel(meta, None, str(reg_file), None, True)
    assert "standalonereg" in sbom_2


def test_cli_collect_wheel_paths_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test CLI error handling for non-existent and non-whl paths."""
    not_a_whl = tmp_path / "test.txt"
    not_a_whl.write_text("hello", encoding="utf-8")
    non_existent = tmp_path / "missing.whl"

    # 1. Non-existent literal file
    monkeypatch.setattr(sys, "argv", ["loom", "embed-wheel", str(non_existent)])
    assert __main__.main() == 1
    err = capsys.readouterr().err
    assert "ERROR: wheel file not found" in err

    # 2. Not a .whl file
    monkeypatch.setattr(sys, "argv", ["loom", "embed-wheel", str(not_a_whl)])
    assert __main__.main() == 1
    err = capsys.readouterr().err
    assert "ERROR: not a .whl file" in err

    # 3. Glob matching no wheels
    monkeypatch.setattr(
        sys, "argv", ["loom", "embed-wheel", str(tmp_path / "empty_dir/*.whl")]
    )
    assert __main__.main() == 1
    err = capsys.readouterr().err
    assert "ERROR: no wheel files matched" in err


def test_cli_embed_wheel_multiple_with_output_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test multiple wheels with -o option returns error."""
    w1 = _make_dummy_wheel(tmp_path, "pkg_one", "1.0.0")
    w2 = _make_dummy_wheel(tmp_path, "pkg_two", "1.0.0")

    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "embed-wheel", str(w1), str(w2), "-o", str(tmp_path / "out.json")],
    )
    assert __main__.main() == 1
    err = capsys.readouterr().err
    assert "ERROR: --output cannot be used when embedding multiple wheels" in err


def test_cli_embed_wheel_project_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test CLI with explicit --project-dir."""
    wheel_path = _make_dummy_wheel(tmp_path, "projdirpkg", "1.0.0")
    fixture_dir = (
        Path(__file__).parent.parent
        / "fixtures"
        / "projects"
        / "sampleproject-hatchling"
    )

    # 1. Non-existent project directory
    missing_dir = tmp_path / "no_such_proj_dir"
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "embed-wheel", str(wheel_path), "--project-dir", str(missing_dir)],
    )
    assert __main__.main() == 1
    err = capsys.readouterr().err
    assert "ERROR: project directory not found" in err

    # 2. Valid project directory
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "embed-wheel", str(wheel_path), "--project-dir", str(fixture_dir)],
    )
    assert __main__.main() == 0
    out = capsys.readouterr().out
    assert "pitloom: embedded" in out


def test_cli_embed_wheel_pregenerated_sbom(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test CLI embedding a pregenerated SBOM file with --sbom."""
    wheel_path = _make_dummy_wheel(tmp_path, "pregenpkg", "1.0.0")
    sbom_file = tmp_path / "custom_sbom.spdx3.json"
    sbom_file.write_text(_SAMPLE_SPDX3_JSON, encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "embed-wheel",
            str(wheel_path),
            "--sbom",
            str(sbom_file),
            "--sbom-basename",
            "embedded_pregen.spdx3.json",
        ],
    )
    assert __main__.main() == 0
    out = capsys.readouterr().out
    assert "embedded_pregen.spdx3.json" in out

    with zipfile.ZipFile(wheel_path, "r") as zf:
        assert (
            "pregenpkg-1.0.0.dist-info/sboms/embedded_pregen.spdx3.json"
            in zf.namelist()
        )


def test_cli_wheel_embed_verbose_and_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test `loom wheel --embed` with --verbose and explicit -o."""
    wheel_path = _make_dummy_wheel(tmp_path, "verbosepkg", "1.0.0")
    out_file = tmp_path / "standalone.spdx3.json"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "wheel",
            str(wheel_path),
            "--embed",
            "-v",
            "-o",
            str(out_file),
        ],
    )
    assert __main__.main() == 0
    captured = capsys.readouterr()
    assert "Output path" in captured.out
    assert out_file.exists()


def test_cli_embed_wheel_error_verbose(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test CLI error logging and traceback on failure with --verbose."""
    bad_wheel = tmp_path / "corrupt.whl"
    bad_wheel.write_bytes(b"not a zip file")

    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "embed-wheel", str(bad_wheel), "-v"],
    )
    assert __main__.main() == 1
    err = capsys.readouterr().err
    assert "ERROR: wheel SBOM embedding failed" in err


def test_cli_wheel_embed_error_verbose(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test `loom wheel --embed` failure with --verbose."""
    bad_wheel = tmp_path / "corrupt.whl"
    bad_wheel.write_bytes(b"not a zip file")

    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "wheel", str(bad_wheel), "--embed", "-v"],
    )
    assert __main__.main() == 1
    err = capsys.readouterr().err
    assert "ERROR: wheel command failed" in err


def test_cli_embed_wheel_project_dir_without_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test CLI fallback when project directory exists but has no pyproject.toml."""
    wheel_path = _make_dummy_wheel(tmp_path, "nometa_pkg", "1.0.0")
    empty_dir = tmp_path / "empty_project_dir"
    empty_dir.mkdir()

    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "embed-wheel", str(wheel_path), "--project-dir", str(empty_dir)],
    )
    assert __main__.main() == 1
    err = capsys.readouterr().err
    assert "No pyproject.toml" in err


def test_cli_wheel_embed_ignores_cwd_project(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ensure loom wheel <wheel> --embed ignores cwd pyproject.toml."""
    wheel_path = _make_dummy_wheel(tmp_path, "flagpkg", "1.0.0")

    # Create a valid pyproject.toml in the cwd with pitloom config.
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
    assert "pitloom: embedded" in captured.out

    with WheelFile.open(wheel_path) as wf:
        wf.validate_record()

    # Verify that the generated SBOM did NOT use the cwd's pyproject.toml
    with zipfile.ZipFile(wheel_path, "r") as zf:
        sbom_bytes = zf.read("flagpkg-1.0.0.dist-info/sboms/flagpkg-1.0.0.spdx3.json")
        assert b"from-cwd" not in sbom_bytes
