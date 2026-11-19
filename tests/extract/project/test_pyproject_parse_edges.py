# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Boundaries of the pyproject parse and name reads found by mutation testing.

See also: ``tests/extract/project/test_pyproject.py``.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from pyproject_metadata import ConfigurationError

from pitloom.extract.project import read_project
from pitloom.extract.project.pyproject import read_pyproject
from tests._code_records import coded

pytestmark = pytest.mark.platform

_MIT = 'license = "MIT"\n'
_STATED = 'classifiers = ["License :: OSI Approved :: MIT License"]\n'


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "pyproject.toml"
    path.write_text(f'[project]\nname = "d"\n{body}', encoding="utf-8")
    return path


def test_a_category_only_classifier_beside_an_spdx_licence_is_dropped_silently(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A ``License ::`` classifier that states no licence (a category alone)
    loses to ``license`` without a ``WARNING:``: only a stated one is said."""
    path = _write(
        tmp_path,
        'version = "1"\n' + _MIT + 'classifiers = ["License :: OSI Approved"]\n',
    )
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        metadata, _ = read_pyproject(path)
    assert metadata.license_name == "MIT"
    assert "license-conflict" not in [code for code, _ in coded(caplog)]


def test_an_unknown_project_key_survives_the_licence_retry(tmp_path: Path) -> None:
    """The retry parses as the first parse does: extra keys are allowed."""
    path = _write(tmp_path, 'version = "1"\nfoo = "x"\n' + _MIT + _STATED)
    metadata, _ = read_pyproject(path)
    assert metadata.license_name == "MIT"


def test_a_refused_retry_reports_its_own_failure_and_chains_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The licence conflict is recovered from; what the user must fix is the
    second refusal, not the conflict already dropped. (Real data cannot reach
    it: pyproject-metadata checks the licence after every other field.)"""
    calls: list[int] = []

    def refuse(*_args: object, **_kwargs: object) -> object:
        calls.append(1)
        if len(calls) == 1:
            raise ConfigurationError(
                "SPDX license expression is not compatible with 'License ::' "
                "classifiers",
                key="project.license",
            )
        raise RuntimeError("second refusal")

    monkeypatch.setattr(
        "pitloom.extract.project._pyproject_parse.StandardMetadata.from_pyproject",
        refuse,
    )
    path = _write(tmp_path, 'version = "1"\n' + _MIT + _STATED)
    with pytest.raises(ValueError) as exc:
        read_pyproject(path)
    assert len(calls) == 2  # the retry ran
    assert "second refusal" in str(exc.value)
    assert "not compatible" not in str(exc.value)
    assert isinstance(exc.value.__cause__, RuntimeError)


def test_an_unexpected_library_failure_is_a_coded_error_chaining_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not a ``ConfigurationError`` (a library bug on odd input): still the
    coded refusal, with the library's own error kept as its cause."""

    def boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("library bug")

    monkeypatch.setattr(
        "pitloom.extract.project._pyproject_parse.StandardMetadata.from_pyproject",
        boom,
    )
    path = _write(tmp_path, 'version = "1"\n')
    with pytest.raises(ValueError) as exc:
        read_pyproject(path)
    assert "library bug" in str(exc.value)
    assert isinstance(exc.value.__cause__, RuntimeError)


def test_the_setuptools_fallback_names_setup_cfg_first_when_both_files_exist(
    tmp_path: Path,
) -> None:
    """A ``pyproject.toml`` with no metadata defers to the setuptools files;
    the config path it returns is ``setup.cfg``, not ``setup.py``."""
    root = tmp_path / "p"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools"]\n', encoding="utf-8"
    )
    (root / "setup.cfg").write_text("[metadata]\nname = real\nversion = 1\n")
    (root / "setup.py").write_text("from setuptools import setup\nsetup()\n")
    metadata, _, config_path = read_project(root)
    assert metadata.name == "real"
    assert config_path == root / "setup.cfg"
