# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Two config rules hold on every surface that reads a ``[tool.pitloom]``
(the CLI, the library API, an sdist's own config, ``--config``, the Hatchling
hook): an unknown key warns once; a negative ``max-source-metadata-bytes`` is
refused.

See also: :mod:`tests.core.test_config_unknown_keys` and
:mod:`tests.core.test_provenance` for the parts.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from pitloom import __main__
from pitloom.assemble import (
    generate_env_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.cli.parser import _build_parser
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import ConfigOverrides, apply_overrides
from pitloom.core.creation import CreationMetadata
from pitloom.core.provenance import ProvenanceConfig
from pitloom.embed import embed_wheel_sbom
from tests.assemble.conftest import _make_dummy_wheel, _make_sdist
from tests.extract.conftest import make_hook
from tests.warning_helpers import error_lines, logged_warnings, stderr_warnings

_PINNED = CreationMetadata(creation_datetime="2026-01-01T00:00:00Z")
_HEAD = '[project]\nname = "demo"\nversion = "1.0.0"\n'
_CFG_HEAD = "[metadata]\nname = demo\nversion = 1.0\n"
_OFFLINE = ["--offline", "--creation-datetime", "2026-01-01T00:00:00Z"]
_TYPO = "[tool.pitloom] unknown key 'ofline'; did you mean 'offline'?"
_TYPO_CFG = "[tool:pitloom] unknown key 'ofline'; did you mean 'offline'?"
_BAD_KEY = "'max-source-metadata-bytes' must be 0 (unlimited) or at least 8 bytes"


def _toml(tail: str) -> str:
    return f"{_HEAD}[tool.pitloom]\n{tail}\n"


def _loom(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    return __main__.main()


def _project(tmp_path: Path, name: str, text: str) -> Path:
    project = tmp_path / name
    (project / "demo").mkdir(parents=True)
    (project / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (project / _config_file_name(text)).write_text(text, encoding="utf-8")
    return project


def _config_file_name(text: str) -> str:
    """The config file a project text belongs in."""
    return "setup.cfg" if text.startswith("[metadata]") else "pyproject.toml"


def _cli(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, str]:
    code = _loom(argv, monkeypatch)
    return code, capsys.readouterr().err


def _hook(tmp_path: Path, text: str) -> None:
    root = _project(tmp_path, "h", text)
    hook = make_hook(str(root), {})
    build_data: dict[str, Any] = {}
    hook.initialize("standard", build_data)
    hook.finalize("standard", build_data, "")


def _wheel_cli_config(tmp_path: Path, text: str) -> list[str]:
    config = tmp_path / "c.toml"
    config.write_text(text, encoding="utf-8")
    wheel = _make_dummy_wheel(tmp_path / "w", "demo", "1.0.0")
    return ["embed-wheel", str(wheel), "--config", str(config), *_OFFLINE]


def _project_config_file(tmp_path: Path, text: str) -> list[str]:
    config = tmp_path / "c.toml"
    config.write_text(text, encoding="utf-8")
    bare = _project(tmp_path, "bare", _HEAD)
    return ["project", str(bare), "--config", str(config), *_OFFLINE]


def _argv(surface: str, tmp_path: Path, text: str) -> list[str]:
    """The ``loom`` argv of a CLI *surface* reading config *text*."""
    if surface == "project":
        return ["project", str(_project(tmp_path, "p", text)), *_OFFLINE]
    if surface == "project-config-file":
        return _project_config_file(tmp_path, text)
    return _wheel_cli_config(tmp_path, text)


_CLI_SURFACES = ["project", "project-config-file", "embed-wheel-config"]


def _one_unknown(messages: list[str], message: str, source_tail: str) -> None:
    """The one unknown-key message: *message*, led by the config file it names."""
    (found,) = [m for m in messages if "unknown key" in m]
    assert found.endswith(f" {message}"), found
    source = found.removeprefix("WARNING: ")[: -len(message) - 1]
    assert source.endswith(source_tail), source


_CLI_SOURCES = {
    "project": "p/pyproject.toml",
    "project-config-file": "c.toml",
    "embed-wheel-config": "c.toml",
}


@pytest.mark.parametrize("surface", _CLI_SURFACES)
def test_cli_unknown_key_warns_once(
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    code, err = _cli(
        _argv(surface, tmp_path, _toml("ofline = true")), monkeypatch, capsys
    )
    assert code == 0
    _one_unknown(stderr_warnings(err), _TYPO, _CLI_SOURCES[surface])


def test_cli_setup_cfg_unknown_key_warns_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    text = f"{_CFG_HEAD}[tool:pitloom]\nofline = true\n"
    argv = ["project", str(_project(tmp_path, "p", text)), *_OFFLINE]
    code, err = _cli(argv, monkeypatch, capsys)
    assert code == 0
    _one_unknown(stderr_warnings(err), _TYPO_CFG, "p/setup.cfg")


_CFG_TYPO = f"{_CFG_HEAD}[tool:pitloom]\nofline = true\n"
_KINDS = {
    "directory": ("p/pyproject.toml", _TYPO),
    "sdist": (".tar.gz:pyproject.toml", _TYPO),
    "setup.cfg": ("p/setup.cfg", _TYPO_CFG),
    "sdist-setup.cfg": (".tar.gz:setup.cfg", _TYPO_CFG),
}


def _kind_target(kind: str, tmp_path: Path, name: str = "p") -> Path:
    if kind == "directory":
        return _project(tmp_path, name, _toml("ofline = true"))
    if kind == "setup.cfg":
        return _project(tmp_path, name, _CFG_TYPO)
    if kind == "sdist":
        return _make_sdist(tmp_path, "[tool.pitloom]\nofline = true\n")
    return _make_sdist(
        tmp_path,
        members={"pyproject.toml": None, "setup.cfg": _CFG_TYPO.encode()},
    )


@pytest.mark.parametrize("kind", sorted(_KINDS))
def test_library_unknown_key_warns_once(
    kind: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    target = _kind_target(kind, tmp_path)
    with caplog.at_level(logging.WARNING):
        for _ in range(2):
            generate_project_sbom(target, creation_metadata=_PINNED, offline=True)
    tail, message = _KINDS[kind]
    _one_unknown(logged_warnings(caplog), message, tail)


def test_two_projects_with_the_same_typo_both_warn(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        for name in ("one", "two"):
            target = _kind_target("directory", tmp_path, name)
            generate_project_sbom(target, creation_metadata=_PINNED, offline=True)
    found = [m for m in logged_warnings(caplog) if "unknown key" in m]
    assert [("/one/" in m, "/two/" in m) for m in found] == [
        (True, False),
        (False, True),
    ]


def test_hatchling_hook_unknown_key_warns_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp, caplog.at_level(logging.WARNING):
        _hook(Path(tmp), _toml("ofline = true"))
    _one_unknown(logged_warnings(caplog), _TYPO, "h/pyproject.toml")


@pytest.mark.parametrize("kind", ["directory", "sdist", "sdist-setup.cfg"])
@pytest.mark.parametrize(
    "tool_line",
    ["creation-tool = MyTool", "tool = MyTool"],
)
def test_setup_cfg_creation_tool_reaches_the_sbom(
    kind: str, tool_line: str, tmp_path: Path
) -> None:
    """It was dropped on reading, silently, on every surface."""
    cfg = f"{_CFG_HEAD}[tool:pitloom]\n{tool_line}\n"
    if kind == "directory":
        target = _project(tmp_path, "p", cfg)
    else:
        target = _make_sdist(
            tmp_path, members={"pyproject.toml": None, "setup.cfg": cfg.encode()}
        )
    # no creation_metadata=: an argument would replace the config's tools
    sbom = generate_project_sbom(target, offline=True)
    tools = [e["name"] for e in json.loads(sbom)["@graph"] if e["type"] == "Tool"]
    assert tools == ["MyTool"]


# --- a negative max-source-metadata-bytes ------------------------------------


@pytest.mark.parametrize("value", [-1, 5])  # below 0, and below the 8-byte floor
@pytest.mark.parametrize(
    "key", ["max-source-metadata-bytes", "max_source_metadata_bytes"]
)
@pytest.mark.parametrize("surface", _CLI_SURFACES)
def test_cli_bad_config_key_is_an_error(
    surface: str,
    key: str,
    value: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    text = f"{_HEAD}[tool.pitloom.provenance]\n{key} = {value}\n"
    code, err = _cli(_argv(surface, tmp_path, text), monkeypatch, capsys)
    assert code == 1
    assert len(error_lines(err)) == 1
    # the key as written, in the table as the reader saw it
    assert (
        f"[tool.pitloom.provenance] '{key}' must be 0 (unlimited) or at least 8" in err
    )
    assert f"bytes, got {value}" in err


def test_cli_bad_setup_cfg_key_names_its_own_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    text = f"{_CFG_HEAD}[tool:pitloom:provenance]\nmax-source-metadata-bytes = 7\n"
    code, err = _cli(
        ["project", str(_project(tmp_path, "p", text)), *_OFFLINE], monkeypatch, capsys
    )
    assert code == 1
    assert f"[tool:pitloom:provenance] {_BAD_KEY}, got 7" in err


@pytest.mark.parametrize("kind", ["directory", "sdist"])
def test_library_bad_config_key_raises(kind: str, tmp_path: Path) -> None:
    tail = "[tool.pitloom.provenance]\nmax-source-metadata-bytes = 3\n"
    target = (
        _project(tmp_path, "p", _HEAD + tail)
        if kind == "directory"
        else _make_sdist(tmp_path, tail)
    )
    with pytest.raises(ValueError, match="at least 8 bytes, got 3"):
        generate_project_sbom(target, creation_metadata=_PINNED, offline=True)


def test_hatchling_hook_bad_config_key_raises() -> None:
    tail = "[tool.pitloom.provenance]\nmax-source-metadata-bytes = -1\n"
    with (
        tempfile.TemporaryDirectory() as tmp,
        pytest.raises(ValueError, match="at least 8 bytes, got -1"),
    ):
        _hook(Path(tmp), _HEAD + tail)


def _subcommands() -> list[str]:
    """Every subcommand that offers ``--max-source-metadata-bytes``."""
    # pylint: disable-next=protected-access
    actions = _build_parser()._actions
    # pylint: disable-next=protected-access
    (sub,) = [a for a in actions if isinstance(a, argparse._SubParsersAction)]
    return sorted(
        name
        for name, parser in sub.choices.items()
        if "--max-source-metadata-bytes" in parser.format_help()
    )


@pytest.mark.parametrize("command", _subcommands())
@pytest.mark.parametrize(
    ("value", "text"),
    [
        ("-1", "argument --max-source-metadata-bytes: must be 0 (unlimited) or at"),
        ("5", "at least 8 bytes, got 5"),
        ("x", "invalid int"),
    ],
)
def test_flag_refuses_a_bad_value_on_every_subcommand(
    command: str, value: str, text: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        _build_parser().parse_args([command, "--max-source-metadata-bytes", value])
    assert exc.value.code == 2
    assert text in capsys.readouterr().err


def test_flag_is_offered_by_the_sbom_subcommands() -> None:
    """Not vacuous: the parametrisation above found the commands."""
    assert {"project", "wheel", "embed-wheel"} <= set(_subcommands())


def test_loom_flag_too_small_exits_2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path, "p", _HEAD)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        _loom(
            ["project", str(project), "--max-source-metadata-bytes", "-1"], monkeypatch
        )
    assert exc.value.code == 2


def _library_calls(tmp_path: Path) -> dict[str, Callable[[int], Any]]:
    project = _project(tmp_path, "p", _HEAD)
    wheel = _make_dummy_wheel(tmp_path / "w", "demo", "1.0.0")
    sbom_wheel = _make_dummy_wheel(tmp_path / "x", "demo", "1.0.0")
    return {
        "project": lambda n: generate_project_sbom(
            project, creation_metadata=_PINNED, max_source_metadata_bytes=n
        ),
        "wheel": lambda n: generate_wheel_sbom(
            wheel, creation_metadata=_PINNED, max_source_metadata_bytes=n
        ),
        "env": lambda n: generate_env_sbom(
            creation_metadata=_PINNED, max_source_metadata_bytes=n
        ),
        "embed": lambda n: embed_wheel_sbom(
            wheel, overrides=ConfigOverrides(max_source_metadata_bytes=n)
        ),
        "embed-inert-sbom": lambda n: embed_wheel_sbom(
            sbom_wheel,
            sbom_path=_sbom_file(tmp_path),
            overrides=ConfigOverrides(max_source_metadata_bytes=n),
        ),
        "overrides": lambda n: apply_overrides(
            PitloomConfig(), ConfigOverrides(max_source_metadata_bytes=n)
        ),
        "provenance-config": lambda n: ProvenanceConfig(max_source_metadata_bytes=n),
        "pitloom-config": lambda n: (
            PitloomConfig(provenance_max_source_metadata_bytes=n).provenance
        ),
    }


def _sbom_file(tmp_path: Path) -> Path:
    """An SBOM for ``demo`` 1.0.0, to hand to ``embed_wheel_sbom(sbom_path=)``."""
    path = tmp_path / "s.json"
    path.write_text(
        generate_wheel_sbom(
            _make_dummy_wheel(tmp_path / "y", "demo", "1.0.0"),
            creation_metadata=_PINNED,
        ),
        encoding="utf-8",
    )
    return path


_CALLS = [
    "project",
    "wheel",
    "env",
    "embed",
    "embed-inert-sbom",
    "overrides",
    "provenance-config",
    "pitloom-config",
]


@pytest.mark.parametrize("value", [-1, 1, 7, 4096.0, True])
@pytest.mark.parametrize("call", _CALLS)
def test_library_refuses_an_invalid_budget(
    call: str, value: Any, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="must be (0 \\(unlimited\\)|an integer)"):
        _library_calls(tmp_path)[call](value)


def test_a_library_config_names_itself_in_the_error() -> None:
    config = PitloomConfig(provenance_max_source_metadata_bytes=3)
    with pytest.raises(
        ValueError, match=r"^pitloom_config 'max-source-metadata-bytes'"
    ):
        _ = config.provenance


@pytest.mark.parametrize("call", ["overrides", "provenance-config", "pitloom-config"])
@pytest.mark.parametrize("value", [0, 8, 4096, np.int64(4096)])
def test_library_accepts_zero_and_a_real_budget(
    call: str, value: int, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The control: ``0`` (unlimited) and a usable budget stay valid, quietly."""
    with caplog.at_level(logging.WARNING):
        _library_calls(tmp_path)[call](value)
    assert not logged_warnings(caplog)
