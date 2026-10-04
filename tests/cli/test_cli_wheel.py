# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI main entry point behaviour."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest
import rfc8785

from pitloom import __main__
from pitloom.__about__ import __version__
from pitloom.cli.commands import wheel as mod_wheel
from pitloom.cli.commands._embed_wheel_batch import report_embed_result
from pitloom.core.project import ProjectMetadata
from pitloom.id_registry import IdRegistry
from pitloom.logging_config import configure_logging
from tests.assemble.conftest import _make_dummy_wheel
from tests.kv_helpers import info_kv, kv_stdout, sbom_output_path
from tests.warning_helpers import count_naming, stderr_warnings

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
SAFETENSORS_FIXTURE = (
    FIXTURE_DIR / "aimodels" / "safetensors" / "whisper-tiny-random.safetensors"
)
ONNX_FIXTURE = FIXTURE_DIR / "aimodels" / "onnx" / "squeezenet1.1-7.onnx"


def _make_wheel(tmp_path: Path, name: str, version: str) -> Path:
    """Build a minimal .whl containing just a METADATA file."""
    wheel_path = tmp_path / f"{name}-{version}-py3-none-any.whl"
    metadata_body = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr(f"{name}-{version}.dist-info/METADATA", metadata_body)
    return wheel_path


def test_wheel_command_dispatches_with_its_options(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`loom wheel foo.whl` dispatches to generate_wheel_sbom(), not the
    AI-model or Hugging Face paths, and forwards
    --max-source-metadata-bytes like every generate-family command."""
    monkeypatch.chdir(tmp_path)
    wheel_path = _make_wheel(tmp_path, "pkg", "1.0.0")
    captured: dict[str, object] = {}

    def _fake_generate(
        wheel_path_arg: Path, **kwargs: object
    ) -> tuple[str, ProjectMetadata]:
        captured.update(kwargs, wheel_path=wheel_path_arg)
        return "{}", ProjectMetadata(name="pkg")

    monkeypatch.setattr(mod_wheel, "generate_wheel_sbom_with_metadata", _fake_generate)
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "wheel", str(wheel_path), "--max-source-metadata-bytes", "5000"],
    )

    assert __main__.main() == 0
    assert captured["wheel_path"] == wheel_path.resolve()
    assert captured["max_source_metadata_bytes"] == 5000


def test_wheel_command_nonexistent_and_verbose(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Non-existent wheel returns code 1; verbose mode prints wheel info."""
    monkeypatch.setattr(sys, "argv", ["loom", "wheel", str(tmp_path / "missing.whl")])
    assert __main__.main() == 1
    err = capsys.readouterr().err
    assert "ERROR: wheel file not found" in err

    # Verbose mode on valid wheel
    wheel_path = _make_wheel(tmp_path, "pkg_v", "1.0.0")
    monkeypatch.setattr(
        mod_wheel,
        "generate_wheel_sbom_with_metadata",
        lambda *a, **k: ("{}", ProjectMetadata(name="pkg_v")),
    )
    monkeypatch.setattr(sys, "argv", ["loom", "wheel", "-v", str(wheel_path)])
    assert __main__.main() == 0
    captured = capsys.readouterr()
    verbose = info_kv(captured.err)
    assert verbose["PITLOOM_VERSION"] == __version__
    assert verbose["WHEEL_FILE"] == str(wheel_path)
    assert sbom_output_path(captured.out) == verbose["OUTPUT_PATH"]


def test_report_embed_result(capsys: pytest.CaptureFixture[str]) -> None:
    """report_embed_result prints one WHEEL=/SBOM= data line to stdout and
    the two INFO: side-effect lines to stderr, matching every other
    INFO:/WARNING:/ERROR: line."""
    # The two side-effect lines go through logging (see CLAUDE.md's "CLI
    # output" section), unlike the confirmation line above them -- calling
    # this function directly, without going through __main__.main(), skips
    # the configure_logging() call that normally wires INFO: up to stderr.
    configure_logging()

    report_embed_result(
        "sbom.spdx.json",
        "pkg.whl",
        ("old_sbom.spdx.json",),
        timestamp_floored=True,
    )
    captured = capsys.readouterr()
    assert kv_stdout(captured.out) == [{"WHEEL": "pkg.whl", "SBOM": "sbom.spdx.json"}]
    assert "removed stale SBOM old_sbom.spdx.json" in captured.err
    assert "timestamp was before 1980" in captured.err


def test_report_embed_result_escapes_control_characters(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report_embed_result("sboms/ev\x1b[31mil\n x.json", "p\x1bkg.whl", ())

    out = capsys.readouterr().out
    assert out.count("\n") == 1 and "\x1b" not in out
    assert "\\x1b[31mil" in out


def test_embed_wheel_prints_one_clean_line_for_a_hostile_metadata_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel = tmp_path / "pkg-1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr(
            "pkg-1.0.dist-info/METADATA", "Name: ev\x1b[31mil\n x\nVersion: 1.0\n"
        )
    monkeypatch.setattr(sys, "argv", ["loom", "embed-wheel", str(wheel)])

    assert __main__.main() == 0

    out = capsys.readouterr().out
    assert out.splitlines() == [
        "WHEEL=pkg-1.0-py3-none-any.whl "
        "SBOM=pkg-1.0.dist-info/sboms/ev_[31mil__x-1.0.spdx3.json"
    ]


def _embedded(wheel: Path) -> bytes:
    with zipfile.ZipFile(wheel) as archive:
        (name,) = [n for n in archive.namelist() if "/sboms/" in n]
        return archive.read(name)


@pytest.mark.parametrize("with_output", [False, True], ids=["embed", "embed-o"])
def test_wheel_embed_embeds_the_canonical_sbom_embed_wheel_does(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    with_output: bool,
) -> None:
    """``wheel --embed`` embeds what ``embed-wheel`` does: RFC 8785 JSON, no
    relationship descriptions, no registry harvest. Each such flag warns
    once, in ``embed-wheel``'s wording; ``-o`` writes a copy of it."""
    wheel = _make_dummy_wheel(tmp_path / "w", "demo", "1.0.0")
    registry = tmp_path / "ids.json"
    IdRegistry(namespace="https://example.org/ns", path=registry).save()
    seeded = registry.read_bytes()
    flags = ["--pretty", "--describe-relationship", "--update-id-registry"]
    argv = ["wheel", str(wheel), "--embed", "--id-registry", str(registry), *flags]
    output = tmp_path / "copy.json"
    if with_output:
        argv += ["-o", str(output)]
    monkeypatch.setattr(sys, "argv", ["loom", *argv, "--offline"])

    assert __main__.main() == 0

    embedded = _embedded(wheel)
    assert embedded == rfc8785.dumps(json.loads(embedded))
    relationships = [
        node for node in json.loads(embedded)["@graph"] if "relationshipType" in node
    ]
    assert relationships
    assert not any("description" in node for node in relationships)
    assert registry.read_bytes() == seeded
    warnings = stderr_warnings(capsys.readouterr().err)
    for flag in flags:
        assert count_naming(warnings, flag) == 1, (flag, warnings)
    if with_output:
        assert output.read_bytes() == embedded


def test_wheel_without_embed_still_honours_pretty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Non-vacuous: the same flags are live when nothing is embedded."""
    wheel = _make_dummy_wheel(tmp_path / "w", "demo", "1.0.0")
    output = tmp_path / "o.json"
    argv = ["loom", "wheel", str(wheel), "--pretty", "--offline", "-o", str(output)]
    monkeypatch.setattr(sys, "argv", argv)
    assert __main__.main() == 0
    assert output.read_text(encoding="utf-8").startswith("{\n")
    assert not stderr_warnings(capsys.readouterr().err)
