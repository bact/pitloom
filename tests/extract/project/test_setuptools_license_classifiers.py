# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A setuptools project's ``License ::`` classifiers read as setuptools
reads them: ``setup.cfg``'s list rule (a line each, or comma-separated on
one line), and ``setup.py``'s licence over ``setup.cfg``'s -- the licence a
built wheel's metadata gives.

See also: :mod:`tests.extract.project.test_setuptools_integration`,
:mod:`tests.extract.project.test_setuptools_merge_license`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from setuptools.config.setupcfg import read_configuration

from pitloom import __main__
from pitloom.extract._core_metadata import license_or_classifier
from pitloom.extract.project import read_project
from pitloom.extract.project.setuptools_cfg import read_setup_cfg
from tests._license_graph import license_targets

_MIT = "License :: OSI Approved :: MIT License"
_PYTHON = "Programming Language :: Python"
_BSD = "License :: OSI Approved :: BSD License"


def _setup_cfg(root: Path, classifiers: str, extra: str = "") -> None:
    (root / "setup.cfg").write_text(
        f"[metadata]\nname = demo\nversion = 1.0\n{extra}classifiers = {classifiers}\n",
        encoding="utf-8",
    )


def _loom_project(root: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The licence targets of ``loom project`` on *root*, run in-process."""
    output = root / "sbom.json"
    monkeypatch.setattr(
        sys, "argv", ["loom", "project", str(root), "-o", str(output), "--offline"]
    )
    assert __main__.main() == 0
    return license_targets(json.loads(output.read_text(encoding="utf-8"))["@graph"])


@pytest.mark.parametrize(
    ("classifiers", "files"),
    [
        (f"{_MIT}, {_PYTHON}", {}),
        (f"{_PYTHON}, {_MIT}", {}),  # the licence last on the line
        (f"\n    {_PYTHON}\n    {_MIT}", {}),  # a line each
        ("file: CLASSIFIERS", {"CLASSIFIERS": f"{_PYTHON}, {_MIT}"}),
        ("file: CLASSIFIERS", {"CLASSIFIERS": f"{_PYTHON}\n{_MIT}\n"}),
    ],
    ids=["one-line", "one-line-licence-last", "lines", "file-one-line", "file-lines"],
)
def test_classifiers_are_split_as_setuptools_splits_them(
    classifiers: str,
    files: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    _setup_cfg(tmp_path, classifiers)
    listed = read_configuration(tmp_path / "setup.cfg")["metadata"]
    assert sorted(listed["classifiers"]) == sorted([_MIT, _PYTHON])
    expected = license_or_classifier(None, listed["classifiers"])[0]
    assert expected == "MIT License"
    assert read_setup_cfg(tmp_path)[0].license_name == expected
    assert _loom_project(tmp_path, monkeypatch) == [expected]


_CFG_CLASSIFIER = "setup.cfg | Field: metadata.classifiers"
_PY_CLASSIFIER = "setup.py | Field: setup(classifiers=...)"


@pytest.mark.parametrize(
    ("setup_py_args", "expected", "source"),
    [
        ("license='MIT'", "MIT", "setup.py | Field: setup(license=...)"),
        # a placeholder field gives way to the classifier, as in a wheel
        ("license='UNKNOWN'", "BSD License", _CFG_CLASSIFIER),
        ("", "BSD License", _CFG_CLASSIFIER),
        # setup() keywords replace setup.cfg's, classifiers too
        (f"classifiers=[{_MIT!r}]", "MIT License", _PY_CLASSIFIER),
        (f"license='UNKNOWN', classifiers=[{_MIT!r}]", "MIT License", _PY_CLASSIFIER),
    ],
    ids=["field", "placeholder", "none", "classifier", "placeholder-classifier"],
)
def test_setup_py_licence_beats_a_setup_cfg_classifier(
    setup_py_args: str, expected: str, source: str, tmp_path: Path
) -> None:
    """The licence of the wheel setuptools builds: ``setup()`` keywords
    over ``setup.cfg``, then the ``License:`` field over a classifier."""
    _setup_cfg(tmp_path, f"\n    {_BSD}")
    (tmp_path / "setup.py").write_text(
        f"from setuptools import setup\nsetup(name='demo', {setup_py_args})\n",
        encoding="utf-8",
    )
    metadata = read_project(tmp_path)[0]
    assert metadata.license_name == expected
    assert metadata.provenance["license"] == f"Source: {source}"


def test_a_setup_py_licence_field_beats_setup_cfg(tmp_path: Path) -> None:
    """``setup.cfg``'s own field gives way too, kept as a conflict."""
    _setup_cfg(tmp_path, f"\n    {_BSD}", extra="license = Apache-2.0\n")
    (tmp_path / "setup.py").write_text(
        "from setuptools import setup\nsetup(name='demo', license='MIT')\n",
        encoding="utf-8",
    )
    metadata = read_project(tmp_path, quiet=True)[0]
    assert metadata.license_name == "MIT"
    assert [c["value"] for c in metadata.field_conflicts["license"]] == [
        "MIT",
        "Apache-2.0",
    ]
