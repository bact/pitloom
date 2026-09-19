# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.embed's CLI surface (embed-wheel / wheel --embed).

See also:
- :mod:`tests.assemble.test_embed_cli_verify_validate` for `--verify`/
  `--validate`, split from this module.
- :mod:`tests.assemble.test_embed_overrides` for overrides and standalone build path.
- :mod:`tests.assemble.test_embed_core` for core embed logic.
- :mod:`tests.assemble.test_embed_internals` for low-level ZIP manipulation.
- :mod:`tests.assemble.test_embed_wheel_mismatch` for `--sbom`'s pre-embed
  name/version cross-check and `--allow-mismatch`.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path
from unittest import mock

import pytest
from installer.sources import WheelFile

from pitloom import __main__
from pitloom.assemble import find_embedded_sbom
from pitloom.core.models import get_wheel_files as real_get_wheel_files

from .conftest import _make_dummy_wheel, _spdx3_json_with_subject
from .test_embed_overrides import _make_ctpkg_project_and_wheel


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

    # 3. Existing directory with no pyproject.toml/setup.cfg/setup.py at
    # all -- relays read_project()'s own FileNotFoundError message
    # (naming the real reason) rather than a fixed generic guess.
    empty_dir = tmp_path / "empty_proj_dir"
    empty_dir.mkdir()
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "embed-wheel", str(wheel_path), "--project-dir", str(empty_dir)],
    )
    assert __main__.main() == 1
    err = capsys.readouterr().err
    assert "ERROR: No pyproject.toml, setup.cfg, or setup.py found" in err


def test_cli_embed_wheel_pregenerated_sbom(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test CLI embedding a pregenerated SBOM file with --sbom."""
    wheel_path = _make_dummy_wheel(tmp_path, "pregenpkg", "1.0.0")
    sbom_file = tmp_path / "custom_sbom.spdx3.json"
    sbom_file.write_text(
        _spdx3_json_with_subject("pregenpkg", "1.0.0"), encoding="utf-8"
    )

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


def _read_embedded_sbom(wheel_path: Path) -> bytes:
    location = find_embedded_sbom(wheel_path)
    assert location is not None
    with zipfile.ZipFile(wheel_path) as zf:
        return zf.read(location.arcname)


def test_cli_embed_wheel_multi_resolves_project_files_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Regression: ``loom embed-wheel <wheel1> <wheel2> --project-dir
    <dir>`` must resolve the project's file list (``get_wheel_files()``)
    exactly once for the whole batch, not once per wheel -- before this
    fix, every stray/ineffective build-flag ``WARNING:`` repeated once
    per wheel and a real ``--allow-build`` PEP 517 build ran once per
    wheel. See :class:`pitloom.embed.EmbedFileCache`.

    Also checks the two wheels' embedded SBOMs are byte-identical (same
    project, same name/version, same batch-wide creation metadata) --
    the fix must not change per-wheel output, only how many times the
    shared discovery work runs."""
    project_dir = tmp_path
    wheel1 = _make_ctpkg_project_and_wheel(project_dir)
    wheel2 = _make_dummy_wheel(project_dir / "dist2", "ctpkg", "1.0.0")

    with mock.patch(
        "pitloom._embed_build_sbom.get_wheel_files", side_effect=real_get_wheel_files
    ) as mocked:
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "loom",
                "embed-wheel",
                str(wheel1),
                str(wheel2),
                "--project-dir",
                str(project_dir),
            ],
        )
        assert __main__.main() == 0

    assert mocked.call_count == 1

    out = capsys.readouterr().out
    assert out.count("pitloom: embedded") == 2
    assert _read_embedded_sbom(wheel1) == _read_embedded_sbom(wheel2)


def test_cli_embed_wheel_multi_cleanup_runs_once_even_if_a_wheel_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Regression: the batch's shared ``EmbedFileCache`` cleanup must
    still run exactly once when a later wheel in the batch fails (a
    corrupt second wheel here) -- not zero times (a leak) and not once
    per wheel."""
    project_dir = tmp_path
    wheel1 = _make_ctpkg_project_and_wheel(project_dir)
    bad_wheel = project_dir / "corrupt.whl"
    bad_wheel.write_bytes(b"not a zip file")
    cleanup = mock.Mock()

    def _fake_get_wheel_files(
        *args: object, **kwargs: object
    ) -> tuple[None, list[object], mock.Mock]:
        del args, kwargs
        return None, [], cleanup

    with mock.patch(
        "pitloom._embed_build_sbom.get_wheel_files", side_effect=_fake_get_wheel_files
    ):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "loom",
                "embed-wheel",
                str(wheel1),
                str(bad_wheel),
                "--project-dir",
                str(project_dir),
            ],
        )
        assert __main__.main() == 1

    captured = capsys.readouterr()
    assert "pitloom: embedded" in captured.out
    assert "ERROR:" in captured.err
    cleanup.assert_called_once()
