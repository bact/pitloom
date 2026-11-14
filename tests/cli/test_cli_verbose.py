# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI main entry point behaviour."""

from __future__ import annotations

import logging
import sys
from pathlib import Path, PurePath, PurePosixPath

import pytest

from pitloom import __main__
from pitloom.cli.commands import project as mod_project
from pitloom.cli.kv_output import log_kv
from pitloom.cli.options import (
    _ResolvedCreationMetadata,
    _ResolvedCreators,
    _ResolvedTools,
    _ResolvedValue,
)
from pitloom.cli.verbose import _build_creation_option_rows
from pitloom.core.creation import Creator, Tool
from pitloom.core.given_path import GivenPath, TypedPath
from pitloom.logging_config import configure_logging
from tests.assemble.conftest import _make_dummy_wheel
from tests.kv_helpers import info_options, sbom_output_path

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
SAFETENSORS_FIXTURE = (
    FIXTURE_DIR / "aimodels" / "safetensors" / "whisper-tiny-random.safetensors"
)
ONNX_FIXTURE = FIXTURE_DIR / "aimodels" / "onnx" / "squeezenet1.1-7.onnx"


def test_verbose_shows_target_config_file_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verbose output must show the target project's config file path."""
    current_dir = tmp_path / "current"
    current_dir.mkdir()
    (current_dir / "pyproject.toml").write_text(
        """
[project]
name = "current"
version = "0.1.0"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    target_dir = tmp_path / "target"
    target_dir.mkdir()
    target_pyproject = target_dir / "pyproject.toml"
    target_pyproject.write_text(
        """
[project]
name = "target"
version = "0.1.0"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    def _fake_generate_project_sbom(*_args: object, **_kwargs: object) -> str:
        return "{}"

    monkeypatch.chdir(current_dir)
    monkeypatch.setattr(
        mod_project, "generate_project_sbom", _fake_generate_project_sbom
    )
    monkeypatch.setattr(sys, "argv", ["loom", "project", str(target_dir), "-v"])

    exit_code = __main__.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    rows = info_options(captured.err)
    assert rows["config_file"]["VALUE"] == str(target_pyproject)
    assert rows["creation_datetime"]["VALUE"] == "None"
    assert rows["creation_comment"]["VALUE"] == "'Generated via Pitloom CLI'"
    assert rows["creation_comment"]["SOURCE"] == "default"
    # Every row is OPTION, SOURCE, VALUE in that order, VALUE last.
    assert all(list(row) == ["OPTION", "SOURCE", "VALUE"] for row in rows.values())
    assert sbom_output_path(captured.out) == rows["output_path"]["VALUE"]


def test_build_creation_option_rows_full() -> None:
    creation = _ResolvedCreationMetadata(
        creators=_ResolvedCreators(
            value=[Creator(name="Alice", type="person", email="alice@example.com")],
            source="cli",
        ),
        tools=_ResolvedTools(value=[], source="default"),
        creation_datetime=_ResolvedValue(value="2026-08-17T00:00:00Z", source="cli"),
        creation_comment=_ResolvedValue(value="Test comment", source="cli"),
    )

    rows = _build_creation_option_rows(
        creation,
        eff_pretty=True,
        pretty_src="cli",
        eff_desc=False,
        desc_src="cli",
    )

    keys = [r[0] for r in rows]
    assert "creator[1]" in keys
    assert "tools" in keys
    assert "creation_datetime" in keys
    assert "creation_comment" in keys

    # Test None tools
    creation_none_tools = _ResolvedCreationMetadata(
        creators=_ResolvedCreators(value=[], source="default"),
        tools=_ResolvedTools(value=None, source="default"),
        creation_datetime=_ResolvedValue(value=None, source="default"),
        creation_comment=_ResolvedValue(value=None, source="default"),
    )
    rows_none = _build_creation_option_rows(
        creation_none_tools,
        eff_pretty=True,
        pretty_src="cli",
        eff_desc=False,
        desc_src="cli",
    )
    assert any(r[1].startswith("None") for r in rows_none if r[0] == "tools")
    assert any(r[1].startswith("[]") for r in rows_none if r[0] == "creators")

    # Test tools list
    creation_tools_list = _ResolvedCreationMetadata(
        creators=_ResolvedCreators(value=[], source="default"),
        tools=_ResolvedTools(value=[Tool(name="MyTool")], source="default"),
        creation_datetime=_ResolvedValue(value=None, source="default"),
        creation_comment=_ResolvedValue(value=None, source="default"),
    )
    rows_list = _build_creation_option_rows(
        creation_tools_list,
        eff_pretty=True,
        pretty_src="cli",
        eff_desc=False,
        desc_src="cli",
    )
    assert any(r[0] == "tool[1]" for r in rows_list)


@pytest.mark.parametrize(
    "argv",
    [["enrich", "m.gguf"], ["wheel", "demo_pkg-1.0.0-py3-none-any.whl"]],
    ids=["enrich", "wheel"],
)
def test_verbose_names_the_project_dir_as_typed_and_masked(
    argv: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``-v`` names ``--project-dir`` as typed (its ``//`` kept), a URL in
    it without its credentials, whatever the command then says of it."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "m.gguf").write_bytes(b"x")
    _make_dummy_wheel(tmp_path)
    typed = "https://u:SECRET@h/x"
    monkeypatch.setattr(sys, "argv", ["loom", *argv, "-v", "--project-dir", typed])
    __main__.main()
    err = capsys.readouterr().err
    assert "INFO: PROJECT_DIR=https://***:***@h/x\n" in err
    assert "SECRET" not in err


def test_log_kv_writes_a_path_as_given_and_masked(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging()
    logging.getLogger("pitloom").setLevel(logging.INFO)
    log_kv(
        A=TypedPath("ftp://u:SECRET@h//x"),
        B=PurePath("x"),
        C="https://h/?token=SECRET",
        D=3,
    )
    assert capsys.readouterr().err == (
        "INFO: A=ftp://***:***@h//x B=x C=https://h/?token=*** D=3\n"
    )


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        (["https://u:SECRET@h/x"], "['https://***:***@h/x']"),
        (
            (PurePosixPath("https:/u:SECRET@h/x"),),
            "(PurePosixPath('https:/***:***@h/x'),)",
        ),
        (b"https://u:SECRET@h/", "b'https://***:***@h/'"),
        ({"u": "https://u:SECRET@h"}, "{'u': 'https://***:***@h'}"),
        (GivenPath("/abs/x", "https://u:SECRET@h//x"), "https://***:***@h//x"),
        (
            "CI run https://ci.example.org, contact ops@example.com",
            "CI run https://ci.example.org, contact ops@example.com",
        ),
        (None, "None"),
        (True, "True"),
        (0, "0"),
    ],
    ids=["list", "tuple-of-paths", "bytes", "dict", "given-path", "text-and-address"]
    + ["none", "bool", "int"],
)
def test_log_kv_masks_every_value_type(
    value: object, shown: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """A value of any type is written as ``str`` writes it (a path as
    typed), a URL in it without its credentials; text is a line, so an
    address after a URL is kept."""
    configure_logging()
    logging.getLogger("pitloom").setLevel(logging.INFO)
    log_kv(V=value)
    assert capsys.readouterr().err == f"INFO: V={shown}\n"
