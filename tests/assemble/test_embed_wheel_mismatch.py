# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for `embed-wheel --sbom`'s pre-embed name/version cross-check
against the target wheel's own METADATA, and `--allow-mismatch`.

See also:
- :mod:`tests.assemble.test_embed_cli` -- this module's sibling, split off
  once the mismatch-check tests pushed it past its size guideline; the
  other `embed-wheel`/`wheel --embed` CLI tests live there.
- :mod:`tests.assemble.test_verify_wheel_cli` for the post-hoc,
  `verify-wheel`-side counterpart of the same cross-check.
- :mod:`tests.assemble.test_sbom_format` for unit tests of the shared
  comparison logic (`compare_name_version`/`check_spdx3_name_version`)
  both sides call.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

from pitloom import __main__

from .conftest import _make_dummy_wheel, _spdx3_json_with_subject


def test_cli_embed_wheel_sbom_name_mismatch_aborts_before_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A --sbom whose declared name doesn't match the wheel's own
    METADATA aborts the embed before anything is written -- no
    .dist-info/sboms/ entry ends up in the wheel, and the command exits
    1 with an ERROR:, not a WARNING:."""
    wheel_path = _make_dummy_wheel(tmp_path, "realname", "1.0.0")
    original_bytes = wheel_path.read_bytes()
    sbom_file = tmp_path / "sbom.spdx3.json"
    sbom_file.write_text(
        _spdx3_json_with_subject("wrongname", "1.0.0"), encoding="utf-8"
    )

    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "embed-wheel", str(wheel_path), "--sbom", str(sbom_file)],
    )
    assert __main__.main() == 1

    captured = capsys.readouterr()
    assert "ERROR:" in captured.err
    assert "name: wheel declares 'realname', SBOM declares 'wrongname'" in captured.err
    assert "pitloom: embedded" not in captured.out
    assert wheel_path.read_bytes() == original_bytes


def test_cli_embed_wheel_sbom_mismatch_one_wheel_does_not_abort_batch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A --sbom mismatch on one wheel in a multi-wheel embed reports that
    wheel's failure and continues to the next wheel, instead of the
    ValueError propagating out of the loop and aborting the whole batch
    (which would silently skip every wheel after the failing one)."""
    dist_dir = tmp_path / "dist"
    bad_wheel = _make_dummy_wheel(dist_dir, "badpkg", "1.0.0")
    good_wheel = _make_dummy_wheel(dist_dir, "goodpkg", "1.0.0")
    sbom_file = tmp_path / "sbom.spdx3.json"
    # Matches good_wheel's name/version, not bad_wheel's.
    sbom_file.write_text(_spdx3_json_with_subject("goodpkg", "1.0.0"), encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "embed-wheel",
            str(bad_wheel),
            str(good_wheel),
            "--sbom",
            str(sbom_file),
        ],
    )
    assert __main__.main() == 1

    captured = capsys.readouterr()
    assert "ERROR:" in captured.err
    assert "badpkg" in captured.err
    assert "pitloom: embedded" in captured.out
    assert "goodpkg-1.0.0-py3-none-any.whl" in captured.out

    with zipfile.ZipFile(bad_wheel) as zf:
        assert not any(n.endswith(".spdx3.json") for n in zf.namelist())
    with zipfile.ZipFile(good_wheel) as zf:
        assert any(n.endswith(".spdx3.json") for n in zf.namelist())


def test_cli_embed_wheel_sbom_mismatch_allow_mismatch_embeds_anyway(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--allow-mismatch downgrades the same mismatch to a WARNING and lets
    the embed proceed -- for CI/automation that wants best-effort
    embedding instead of a hard refusal."""
    wheel_path = _make_dummy_wheel(tmp_path, "realname2", "1.0.0")
    sbom_file = tmp_path / "sbom.spdx3.json"
    sbom_file.write_text(
        _spdx3_json_with_subject("wrongname2", "1.0.0"), encoding="utf-8"
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
            "--allow-mismatch",
        ],
    )
    assert __main__.main() == 0

    captured = capsys.readouterr()
    assert "WARNING:" in captured.err
    assert (
        "name: wheel declares 'realname2', SBOM declares 'wrongname2'" in captured.err
    )
    assert "pitloom: embedded" in captured.out

    with zipfile.ZipFile(wheel_path, "r") as zf:
        assert any(n.endswith(".spdx3.json") and "/sboms/" in n for n in zf.namelist())


def test_cli_embed_wheel_sbom_matching_name_version_no_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A --sbom whose declared name/version matches the wheel's METADATA
    embeds cleanly with no WARNING/ERROR at all."""
    wheel_path = _make_dummy_wheel(tmp_path, "matchingpkg", "2.3.4")
    sbom_file = tmp_path / "sbom.spdx3.json"
    sbom_file.write_text(
        _spdx3_json_with_subject("matchingpkg", "2.3.4"), encoding="utf-8"
    )

    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "embed-wheel", str(wheel_path), "--sbom", str(sbom_file)],
    )
    assert __main__.main() == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert "pitloom: embedded" in captured.out


def test_cli_embed_wheel_no_sbom_flag_skips_cross_check(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A Pitloom-generated SBOM (no --sbom) is never cross-checked -- it's
    built from the same wheel METADATA, so it can't diverge; the check
    only applies to an externally-supplied --sbom."""
    fixture_dir = (
        Path(__file__).parent.parent
        / "fixtures"
        / "projects"
        / "sampleproject-hatchling"
    )
    wheel_path = _make_dummy_wheel(tmp_path, "genpkg", "1.0.0")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "embed-wheel",
            str(wheel_path),
            "--project-dir",
            str(fixture_dir),
        ],
    )
    assert __main__.main() == 0

    captured = capsys.readouterr()
    assert "pitloom: embedded" in captured.out
    assert "SBOM/wheel" not in captured.err
