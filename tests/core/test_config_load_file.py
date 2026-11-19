# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A configuration file that cannot be read (``--config``, an sdist's own
config): each fault is one coded line that names the file once, as ``FILE=``,
never behind a ``config file '...':`` prefix (a coded exception is forwarded
unchanged), through the library and a real ``loom`` run.

See also: :mod:`tests.core.test_config_cascade` (``load_config_file``'s
cascade rules) and :mod:`tests.extract.project.test_sdist_config` (the
sdist reader).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from pitloom.core.config_cascade import load_config_file
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import code_of
from tests.assemble.conftest import _make_sdist
from tests.test_config_key_surfaces import _HEAD, _OFFLINE, _cli, _project

pytestmark = pytest.mark.platform

_BAD_TOML = b"[tool.pitloom\ninvalid"
_CRLF_TOML = b"a = 1\r\nb = 2\r\nc = = 3\r\n"  # the fault is on line 3


def _config(tmp_path: Path, payload: bytes) -> Path:
    path = tmp_path / "c.toml"
    path.write_bytes(payload)
    return path


def _project_argv(tmp_path: Path, config: Path, name: str = "p") -> list[str]:
    project = _project(tmp_path, name, _HEAD)
    output = tmp_path / f"{name}.spdx3.json"  # else the SBOM lands in the cwd
    return [
        "project",
        str(project),
        "--config",
        str(config),
        "-o",
        str(output),
        *_OFFLINE,
    ]


def _error_line(err: str) -> str:
    """The one ``ERROR:`` line of *err* (usage text and notes left out)."""
    (line,) = [ln for ln in err.splitlines() if ln.startswith("ERROR: ")]
    return line


def _fault_names_the_file_once(text: str, path: Path) -> None:
    """*text* leads with ``FILE=<path>`` and holds no second ``FILE=`` nor a
    ``config file`` prefix (trap T4: ``config file 'c.toml': FILE=c.toml``)."""
    assert text.startswith(f"FILE={path}: ")
    assert text.count("FILE=") == 1
    assert "config file" not in text


def test_malformed_toml_names_the_file_once_in_the_library(tmp_path: Path) -> None:
    path = _config(tmp_path, _BAD_TOML)
    with pytest.raises(ValueError) as exc:
        load_config_file(path)
    assert code_of(exc.value) == "config-malformed"
    _fault_names_the_file_once(str(exc.value), path)
    assert "not valid TOML; " in str(exc.value)


@pytest.mark.skipif(
    not hasattr(sys, "get_int_max_str_digits"), reason="no integer digit limit"
)
def test_an_integer_over_the_digit_limit_names_the_file(tmp_path: Path) -> None:
    """The parser raises a plain ValueError here, not a TOMLDecodeError."""
    path = _config(
        tmp_path, b"[tool.pitloom]\nmax-model-extract-bytes = " + b"9" * 5000
    )
    with pytest.raises(ValueError) as exc:
        load_config_file(path)
    assert code_of(exc.value) == "config-malformed"
    _fault_names_the_file_once(str(exc.value), path)


def test_malformed_toml_names_the_file_once_on_the_command_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = _config(tmp_path, _BAD_TOML)
    status, err = _cli(_project_argv(tmp_path, path), monkeypatch, capsys)
    assert status == 1
    line = _error_line(err)
    assert line.endswith(" [config-malformed]")
    _fault_names_the_file_once(
        line.removeprefix("ERROR: loom project: ").removesuffix(" [config-malformed]"),
        path,
    )


def test_an_sdists_invalid_config_names_the_member_once_on_the_command_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The sdist reader forwards a coded error from the config parser, so the
    member (``<archive>:pyproject.toml``) is named once, as ``FILE=``."""
    sdist = _make_sdist(tmp_path, "[tool.pitloom]\npretty = 'yes'\n")
    status, err = _cli(["project", str(sdist), *_OFFLINE], monkeypatch, capsys)
    assert status == 1
    line = _error_line(err)
    assert line.endswith(" [config-invalid]")
    text = line.removeprefix("ERROR: loom project: ")
    assert text.startswith(f"FILE={sdist}:pyproject.toml: [tool.pitloom] pretty: ")
    assert text.count("FILE=") == 1
    assert "config file" not in text


def test_a_toml_error_on_line_3_of_a_crlf_file_names_line_3(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CRLF line ends do not shift the line the parser reports."""
    path = _config(tmp_path, _CRLF_TOML)
    with pytest.raises(ValueError, match=r"\(at line 3, column") as exc:
        load_config_file(path)
    assert code_of(exc.value) == "config-malformed"
    status, err = _cli(_project_argv(tmp_path, path), monkeypatch, capsys)
    assert status == 1
    assert "(at line 3, column" in _error_line(err)


@pytest.mark.parametrize(
    "payload", [b"\xff\xfe[tool.pitloom]\n", b"[tool.pitloom]\nx = '\xc3('\n"]
)
def test_a_config_that_is_not_utf8_is_unreadable_for_the_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    payload: bytes,
) -> None:
    path = _config(tmp_path, payload)
    with pytest.raises(ValueError) as exc:
        load_config_file(path)
    assert code_of(exc.value) == "file-unreadable/not-utf8"
    _fault_names_the_file_once(str(exc.value), path)
    assert "for the configuration" in str(exc.value)
    status, err = _cli(_project_argv(tmp_path, path), monkeypatch, capsys)
    assert status == 1
    line = _error_line(err)
    assert line.endswith(" [file-unreadable/not-utf8]")
    assert "for the configuration" in line


def test_a_missing_config_file_stays_input_not_found(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Not folded into the read faults: the user named a path that is not
    there."""
    missing = tmp_path / "nope.toml"
    with pytest.raises(FileNotFoundError) as exc:
        load_config_file(missing)
    assert code_of(exc.value) == "input-not-found"
    status, err = _cli(_project_argv(tmp_path, missing), monkeypatch, capsys)
    assert status == 1
    line = _error_line(err)
    assert line.endswith(" [input-not-found]")
    assert "config file not found" in line


@pytest.mark.parametrize(
    "content",
    [b'[project]\nname = "x"\n', b"[tool.other]\nkey = 1\n"],
    ids=["no-tool", "other-tool"],
)
def test_a_config_without_a_pitloom_table_warns_and_exits_0(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    content: bytes,
) -> None:
    """A wrong path would otherwise pass unnoticed: one ``WARNING:`` coded
    ``option-no-effect``, and the run goes on with the defaults. An empty
    ``[tool.pitloom]`` is a real config and stays quiet."""
    path = _config(tmp_path, content)
    status, err = _cli(_project_argv(tmp_path, path), monkeypatch, capsys)
    assert status == 0
    (line,) = [ln for ln in err.splitlines() if "[tool.pitloom] table" in ln]
    assert line.startswith(f"WARNING: Options: FILE={path}: --config has no ")
    assert line.endswith("; the defaults apply [option-no-effect]")
    empty = _config(tmp_path, b"[tool.pitloom]\n")
    status, err = _cli(_project_argv(tmp_path, empty, "q"), monkeypatch, capsys)
    assert status == 0
    assert "option-no-effect" not in err


def test_the_warning_for_a_config_without_a_table_carries_its_code(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The library route: the record carries ``pitloom_code`` for a relay."""
    path = _config(tmp_path, b'[project]\nname = "x"\n')
    with caplog.at_level(logging.WARNING):
        load_config_file(path, source="pitloom_config")
    (record,) = [r for r in caplog.records if "no [tool.pitloom]" in r.getMessage()]
    assert getattr(record, CODE_ATTR) == "option-no-effect"
    assert f"FILE={path}: pitloom_config has no " in record.getMessage()
