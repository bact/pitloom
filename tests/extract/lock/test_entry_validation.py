# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Lock-entry ``name`` and ``version`` validation, one case per format
(``pylock.toml``, ``poetry.lock``, ``pdm.lock``, ``Pipfile.lock``,
``uv.lock``): a name that is no PEP 508 name, or a version padded with
whitespace, skips its entry with one single-line ``WARNING:`` instead of
reaching a PURL, a dependency string or the log.

See also: tests/extract/lock/test_common.py (the shared helpers).
"""

import json
import logging
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.extract.lock.pdm import extract_pdm_lock_dependencies
from pitloom.extract.lock.pipfile import extract_pipfile_lock_dependencies
from pitloom.extract.lock.poetry import extract_poetry_lock_dependencies
from pitloom.extract.lock.pylock import extract_pylock_dependencies
from pitloom.extract.lock.uv import extract_uv_lock_dependencies

_Extractor = Callable[[Path], list[str] | None]

_GOOD = [("Foo_Bar.baz", "1.0"), ("requests", "2.0")]
_BAD_NAMES = [
    "bar baz\x1b[31m",
    "a; python_version<'3'",
    "b\nWARNING: x",
    "a @ http://evil/x",
    "a[x]",
]
_PAD_VERSION = " 1.0\n"


def _toml_packages(table: str, entries: list[tuple[str, str]]) -> str:
    """``[[table]]`` entries; ``json.dumps`` quotes as a TOML basic string."""
    return "".join(
        f"[[{table}]]\nname = {json.dumps(n)}\nversion = {json.dumps(v)}\n"
        for n, v in entries
    )


def _pylock(dir_: Path, entries: list[tuple[str, str]]) -> _Extractor:
    (dir_ / "pylock.toml").write_text(
        'lock-version = "1.0"\ncreated-by = "x"\n'
        + _toml_packages("packages", entries),
        encoding="utf-8",
    )
    return extract_pylock_dependencies


def _poetry(dir_: Path, entries: list[tuple[str, str]]) -> _Extractor:
    (dir_ / "poetry.lock").write_text(
        '[metadata]\nlock-version = "2.1"\n' + _toml_packages("package", entries),
        encoding="utf-8",
    )
    return extract_poetry_lock_dependencies


def _pdm(dir_: Path, entries: list[tuple[str, str]]) -> _Extractor:
    (dir_ / "pdm.lock").write_text(
        '[metadata]\nlock_version = "4.5"\n' + _toml_packages("package", entries),
        encoding="utf-8",
    )
    return extract_pdm_lock_dependencies


def _pipfile(dir_: Path, entries: list[tuple[str, str]]) -> _Extractor:
    default = {name: {"version": f"=={version}"} for name, version in entries}
    (dir_ / "Pipfile.lock").write_text(
        json.dumps({"_meta": {"pipfile-spec": 6}, "default": default}),
        encoding="utf-8",
    )
    return extract_pipfile_lock_dependencies


def _uv(dir_: Path, entries: list[tuple[str, str]]) -> _Extractor:
    # The root references the first two entries; the rest stay unreferenced
    # packages, so each bad name is warned of once, as a package.
    refs = ", ".join(f"{{name = {json.dumps(n)}}}" for n, _v in entries[:2])
    root = (
        'version = 1\n[[package]]\nname = "app"\nversion = "0.1"\n'
        f'source = {{editable = "."}}\ndependencies = [{refs}]\n'
    )
    (dir_ / "uv.lock").write_text(
        root + _toml_packages("package", entries), encoding="utf-8"
    )
    return lambda project_dir: extract_uv_lock_dependencies(project_dir, "app")


_FORMATS = pytest.mark.parametrize(
    "build",
    [_pylock, _poetry, _pdm, _pipfile, _uv],
    ids=["pylock", "poetry", "pdm", "pipfile", "uv"],
)


@_FORMATS
def test_a_name_that_is_no_pep_508_name_is_skipped_with_one_warning(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    build: Callable[[Path, list[tuple[str, str]]], _Extractor],
) -> None:
    """Valid names (dots, underscores, capitals) are kept as written; each
    injection shape is skipped, shown escaped on one line."""
    entries = [*_GOOD, *((name, "1.0") for name in _BAD_NAMES)]
    extract = build(tmp_path, entries)

    with caplog.at_level(logging.WARNING):
        result = extract(tmp_path)

    assert result is not None
    assert sorted(result) == ["Foo_Bar.baz==1.0", "requests==2.0"]
    assert len(caplog.messages) == len(_BAD_NAMES)
    assert all("invalid 'name'" in m and m.isprintable() for m in caplog.messages)


@pytest.mark.parametrize(
    "build", [_pylock, _poetry, _pdm, _uv], ids=["pylock", "poetry", "pdm", "uv"]
)
def test_a_version_padded_with_whitespace_is_skipped_with_one_warning(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    build: Callable[[Path, list[tuple[str, str]]], _Extractor],
) -> None:
    extract = build(tmp_path, [("requests", "2.0"), ("padded", _PAD_VERSION)])

    with caplog.at_level(logging.WARNING):
        result = extract(tmp_path)

    assert result == ["requests==2.0"]
    (message,) = caplog.messages
    assert "'padded'" in message
