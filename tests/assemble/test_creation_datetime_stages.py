# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A bad creation datetime is refused where it enters, once per stage:
the flag (argparse, ``option-invalid``, exit 2), a file (``config-invalid``,
exit 1) and a library value (``option-invalid``). A URL given by mistake is
masked on every one of them.

See also: :mod:`tests.assemble.test_creation` (``SOURCE_DATE_EPOCH``) and
:mod:`tests.assemble.test_creation_info` (the parse).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.cli.parser import _build_parser
from pitloom.core.creation import CreationMetadata
from pitloom.messages import code_of
from tests.test_byte_cap_surfaces import _subcommands
from tests.test_config_key_surfaces import _HEAD, _cli, _project

pytestmark = pytest.mark.platform

_FLAG = "--creation-datetime"
_SECRET = "https://user:hunter2@host.example/x"
_MASKED = "https://***:***@host.example/x"
#: A ``[tool.pitloom]`` text that holds *value* as the creation datetime, in
#: each of the two places the key is read.
_FILE_TEXTS = {
    "top-level": '[tool.pitloom]\ncreation-datetime = "{}"\n',
    "creation-table": '[tool.pitloom.creation]\ndatetime = "{}"\n',
}


def _chain(exc: BaseException) -> list[str]:
    """The text and arguments of *exc* and everything it chains to."""
    texts: list[str] = []
    link: BaseException | None = exc
    while link is not None:
        texts.append(f"{link}{link.args!r}")
        link = link.__cause__ or link.__context__
    return texts


@pytest.mark.parametrize("command", _subcommands(_FLAG))
def test_the_flag_refuses_a_bad_datetime_at_parse_time(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 2 from argparse on every subcommand that offers it (it was
    exit 1, at assembly)."""
    with pytest.raises(SystemExit) as exc:
        _build_parser().parse_args([command, _FLAG, "notadate"])
    assert exc.value.code == 2
    err = capsys.readouterr().err.rstrip()
    assert f"argument {_FLAG}: must be an ISO 8601 date and time, got a string" in err
    assert err.endswith("'notadate' [option-invalid]")


def test_the_flag_refuses_a_time_outside_utc_years_1_to_9999_at_parse_time(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Valid as written, so it passed the parse and died at assembly with an
    uncoded ``date value out of range``."""
    with pytest.raises(SystemExit) as exc:
        _build_parser().parse_args(["project", _FLAG, "0001-01-01T00:00:00+05:00"])
    assert exc.value.code == 2
    assert capsys.readouterr().err.rstrip().endswith("[option-invalid]")


def test_the_flag_is_offered_by_the_sbom_subcommands() -> None:
    """Not vacuous: the parametrisation above found the commands."""
    assert {"project", "wheel", "embed-wheel"} <= set(_subcommands(_FLAG))


@pytest.mark.parametrize("where", sorted(_FILE_TEXTS))
def test_a_bad_datetime_in_a_file_is_config_invalid_exit_1(
    where: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _project(tmp_path, "p", _HEAD + _FILE_TEXTS[where].format("zzz"))
    status, err = _cli(["project", str(project), "--offline"], monkeypatch, capsys)
    assert status == 1
    line = err.rstrip().splitlines()[-1]
    assert line.endswith(
        "must be an ISO 8601 date and time, got a string 'zzz' [config-invalid]"
    )
    assert "FILE=" in line


def test_a_bad_datetime_has_a_code_per_stage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One value, ``zzz``: the stage picks the code (a flag and a library
    value are ``option-invalid``, a file's is ``config-invalid``)."""
    with pytest.raises(ValueError, match="^creation_datetime: must be") as lib:
        generate_project_sbom(
            _project(tmp_path, "lib", _HEAD),
            creation_metadata=CreationMetadata(creation_datetime="zzz"),
            offline=True,
        )
    assert code_of(lib.value) == "option-invalid"
    file_project = _project(
        tmp_path, "file", _HEAD + _FILE_TEXTS["top-level"].format("zzz")
    )
    with pytest.raises(ValueError, match="creation-datetime: must be") as file:
        generate_project_sbom(file_project, offline=True)
    assert code_of(file.value) == "config-invalid"
    with pytest.raises(SystemExit) as flag:
        _build_parser().parse_args(["project", _FLAG, "zzz"])
    assert flag.value.code == 2
    assert capsys.readouterr().err.rstrip().endswith("[option-invalid]")


@pytest.mark.parametrize("where", sorted(_FILE_TEXTS))
def test_a_url_as_the_datetime_is_masked_in_a_file(
    where: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Trap T8: the raw value rides in ``got``, masked by the writer; the
    command line, the exception text, its arguments and its chain keep no
    credential."""
    project = _project(tmp_path, "p", _HEAD + _FILE_TEXTS[where].format(_SECRET))
    with pytest.raises(ValueError) as exc:
        generate_project_sbom(project, offline=True)
    assert code_of(exc.value) == "config-invalid"
    assert _MASKED in str(exc.value)
    assert not any("hunter2" in text for text in _chain(exc.value))
    status, err = _cli(["project", str(project), "--offline"], monkeypatch, capsys)
    assert status == 1
    assert _MASKED in err and "hunter2" not in err


def test_a_url_as_the_datetime_is_masked_as_a_flag(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        _build_parser().parse_args(["project", _FLAG, _SECRET])
    err = capsys.readouterr().err
    assert _MASKED in err
    assert "hunter2" not in err


@pytest.mark.parametrize("key", ["creation_datetime", "build_datetime"])
def test_a_url_as_a_library_datetime_is_masked(key: str, tmp_path: Path) -> None:
    project = _project(tmp_path, "p", _HEAD)
    kwargs: dict[str, Any] = {key: _SECRET}
    with pytest.raises(ValueError) as exc:
        generate_project_sbom(
            project, creation_metadata=CreationMetadata(**kwargs), offline=True
        )
    assert code_of(exc.value) == "option-invalid"
    assert _MASKED in str(exc.value)
    assert not any("hunter2" in text for text in _chain(exc.value))
