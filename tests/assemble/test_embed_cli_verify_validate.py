# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.embed's CLI --verify/--validate convenience flags
(embed-wheel --verify/--validate).

See also:
- :mod:`tests.assemble.test_embed_cli` for the rest of the CLI surface
  (embed-wheel / wheel --embed) this module was split from.
- :mod:`tests.assemble.test_embed_overrides` for overrides and standalone build path.
- :mod:`tests.assemble.test_embed_core` for core embed logic.
- :mod:`tests.assemble.test_embed_internals` for low-level ZIP manipulation.
- :mod:`tests.assemble.test_embed_wheel_mismatch` for `--sbom`'s pre-embed
  name/version cross-check and `--allow-mismatch`.
"""

from __future__ import annotations

import dataclasses
import sys
import zipfile
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble import EmbeddedSbomLocation, find_embedded_sbom

from .conftest import _make_dummy_wheel, _spdx3_json_with_subject


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
    sbom_file.write_text(
        _spdx3_json_with_subject("verifyflag", "1.0.0"), encoding="utf-8"
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
            "--verify",
        ],
    )
    assert __main__.main() == 0

    captured = capsys.readouterr()
    assert "pitloom: embedded" in captured.out
    assert "WARNING:" not in captured.err
    assert "ERROR:" not in captured.err


def test_cli_embed_wheel_verify_reports_when_post_embed_lookup_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--verify's post-embed re-lookup can itself fail to find what was
    just embedded (`_locate_and_detect` returning `None`, which already
    printed its own ERROR:) -- `_run_post_embed_checks` must surface that
    as an overall failure (exit 1) rather than silently treating it as
    success, even though the embed itself already succeeded."""
    wheel_path = _make_dummy_wheel(tmp_path, "lookupfailpkg", "1.0.0")
    sbom_file = tmp_path / "sbom.spdx3.json"
    sbom_file.write_text(
        _spdx3_json_with_subject("lookupfailpkg", "1.0.0"), encoding="utf-8"
    )

    monkeypatch.setattr(
        "pitloom.cli.commands.embed_wheel._locate_and_detect", lambda *a, **k: None
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
            "--verify",
        ],
    )
    assert __main__.main() == 1

    captured = capsys.readouterr()
    assert "pitloom: embedded" in captured.out


def test_cli_embed_wheel_verify_rereads_wheel_from_disk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--verify genuinely re-reads the just-written wheel from disk (via
    find_embedded_sbom) rather than trusting the pre-write SBOM string --
    the whole point of --verify/--validate is confirming what actually
    landed in the wheel, not what Pitloom intended to write.

    Proven by patching find_embedded_sbom to return a location with a
    deliberately wrong extension: the WARNING reflects that patched
    on-disk value, which could only happen if the disk-lookup path is
    genuinely exercised, not bypassed with in-memory data."""
    wheel_path = _make_dummy_wheel(tmp_path, "rereadpkg", "1.0.0")
    sbom_file = tmp_path / "sbom.spdx3.json"
    sbom_file.write_text(
        _spdx3_json_with_subject("rereadpkg", "1.0.0"), encoding="utf-8"
    )

    def _wrong_extension(
        wheel_path_arg: Path, sbom_filename: str | None = None
    ) -> EmbeddedSbomLocation | None:
        location = find_embedded_sbom(wheel_path_arg, sbom_filename)
        if location is None:
            return None
        return dataclasses.replace(location, arcname="on-disk-value.txt")

    monkeypatch.setattr(
        "pitloom.cli.commands.utils.find_embedded_sbom", _wrong_extension
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
            "--verify",
        ],
    )
    assert __main__.main() == 0

    captured = capsys.readouterr()
    assert "pitloom: embedded" in captured.out
    assert "on-disk-value.txt doesn't use the recommended" in captured.err


def test_cli_embed_wheel_verify_validate_share_one_disk_lookup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--verify --validate together locate the embedded SBOM from disk
    exactly ONCE, not once per check -- still a genuine disk read (unlike
    the abandoned in-memory shortcut, see test_cli_embed_wheel_verify_
    rereads_wheel_from_disk above), just not duplicated across the two
    checks."""
    call_count = 0
    real_find_embedded_sbom = find_embedded_sbom

    def _counting_find_embedded_sbom(
        wheel_path_arg: Path, sbom_filename: str | None = None
    ) -> EmbeddedSbomLocation | None:
        nonlocal call_count
        call_count += 1
        return real_find_embedded_sbom(wheel_path_arg, sbom_filename)

    monkeypatch.setattr(
        "pitloom.cli.commands.utils.find_embedded_sbom", _counting_find_embedded_sbom
    )

    wheel_path = _make_dummy_wheel(tmp_path, "sharedlookup", "1.0.0")
    sbom_file = tmp_path / "sbom.spdx3.json"
    # Unrecognized format so --validate WARN-and-skips rather than reaching
    # spdx3_validate's network-dependent schema fetch -- this test is about
    # the shared-lookup property, not content validation.
    sbom_file.write_text("not valid spdx3 json-ld", encoding="utf-8")

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
            "--validate",
        ],
    )
    assert __main__.main() == 0

    captured = capsys.readouterr()
    assert "pitloom: embedded" in captured.out
    assert call_count == 1


def test_cli_embed_wheel_verify_validate_share_one_format_detection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--verify --validate together detect the embedded SBOM's format
    exactly ONCE, not once per check -- same dedup as the disk-lookup
    sharing above (see test_cli_embed_wheel_verify_validate_share_one_
    disk_lookup), but for `detect_sbom_format()` instead of the disk read
    itself. Without this, a future split of `_run_post_embed_checks` back
    into two independent calls would silently reintroduce the double
    parse with no test failing."""
    from pitloom import _sbom_format

    call_count = 0
    real_detect_sbom_format = _sbom_format.detect_sbom_format

    def _counting_detect_sbom_format(data: bytes) -> str | None:
        nonlocal call_count
        call_count += 1
        return real_detect_sbom_format(data)

    # embed_wheel.py/verify_wheel.py/validate_wheel.py all locate+detect via
    # the single shared `_locate_and_detect()` in cli/commands/utils.py, so
    # patching its one `detect_sbom_format` binding catches a regression
    # anywhere in that shared path, not just embed_wheel.py's own call.
    monkeypatch.setattr(
        "pitloom.cli.commands.utils.detect_sbom_format", _counting_detect_sbom_format
    )

    wheel_path = _make_dummy_wheel(tmp_path, "sharedformat", "1.0.0")
    sbom_file = tmp_path / "sbom.spdx3.json"
    # Unrecognized format so --validate WARN-and-skips rather than reaching
    # spdx3_validate's network-dependent schema fetch -- this test is about
    # the shared-detection property, not content validation.
    sbom_file.write_text("not valid spdx3 json-ld", encoding="utf-8")

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
            "--validate",
        ],
    )
    assert __main__.main() == 0

    captured = capsys.readouterr()
    assert "pitloom: embedded" in captured.out
    assert call_count == 1


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


def test_cli_embed_wheel_validate_flag_skips_unrecognized_format(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--validate against an embedded SBOM with no registered validator
    for its (unrecognized) format WARNs and skips -- that's not the same
    as failing, so the command still exits 0."""
    wheel_path = _make_dummy_wheel(tmp_path, "skipflag", "1.0.0")
    sbom_file = tmp_path / "notspdx3.spdx3.json"
    sbom_file.write_text('{"foo": "bar"}', encoding="utf-8")

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
    assert __main__.main() == 0

    captured = capsys.readouterr()
    assert "pitloom: embedded" in captured.out
    assert "WARNING:" in captured.err
    assert "no validator registered" in captured.err
    assert "ERROR:" not in captured.err
