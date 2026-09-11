# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI main entry point behaviour."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble import target_resolves_to_project
from pitloom.cli.commands import env as mod_env
from pitloom.cli.commands import generate as mod_generate
from pitloom.core.creation import CreationMetadata
from pitloom.ids import IdRegistry
from tests.cli.shared import _make_simple_project

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
SAFETENSORS_FIXTURE = (
    FIXTURE_DIR / "aimodels" / "safetensors" / "whisper-tiny-random.safetensors"
)
ONNX_FIXTURE = FIXTURE_DIR / "aimodels" / "onnx" / "squeezenet1.1-7.onnx"


def test_generate_command_honours_project_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """``loom generate`` must honour [tool.pitloom] settings from the target project."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "1.0.0"

[tool.pitloom]
pretty = true
describe-relationship = true
creation-datetime = "2026-04-01T00:00:00Z"
creation-comment = "configured in pyproject"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def _fake_generate(
        target: object,
        *,
        output_path: object = None,
        creation_metadata: object = None,
        pretty: object = None,
        describe_relationship: object = None,
        registry: object = None,
        **kwargs: object,
    ) -> str:
        _ = (registry, kwargs)
        captured["target"] = target
        captured["output_path"] = output_path
        captured["creation_metadata"] = creation_metadata
        captured["pretty"] = pretty
        captured["describe_relationship"] = describe_relationship
        return "{}"

    output_path = tmp_path / "out.spdx3.json"
    monkeypatch.setattr(mod_generate, "generate_project_sbom", _fake_generate)
    monkeypatch.setattr(
        sys, "argv", ["loom", "generate", str(project_dir), "-o", str(output_path)]
    )

    exit_code = __main__.main()

    assert exit_code == 0
    assert captured["target"] == project_dir
    assert captured["pretty"] is True
    assert captured["describe_relationship"] is True
    assert isinstance(captured["creation_metadata"], CreationMetadata)
    creation = captured["creation_metadata"]
    assert creation.creation_datetime == "2026-04-01T00:00:00Z"
    assert creation.creation_comment == "configured in pyproject"


def test_generate_command_default_file_headers_and_content_type_are_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """No --extract-file-header/--content-type/--content-type-method
    flags: all three must reach generate_project_sbom() as None, deferring
    to [tool.pitloom] extract-file-header / [tool.pitloom.content-type]."""
    project_dir = _make_simple_project(tmp_path)
    captured: dict[str, object] = {}

    def _fake_generate(target: object, **kwargs: object) -> str:
        _ = target
        captured["extract_file_header"] = kwargs.get("extract_file_header")
        captured["content_type"] = kwargs.get("content_type")
        captured["content_type_method"] = kwargs.get("content_type_method")
        return "{}"

    output_path = tmp_path / "out.spdx3.json"
    monkeypatch.setattr(mod_generate, "generate_project_sbom", _fake_generate)
    monkeypatch.setattr(
        sys, "argv", ["loom", "generate", str(project_dir), "-o", str(output_path)]
    )

    assert __main__.main() == 0
    assert captured["extract_file_header"] is None
    assert captured["content_type"] is None
    assert captured["content_type_method"] is None


@pytest.mark.parametrize(
    ("flag", "kwarg", "expected"),
    [
        ("--extract-file-header", "extract_file_header", True),
        ("--no-extract-file-header", "extract_file_header", False),
        ("--content-type", "content_type", True),
        ("--no-content-type", "content_type", False),
    ],
)
def test_generate_command_file_headers_content_type_flags_passed_through(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    flag: str,
    kwarg: str,
    expected: bool,
) -> None:
    """--extract-file-header/--no-extract-file-header and
    --content-type/--no-content-type must each override
    generate_project_sbom()'s corresponding param independently."""
    project_dir = _make_simple_project(tmp_path)
    captured: dict[str, object] = {}

    def _fake_generate(target: object, **kwargs: object) -> str:
        _ = target
        captured["extract_file_header"] = kwargs.get("extract_file_header")
        captured["content_type"] = kwargs.get("content_type")
        return "{}"

    output_path = tmp_path / "out.spdx3.json"
    monkeypatch.setattr(mod_generate, "generate_project_sbom", _fake_generate)
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "generate", str(project_dir), flag, "-o", str(output_path)],
    )

    assert __main__.main() == 0
    assert captured[kwarg] is expected


def test_generate_command_content_type_method_flag_passed_through(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """--content-type-method must reach generate_project_sbom() verbatim."""
    project_dir = _make_simple_project(tmp_path)
    captured: dict[str, object] = {}

    def _fake_generate(target: object, **kwargs: object) -> str:
        _ = target
        captured["content_type_method"] = kwargs.get("content_type_method")
        return "{}"

    output_path = tmp_path / "out.spdx3.json"
    monkeypatch.setattr(mod_generate, "generate_project_sbom", _fake_generate)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "generate",
            str(project_dir),
            "--content-type-method",
            "magika",
            "-o",
            str(output_path),
        ],
    )

    assert __main__.main() == 0
    assert captured["content_type_method"] == "magika"


def test_generate_command_requires_output_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Without ``-o``, ``loom generate`` must fail loudly and write
    nothing -- no default filename is guessed (regression: an earlier
    version silently wrote a hardcoded ``sbom.spdx3.json`` to whatever
    the process cwd happened to be, overwriting anything already
    there)."""
    project_dir = _make_simple_project(tmp_path)
    other_dir = tmp_path / "workdir"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)

    def _fake_generate(target: object, **kwargs: object) -> str:
        _ = (target, kwargs)
        raise AssertionError("generate() must not run without -o")

    monkeypatch.setattr(mod_generate, "generate", _fake_generate)
    monkeypatch.setattr(sys, "argv", ["loom", "generate", str(project_dir)])

    assert __main__.main() == 1
    assert "ERROR:" in capsys.readouterr().err
    assert list(other_dir.iterdir()) == []


def test_deployed_dispatches_to_generate_env_sbom(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`loom env` must dispatch to generate_env_sbom()."""
    monkeypatch.chdir(tmp_path)
    captured: dict[str, object] = {}

    def _fake_generate_env_sbom(
        output_path: object = None,
        creation_metadata: object = None,
        pretty: bool = False,
        describe_relationship: bool = False,
        registry: object = None,
        offline: bool = False,
        provenance: object = None,
        **kwargs: object,
    ) -> str:
        _ = (creation_metadata, pretty, describe_relationship, registry, offline)
        captured["output_path"] = output_path
        return "{}"

    monkeypatch.setattr(mod_env, "generate_env_sbom", _fake_generate_env_sbom)
    monkeypatch.setattr(sys, "argv", ["loom", "env"])

    assert __main__.main() == 0
    assert captured["output_path"] == tmp_path / "deployed-environment.spdx3.json"


def test_ids_generate_cli_end_to_end(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`loom ids generate` smoke test through main(): real filesystem, no
    monkeypatching of IdRegistry itself since it is fast and local."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["loom", "ids", "generate"])

    assert __main__.main() == 0

    registry_path = tmp_path / "loom-ids.json"
    assert registry_path.exists()
    registry = IdRegistry.load(registry_path)
    assert "src/mod.py" in registry.files


def test_generate_command_does_not_duplicate_project_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: for a plain project-directory target,
    `_run_generate_command()` calls `resolve_project_with_lockfile()` +
    `generate_project_sbom()` directly -- the same single-read pattern
    `loom project` uses -- rather than going through `_resolve_common_options()`'s
    own config-only peek followed by `generate()`'s real read. Only
    `resolve_project_with_lockfile()`'s own peek-then-quiet-reread can emit
    a WARNING: here (e.g. the PEP 639 transitional license/classifier
    conflict), so it must never double-fire end to end via the CLI."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0.0"\n'
        'license = "MIT"\n'
        'classifiers = ["License :: OSI Approved :: MIT License"]\n',
        encoding="utf-8",
    )
    out = tmp_path / "out.spdx3.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "generate", str(project_dir), "-o", str(out), "--offline"],
    )

    with caplog.at_level(logging.WARNING):
        assert __main__.main() == 0

    assert caplog.text.count("PEP 639 transitional state") == 1


def test_generate_command_sdist_target_does_not_drop_sibling_project_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: an sdist-archive target isn't a directory, so it takes
    `_run_generate_command()`'s fallback branch -- a plain, always
    non-quiet `_resolve_common_options()` peek followed by `generate()`'s
    real read. That real read (`generate_project_sbom()` -> `read_sdist()`)
    never touches `read_pyproject()` at all -- it parses the archive's own
    internal PKG-INFO, not the *sibling* pyproject.toml the peek read to
    resolve [tool.pitloom] config -- so the peek's WARNING: is this
    invocation's only possible emission of it and must not be lost."""
    import io
    import tarfile

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0.0"\n'
        'license = "MIT"\n'
        'classifiers = ["License :: OSI Approved :: MIT License"]\n',
        encoding="utf-8",
    )
    sdist_path = tmp_path / "demo-1.0.0.tar.gz"
    pkg_info = b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0.0\n"
    with tarfile.open(sdist_path, "w:gz") as tf:
        ti = tarfile.TarInfo(name="demo-1.0.0/PKG-INFO")
        ti.size = len(pkg_info)
        tf.addfile(ti, io.BytesIO(pkg_info))

    out = tmp_path / "out.spdx3.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "generate", str(sdist_path), "-o", str(out), "--offline"],
    )

    with caplog.at_level(logging.WARNING):
        assert __main__.main() == 0

    assert caplog.text.count("PEP 639 transitional state") == 1


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (".", True),
        ("some/project/dir", True),
        ("archive.tar.gz", True),
        ("env", False),
        ("environment", False),
        ("--env", False),
        ("package.whl", False),
        ("PACKAGE.WHL", False),
        ("https://huggingface.co/mistralai/Mistral-7B-v0.1", False),
    ],
)
def test_target_resolves_to_project(target: str, expected: bool) -> None:
    """Non-filesystem-dependent target shapes classify without touching disk."""
    assert target_resolves_to_project(target) is expected


def test_target_resolves_to_project_model_file(tmp_path: Path) -> None:
    """A real on-disk file with a recognized model extension is not a
    project target -- matches generate()'s own dispatch check, which also
    requires target_path.is_file()."""
    model_file = tmp_path / "weights.safetensors"
    model_file.write_bytes(b"")
    assert target_resolves_to_project(model_file) is False

    non_model_file = tmp_path / "weights.safetensors.txt"
    non_model_file.write_bytes(b"")
    assert target_resolves_to_project(non_model_file) is True
