# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for `pitloom verify-wheel` (PEP 770 location + recommended
extension -- structural check only, no schema/SHACL content validation).

See also:
- :mod:`tests.assemble.test_validate_wheel_cli` for the content-check
  counterpart.
- :mod:`tests.assemble.test_embed_cli` for `embed-wheel`'s own CLI tests,
  including its `--verify`/`--validate` convenience flags.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

from pitloom import __main__

from .conftest import _SAMPLE_SPDX3_JSON, _make_dummy_wheel


def _embed_sbom(wheel_path: Path, *, sbom_basename: str) -> None:
    """Add a `sboms/` entry to *wheel_path* under an exact basename.

    Unlike `embed-wheel` itself (which always appends `.spdx3.json`), this
    writes whatever basename is given verbatim -- needed to construct a
    deliberately non-conventional-extension fixture that `embed-wheel`'s
    own self-correction makes otherwise unreachable.
    """
    with zipfile.ZipFile(wheel_path) as zf:
        dist_info = next(
            n.split("/")[0] for n in zf.namelist() if n.endswith(".dist-info/METADATA")
        )
    with zipfile.ZipFile(wheel_path, "a") as zf:
        zf.writestr(f"{dist_info}/sboms/{sbom_basename}", _SAMPLE_SPDX3_JSON)


def test_verify_wheel_correct_extension_ok(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A recommended-extension SBOM passes with no WARNING, exit 0."""
    wheel_path = _make_dummy_wheel(tmp_path, "okpkg", "1.0.0")
    _embed_sbom(wheel_path, sbom_basename="okpkg-1.0.0.spdx3.json")

    monkeypatch.setattr(sys, "argv", ["loom", "verify-wheel", str(wheel_path)])
    assert __main__.main() == 0

    captured = capsys.readouterr()
    assert "pitloom verify-wheel: 1 wheel(s) OK" in captured.out
    assert captured.err == ""


def test_verify_wheel_wrong_extension_warns(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A non-recommended extension WARNs but still exits 0 -- not fatal."""
    wheel_path = _make_dummy_wheel(tmp_path, "warnpkg", "1.0.0")
    _embed_sbom(wheel_path, sbom_basename="sbom.json")

    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "verify-wheel", str(wheel_path), "--sbom-basename", "sbom.json"],
    )
    assert __main__.main() == 0

    captured = capsys.readouterr()
    assert "WARNING:" in captured.err
    assert "recommended '.spdx3.json' extension" in captured.err
    assert "pitloom verify-wheel: 1 wheel(s) OK" in captured.out


def test_verify_wheel_missing_sbom_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No `sboms/` entry at all -> ERROR, exit 1."""
    wheel_path = _make_dummy_wheel(tmp_path, "nosbompkg", "1.0.0")

    monkeypatch.setattr(sys, "argv", ["loom", "verify-wheel", str(wheel_path)])
    assert __main__.main() == 1

    captured = capsys.readouterr()
    assert "ERROR: no SBOM found under .dist-info/sboms/" in captured.err


def test_verify_wheel_sbom_basename_exact_match(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Two ambiguous SBOMs are fine when --sbom-basename disambiguates."""
    wheel_path = _make_dummy_wheel(tmp_path, "ambigpkg", "1.0.0")
    _embed_sbom(wheel_path, sbom_basename="a.spdx3.json")
    _embed_sbom(wheel_path, sbom_basename="b.spdx3.json")

    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "verify-wheel", str(wheel_path), "--sbom-basename", "a.spdx3.json"],
    )
    assert __main__.main() == 0
    assert "pitloom verify-wheel: 1 wheel(s) OK" in capsys.readouterr().out


def test_verify_wheel_ambiguous_without_basename_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Multiple SBOMs with no --sbom-basename to disambiguate -> ERROR."""
    wheel_path = _make_dummy_wheel(tmp_path, "ambigpkg2", "1.0.0")
    _embed_sbom(wheel_path, sbom_basename="a.spdx3.json")
    _embed_sbom(wheel_path, sbom_basename="b.spdx3.json")

    monkeypatch.setattr(sys, "argv", ["loom", "verify-wheel", str(wheel_path)])
    assert __main__.main() == 1
    assert "Multiple SBOMs found" in capsys.readouterr().err


def test_verify_wheel_nested_sboms_entry_not_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A non-SBOM file nested under sboms/ (e.g. sboms/extra/notes.txt)
    doesn't count as a second candidate -- only direct children of
    sboms/ are SBOMs, so one real SBOM plus a nested entry isn't
    ambiguous."""
    wheel_path = _make_dummy_wheel(tmp_path, "nestedpkg", "1.0.0")
    _embed_sbom(wheel_path, sbom_basename="nestedpkg-1.0.0.spdx3.json")
    with zipfile.ZipFile(wheel_path) as zf:
        dist_info = next(
            n.split("/")[0] for n in zf.namelist() if n.endswith(".dist-info/METADATA")
        )
    with zipfile.ZipFile(wheel_path, "a") as zf:
        zf.writestr(f"{dist_info}/sboms/extra/notes.txt", "not an sbom")

    monkeypatch.setattr(sys, "argv", ["loom", "verify-wheel", str(wheel_path)])
    assert __main__.main() == 0

    captured = capsys.readouterr()
    assert "pitloom verify-wheel: 1 wheel(s) OK" in captured.out
    assert "Multiple SBOMs found" not in captured.err


def test_verify_wheel_unrecognized_format_warns(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A non-JSON-LD embedded file has no detected format -> WARNING,
    not ERROR -- unrecognized isn't the same as a location problem."""
    wheel_path = _make_dummy_wheel(tmp_path, "otherpkg", "1.0.0")
    with zipfile.ZipFile(wheel_path) as zf:
        dist_info = next(
            n.split("/")[0] for n in zf.namelist() if n.endswith(".dist-info/METADATA")
        )
    with zipfile.ZipFile(wheel_path, "a") as zf:
        zf.writestr(f"{dist_info}/sboms/otherpkg-1.0.0.spdx3.json", "not valid json")

    monkeypatch.setattr(sys, "argv", ["loom", "verify-wheel", str(wheel_path)])
    assert __main__.main() == 0

    captured = capsys.readouterr()
    assert "WARNING: " in captured.err
    assert "unrecognized SBOM format" in captured.err
    assert "pitloom verify-wheel: 1 wheel(s) OK" in captured.out


def test_verify_wheel_sbom_basename_not_found_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--sbom-basename given but no matching entry exists -> ERROR, exit 1."""
    wheel_path = _make_dummy_wheel(tmp_path, "nomatchpkg", "1.0.0")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "verify-wheel",
            str(wheel_path),
            "--sbom-basename",
            "missing.spdx3.json",
        ],
    )
    assert __main__.main() == 1

    captured = capsys.readouterr()
    assert "ERROR: no SBOM found under .dist-info/sboms/" in captured.err
    assert "matching 'missing.spdx3.json'" in captured.err


def test_verify_wheel_permission_error_reported_per_wheel(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An OSError opening the wheel (e.g. permission denied) is reported as
    ERROR per-wheel, not left to propagate and abort the whole batch.

    Exercises _open_wheel_zip's OSError-propagates-unwrapped contract
    together with _locate_embedded_sbom_or_report's `except (ValueError,
    OSError)` -- the CLI layer doesn't need the type distinction a library
    caller might, so both are caught and reported the same way here."""
    wheel_path = _make_dummy_wheel(tmp_path, "unreadablepkg", "1.0.0")

    def _raise_permission_error(*_args: object, **_kwargs: object) -> zipfile.ZipFile:
        raise PermissionError(f"[Errno 13] Permission denied: '{wheel_path}'")

    monkeypatch.setattr(
        "pitloom._wheel_sbom_location.zipfile.ZipFile", _raise_permission_error
    )
    monkeypatch.setattr(sys, "argv", ["loom", "verify-wheel", str(wheel_path)])
    assert __main__.main() == 1

    captured = capsys.readouterr()
    assert "ERROR: [Errno 13] Permission denied" in captured.err


def test_verify_wheel_no_wheel_files_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No wheel file matches the given path -> ERROR, exit 1, before any check."""
    monkeypatch.setattr(
        sys, "argv", ["loom", "verify-wheel", str(tmp_path / "nope.whl")]
    )
    assert __main__.main() == 1

    captured = capsys.readouterr()
    assert "ERROR: wheel file not found" in captured.err


def test_verify_wheel_multiple_wheels_mixed_pass_fail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One good wheel + one missing-SBOM wheel -> overall exit 1, but the
    good wheel's result isn't silently dropped from the run."""
    dist_dir = tmp_path / "dist"
    good = _make_dummy_wheel(dist_dir, "good", "1.0.0")
    _embed_sbom(good, sbom_basename="good-1.0.0.spdx3.json")
    bad = _make_dummy_wheel(dist_dir, "bad", "1.0.0")

    monkeypatch.setattr(sys, "argv", ["loom", "verify-wheel", str(good), str(bad)])
    assert __main__.main() == 1

    captured = capsys.readouterr()
    assert "ERROR: no SBOM found" in captured.err
    assert "bad-1.0.0-py3-none-any.whl" in captured.err
    # No success summary when any wheel failed.
    assert "wheel(s) OK" not in captured.out
