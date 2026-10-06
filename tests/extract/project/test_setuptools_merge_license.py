# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The licence of a project with both ``setup.py`` and ``setup.cfg``, and the
real values ``setup.py`` overrides, kept as conflicts.

See also: test_setuptools_merge.py (the other options),
test_setuptools_license_classifiers.py (the classifier rules).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom.extract.project import read_project
from pitloom.extract.project.setuptools import read_setuptools
from tests.extract.project.test_setuptools_merge import write_project

_MIT = "License :: OSI Approved :: MIT License"
_BSD = "License :: OSI Approved :: BSD License"
_PY_FIELD = "Source: setup.py | Field: setup(license=...)"
_PY_CLASSIFIER = "Source: setup.py | Field: setup(classifiers=...)"
_CFG_FIELD = "Source: setup.cfg | Field: metadata.license"


def _named(lines: str) -> str:
    return f"[metadata]\nname = p\n{lines}\n"


@pytest.mark.parametrize(
    ("cfg", "py", "licence", "source", "conflict"),
    [
        ("license = UNKNOWN", "license='MIT'", "MIT", _PY_FIELD, None),
        # setuptools writes UNKNOWN here: a placeholder is not a claim
        ("license = MIT", "license='UNKNOWN'", "MIT", _CFG_FIELD, None),
        ("license = UNKNOWN", "license='NOASSERTION'", "NOASSERTION", _PY_FIELD, None),
        ("license = MIT", "license=None", "MIT", _CFG_FIELD, None),
        ("license = MIT", "license='MIT License'", "MIT License", _PY_FIELD, None),
        ("license = MIT", "license='NONE'", "NONE", _PY_FIELD, ["NONE", "MIT"]),
        (
            "license = Apache-2.0",
            "license='MIT'",
            "MIT",
            _PY_FIELD,
            ["MIT", "Apache-2.0"],
        ),
        (
            "[DEFAULT]\nlicense = Apache-2.0\n" + _named(""),
            "license='MIT'",
            "MIT",
            _PY_FIELD,
            ["MIT", "Apache-2.0"],
        ),
        # classifiers replace classifiers
        (
            f"classifiers = {_MIT}",
            "classifiers=['Topic :: Utilities']",
            None,
            None,
            None,
        ),
        (
            f"classifiers = {_MIT}",
            f"classifiers=[{_BSD!r}]",
            "BSD License",
            _PY_CLASSIFIER,
            ["BSD License", "MIT License"],
        ),
        # a field beats a classifier, whichever file states it
        (
            "license = Apache-2.0",
            f"classifiers=[{_MIT!r}]",
            "Apache-2.0",
            _CFG_FIELD,
            ["Apache-2.0", "MIT License"],
        ),
        (
            f"classifiers = {_BSD}",
            "license='MIT'",
            "MIT",
            _PY_FIELD,
            ["MIT", "BSD License"],
        ),
        # as the wheel: setup.py's placeholder gives way to its classifier
        # before setup.cfg's overridden field
        (
            "license = Apache-2.0",
            f"license='UNKNOWN', classifiers=[{_MIT!r}]",
            "MIT License",
            _PY_CLASSIFIER,
            ["MIT License", "Apache-2.0"],
        ),
        # setup.py's placeholder and classifiers without a licence replace
        # setup.cfg's classifier: the placeholder is all that is left
        (
            f"classifiers = {_MIT}",
            "license='UNKNOWN', classifiers=['Topic :: Utilities']",
            "UNKNOWN",
            _PY_FIELD,
            None,
        ),
    ],
    ids=[
        "weak-cfg",
        "weak-py",
        "both-weak",
        "py-none-literal",
        "same-licence",
        "none-statement",
        "real-vs-real",
        "cfg-default",
        "classifiers-replace",
        "classifier-vs-classifier",
        "cfg-field-py-classifier",
        "py-field-cfg-classifier",
        "weak-py-own-classifier",
        "weak-py-no-classifier",
    ],
)
def test_setuptools_licence(
    cfg: str,
    py: str,
    licence: str | None,
    source: str | None,
    conflict: list[str] | None,
    tmp_path: Path,
) -> None:
    write_project(tmp_path, cfg if cfg.startswith("[") else _named(cfg), py)
    metadata, _ = read_setuptools(tmp_path, quiet=True)
    assert metadata.license_name == licence
    assert metadata.provenance.get("license") == source
    candidates = metadata.field_conflicts.get("license")
    assert (None if candidates is None else [c["value"] for c in candidates]) == (
        conflict
    )
    if candidates:
        assert candidates[0]["source"] == source  # the winner first


@pytest.mark.parametrize(
    ("option", "cfg", "py", "conflict"),
    [
        ("version", "1.0.0", "1.0", None),  # PEP 440 equal
        ("version", "1.0", "2.0", ["2.0", "1.0"]),
        ("version", "1.0", "VERSION", None),  # not a literal: setup.cfg's used
        ("python_requires", ">= 3.8", ">=3.8", None),
        ("python_requires", ">=3.8", ">=3.9", [">=3.9", ">=3.8"]),
        ("python_requires", ">=3.8", "", None),  # empty: setup.cfg's kept
    ],
)
def test_setup_py_overriding_a_real_value_is_a_conflict(
    option: str, cfg: str, py: str, conflict: list[str] | None, tmp_path: Path
) -> None:
    section = "" if option == "version" else "[options]\n"
    literal = py if py.isupper() else repr(py)
    write_project(tmp_path, _named(f"{section}{option} = {cfg}"), f"{option}={literal}")
    metadata, _ = read_setuptools(tmp_path, quiet=True)
    key = "version" if option == "version" else "requires_python"
    candidates = metadata.field_conflicts.get(key)
    assert (None if candidates is None else [c["value"] for c in candidates]) == (
        conflict
    )
    if candidates:
        assert getattr(metadata, key) == candidates[0]["value"]
        assert [c["source"].split(" |")[0] for c in candidates] == [
            "Source: setup.py",
            "Source: setup.cfg",
        ]


def test_a_conflict_warns_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_project(tmp_path, _named("license = Apache-2.0"), "license='MIT'")
    caplog.set_level(logging.WARNING)
    read_setuptools(tmp_path)
    (record,) = caplog.records
    assert "setup.py and setup.cfg disagree on license" in record.getMessage()
    assert "keeping setup.py's" in record.getMessage()


def test_an_installed_conflict_adds_to_the_setuptools_one(tmp_path: Path) -> None:
    """In-tree installed metadata that disagrees too is recorded after the
    ``setup.py``/``setup.cfg`` conflict, not in its place."""
    write_project(tmp_path, _named("license = Apache-2.0"), "name='p', license='MIT'")
    egg_info = tmp_path / "p.egg-info"
    egg_info.mkdir()
    (egg_info / "PKG-INFO").write_text(
        "Metadata-Version: 2.1\nName: p\nVersion: 1.0\nLicense: BSD-3-Clause\n",
        encoding="utf-8",
    )
    metadata = read_project(tmp_path, quiet=True)[0]
    candidates = metadata.field_conflicts["license"]
    assert [c["value"] for c in candidates] == ["MIT", "Apache-2.0", "BSD-3-Clause"]
    assert candidates[2]["source"].startswith("Source: p.egg-info")


@pytest.mark.parametrize(
    ("cfg_name", "py_name", "conflict"),
    [("c", "p", ["p", "c"]), ("My_Pkg", "my-pkg", None)],  # PEP 503 equal
    ids=["different", "same-canonical"],
)
def test_a_different_setup_py_name_is_a_conflict(
    cfg_name: str, py_name: str, conflict: list[str] | None, tmp_path: Path
) -> None:
    write_project(tmp_path, f"[metadata]\nname = {cfg_name}\n", f"name={py_name!r}")
    metadata, _ = read_setuptools(tmp_path, quiet=True)
    assert metadata.name == py_name
    candidates = metadata.field_conflicts.get("name")
    assert (None if candidates is None else [c["value"] for c in candidates]) == (
        conflict
    )
