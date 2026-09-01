# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.embed's CLI surface (embed-wheel / wheel --embed).

See also:
- :mod:`tests.assemble.test_embed_overrides` for overrides and standalone build path.
- :mod:`tests.assemble.test_embed_core` for core embed logic.
- :mod:`tests.assemble.test_embed_internals` for low-level ZIP manipulation.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest
from installer.sources import WheelFile

from pitloom import __main__

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


def test_cli_embed_wheel_single_with_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test `loom embed-wheel <single_wheel> -o <path>` also writes a
    standalone SBOM copy and reports its path -- unlike the multi-wheel
    case, a single wheel is allowed to combine ``--embed`` with ``-o``."""
    wheel_path = _make_dummy_wheel(tmp_path, "singlepkg", "1.0.0")
    out_file = tmp_path / "standalone.spdx3.json"

    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "embed-wheel", str(wheel_path), "-o", str(out_file)],
    )
    assert __main__.main() == 0
    captured = capsys.readouterr()
    assert "pitloom: embedded" in captured.out
    assert "PITLOOM_" in captured.out
    assert out_file.exists()


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


def test_cli_embed_wheel_verify_flag_passes_on_happy_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--verify runs verify-wheel's own check against the freshly embedded
    wheel -- no WARNING/ERROR since embed-wheel always uses the
    recommended extension, exit stays 0."""
    wheel_path = _make_dummy_wheel(tmp_path, "verifyflag", "1.0.0")
    sbom_file = tmp_path / "sbom.spdx3.json"
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
            "--verify",
        ],
    )
    assert __main__.main() == 0

    captured = capsys.readouterr()
    assert "pitloom: embedded" in captured.out
    assert "WARNING:" not in captured.err
    assert "ERROR:" not in captured.err


def test_cli_embed_wheel_validate_flag_fails_on_invalid_sbom(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--validate runs validate-wheel's own check against the just-embedded
    wheel. A malformed --sbom still embeds successfully, but --validate
    catches the problem afterwards and the command exits 1 -- embedding
    already happened and isn't rolled back."""
    wheel_path = _make_dummy_wheel(tmp_path, "validateflag", "1.0.0")
    sbom_file = tmp_path / "bad.spdx3.json"
    # @context present (so it's detected as spdx3-jsonld and actually
    # reaches spdx3_validate.validate()) but unrecognized -> UnknownVersionError.
    sbom_file.write_text('{"@context": "bogus", "@graph": []}', encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "embed-wheel",
            str(wheel_path),
            "--sbom",
            str(sbom_file),
            "--validate",
        ],
    )
    assert __main__.main() == 1

    captured = capsys.readouterr()
    assert "pitloom: embedded" in captured.out
    assert "ERROR:" in captured.err

    with zipfile.ZipFile(wheel_path, "r") as zf:
        assert any(n.endswith(".spdx3.json") and "/sboms/" in n for n in zf.namelist())
