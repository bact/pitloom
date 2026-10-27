# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A version with a number past Python's int digit limit (``"1." + "9" *
5000``) in a lock file or a pin is an unusable version, not a crash: the
version helpers of :mod:`pitloom.extract.lock.common`, every lock format
through ``loom project``, and a declared pin against a lock.

See also: tests/core/test_pep440.py (the shared bound).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from pitloom.__main__ import main
from pitloom.extract.lock.common import (
    is_same_version,
    is_usable_version,
    parse_exact_pin_requirement,
    version_key,
)
from pitloom.extract.project._field_agreement import values_agree

LONG = "1." + "9" * 5000
_DEP = "nopkg-overlong"
_set_int_limit = getattr(sys, "set_int_max_str_digits", None)


@pytest.fixture(autouse=True)
def _default_int_limit() -> Iterator[None]:
    """Python's default digit limit, set explicitly so the crash this
    guards against does not depend on the environment."""
    if _set_int_limit is None:
        yield
        return
    old = sys.get_int_max_str_digits()  # pylint: disable=no-member
    _set_int_limit(4300)
    yield
    _set_int_limit(old)


def test_version_helpers_treat_an_overlong_version_as_unparseable() -> None:
    """Each helper degrades as for any non-PEP 440 string; ordinary
    versions still compare under PEP 440."""
    assert version_key(LONG) == LONG
    assert not is_usable_version(LONG)
    assert is_same_version(LONG, LONG)
    assert not is_same_version(LONG, "1.0")
    assert is_same_version("1.0", "1.0.0")
    assert not values_agree("version", LONG, "1.0")
    assert not values_agree("requires_python", f">={LONG}", ">=1.0")
    assert values_agree("requires_python", f">={LONG}", f" >={LONG}")


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (f"=={LONG}", None),
        (f"==={LONG}", None),
        (f">=1,<{LONG}", None),
        ("==1.0", ("a", "==", "1.0")),
    ],
    ids=["exact", "arbitrary", "range", "ordinary"],
)
def test_an_overlong_pin_is_no_pin(
    spec: str, expected: tuple[str, str, str] | None
) -> None:
    """Refused before ``packaging`` builds it (25 raises then), whatever
    the operator; an ordinary pin is unchanged."""
    assert parse_exact_pin_requirement(f"a{spec}") == expected


def _uv(project: Path, version: str) -> None:
    (project / "uv.lock").write_text(
        'version = 1\n\n[[package]]\nname = "demo"\nversion = "0.1.0"\n'
        f'source = {{ editable = "." }}\ndependencies = [{{ name = "{_DEP}" }}]\n\n'
        f'[[package]]\nname = "{_DEP}"\nversion = "{version}"\n'
        'source = { registry = "https://pypi.org/simple" }\n',
        encoding="utf-8",
    )


def _pylock(project: Path, version: str) -> None:
    (project / "pylock.toml").write_text(
        'lock-version = "1.0"\ncreated-by = "t"\n\n'
        f'[[packages]]\nname = "{_DEP}"\nversion = "{version}"\n',
        encoding="utf-8",
    )


def _poetry(project: Path, version: str) -> None:
    (project / "poetry.lock").write_text(
        f'[[package]]\nname = "{_DEP}"\nversion = "{version}"\nfiles = []\n\n'
        '[metadata]\nlock-version = "2.0"\ncontent-hash = "x"\n',
        encoding="utf-8",
    )


def _pdm(project: Path, version: str) -> None:
    (project / "pdm.lock").write_text(
        f'[[package]]\nname = "{_DEP}"\nversion = "{version}"\n'
        'groups = ["default"]\n\n[metadata]\nlock_version = "4.5.1"\n',
        encoding="utf-8",
    )


def _pipfile(project: Path, version: str) -> None:
    data = {
        "_meta": {"pipfile-spec": 6},
        "default": {_DEP: {"version": f"=={version}"}},
    }
    (project / "Pipfile.lock").write_text(json.dumps(data), encoding="utf-8")


def _requirements(project: Path, version: str) -> None:
    (project / "requirements.txt").write_text(f"{_DEP}=={version}\n", encoding="utf-8")


def _run_project(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[list[str], str]:
    """``loom project``: the versions of :data:`_DEP` it records, and stderr."""
    out = project.parent / "out.spdx3.json"
    argv = ["loom", "project", str(project), "-o", str(out), "--offline"]
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    assert main() == 0
    graph = json.loads(out.read_text(encoding="utf-8"))["@graph"]
    versions = [
        e.get("software_packageVersion", "") for e in graph if e.get("name") == _DEP
    ]
    return versions, capsys.readouterr().err


@pytest.mark.parametrize(
    "write_lock",
    [_uv, _pylock, _poetry, _pdm, _pipfile, _requirements],
    ids=["uv", "pylock", "poetry", "pdm", "pipfile", "requirements"],
)
def test_an_overlong_locked_version_is_skipped_not_fatal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    write_lock: Callable[[Path, str], None],
) -> None:
    """The entry is refused with the format's own ``WARNING:`` naming it;
    the run succeeds and the declared dependency is still listed, with no
    version from the lock."""
    project = tmp_path / "demo"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        f'[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["{_DEP}"]\n',
        encoding="utf-8",
    )
    write_lock(project, LONG)
    versions, err = _run_project(project, monkeypatch, capsys)
    assert len(versions) == 1
    assert "9" * 100 not in versions[0]
    assert "ERROR:" not in err
    assert any(
        line.startswith("WARNING: ") and _DEP in line for line in err.splitlines()
    )


def test_an_overlong_declared_pin_against_a_lock_is_not_fatal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The declared requirement is not parsed (as any non-PEP 508 one):
    the locked version is used, and a ``WARNING:`` says so."""
    project = tmp_path / "demo"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n'
        f'dependencies = ["{_DEP}=={LONG}"]\n',
        encoding="utf-8",
    )
    _uv(project, "2.0")
    versions, err = _run_project(project, monkeypatch, capsys)
    assert versions == ["2.0"]
    assert "ERROR:" not in err
    assert "larger than the 640-digit version-number cap; not parsed" in err


@pytest.mark.parametrize("key", ["version", "requires-python"])
def test_an_overlong_own_version_fails_as_an_invalid_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    key: str,
) -> None:
    """The project's own ``version``/``requires-python`` (several clauses:
    ``packaging`` 26 fails printing them): one ``ERROR:``, as for any
    invalid value, on every ``packaging`` release."""
    project = tmp_path / "demo"
    project.mkdir()
    fields = {"version": "0.1.0", key: f">=1,<{LONG}" if key != "version" else LONG}
    body = "".join(f'{k} = "{v}"\n' for k, v in fields.items())
    (project / "pyproject.toml").write_text(
        f'[project]\nname = "demo"\n{body}', encoding="utf-8"
    )
    monkeypatch.setattr(sys, "argv", ["loom", "project", str(project), "--offline"])
    monkeypatch.chdir(tmp_path)
    assert main() != 0
    err = capsys.readouterr().err
    assert f"'project.{key}' has a number over 640 digits" in err
    assert "Traceback" not in err


def test_an_overlong_requirement_in_pyproject_is_held_not_fatal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A requirement of several clauses (``packaging`` 26 fails printing
    it) in ``dependencies`` and an extra: held out of
    ``pyproject-metadata``'s parse, the run succeeds."""
    project = tmp_path / "demo"
    project.mkdir()
    dep = f"{_DEP}>=1,<{LONG}"
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n'
        f'dependencies = ["{dep}"]\n'
        f'[project.optional-dependencies]\nx = ["{dep}"]\n',
        encoding="utf-8",
    )
    versions, err = _run_project(project, monkeypatch, capsys)
    assert versions
    assert "ERROR:" not in err
