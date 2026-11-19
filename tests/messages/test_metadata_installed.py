# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The lines of the metadata a project does not state itself, through the
real readers: installed ``.dist-info``/``.egg-info`` directories that are not
the project's or are one of several (``installed-metadata-unusable``,
``installed-metadata-ambiguous``) or disagree with the declared metadata
(``metadata-conflict``); an sdist's ``pyproject.toml`` and ``setup.cfg``
members (``config-malformed``, ``file-unreadable``,
``dynamic-field-needs-build``, ``metadata-invalid``), each naming the archive
member once; a lock file that disagrees with a declared dependency
(``dependency-pin-conflict``, ``requirement-invalid``).

See also: tests/extract/project/test_installed.py (the reader's rules) and
tests/messages/test_metadata_surfaces.py (the surfaces).
"""

# pylint: disable=protected-access

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom.assemble.spdx3.deps_installed import _resolve_version
from pitloom.extract.project import read_project
from pitloom.extract.project.installed import find_installed_metadata_candidate
from pitloom.extract.project.sdist import read_sdist
from pitloom.messages import code_of
from tests._code_records import coded
from tests._unreadable_path import unreadable
from tests.assemble.conftest import _make_sdist

pytestmark = pytest.mark.platform

_LOG = "pitloom"
_PKG_INFO = "Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"


def _project(root: Path, dirs: dict[str, str | None]) -> Path:
    """*root* with ``setup.cfg`` naming ``demo`` and an installed-metadata
    directory per item of *dirs* (name: its marker file's text, or ``None``
    for a directory with no marker)."""
    root.mkdir(exist_ok=True)
    (root / "setup.cfg").write_text(
        "[metadata]\nname = demo\nversion = 1.0\n", encoding="utf-8"
    )
    for name, text in dirs.items():
        path = root / name
        path.mkdir(parents=True, exist_ok=True)
        if text is not None:
            marker = "PKG-INFO" if path.name.endswith(".egg-info") else "METADATA"
            (path / marker).write_text(text, encoding="utf-8")
    return root


# -- rows 45 to 49: installed metadata that is not usable ------------------


@pytest.mark.parametrize(
    ("kwargs", "part"),
    [
        ({"demo.dist-info": None}, "demo.dist-info has no METADATA; ignored"),
        ({"demo.egg-info": None}, "demo.egg-info has no PKG-INFO; ignored"),
        (
            {"demo.dist-info": _PKG_INFO.format(name="other", version="1")},
            "demo.dist-info declares name other, not the project's; ignored",
        ),
        (
            {"demo.dist-info": "Metadata-Version: 2.1\nVersion: 1\n"},
            "demo.dist-info declares no name; ignored",
        ),
    ],
    ids=["no-metadata", "no-pkg-info", "other-name", "no-name"],
)
@pytest.mark.parametrize("quiet", [False, True], ids=["said", "quiet"])
def test_an_installed_directory_that_is_not_the_projects_is_ignored_with_its_cause(
    kwargs: dict[str, str | None],
    part: str,
    quiet: bool,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    root = _project(tmp_path / "p", kwargs)
    with caplog.at_level(logging.WARNING, logger=_LOG):
        assert find_installed_metadata_candidate(root, "demo", quiet=quiet) is None
    said = coded(caplog)
    if quiet:
        assert not said
        return
    ((code, message),) = said
    assert code == "installed-metadata-unusable"
    assert message.startswith(f"DIR={root}: ")
    assert part in message


@pytest.mark.parametrize(
    ("error", "code", "part"),
    [
        (
            PermissionError(13, "denied"),
            "file-unreadable",
            "for the project metadata; denied",
        ),
        (
            FileNotFoundError(2, "gone"),  # gone since the check: as never there
            "installed-metadata-unusable",
            "has no METADATA; ignored",
        ),
    ],
    ids=["denied", "gone"],
)
def test_a_marker_that_cannot_be_read_reaches_the_warning_with_its_error(
    error: OSError,
    code: str,
    part: str,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The ``OSError`` is the failure the line says, not swallowed to a
    ``None`` that reads as an absent file."""
    root = _project(
        tmp_path / "p", {"demo.dist-info": _PKG_INFO.format(name="demo", version="1")}
    )
    with caplog.at_level(logging.WARNING, logger=_LOG):
        found = find_installed_metadata_candidate(
            unreadable(root, "METADATA", error), "demo"
        )
    assert found is None
    ((got, message),) = coded(caplog)
    assert got == code
    assert part in message


# -- row 48: several candidates -----------------------------------------------


@pytest.mark.parametrize("order", [("dist", "egg"), ("egg", "dist")])
def test_several_candidates_pick_a_dist_info_before_an_egg_info_in_any_creation_order(
    order: tuple[str, str], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = tmp_path / "p"
    root.mkdir()
    text = _PKG_INFO.format(name="demo", version="1")
    for kind in order:
        _project(root, {f"demo.{kind}-info": text})
    with caplog.at_level(logging.WARNING, logger=_LOG):
        found = find_installed_metadata_candidate(root, "demo")
    assert found is not None and found[1] == "demo.dist-info"
    ((code, message),) = coded(caplog)
    assert code == "installed-metadata-ambiguous"
    assert message == (
        f"DIR={root}: several installed-metadata candidates "
        "(demo.dist-info, demo.egg-info); used demo.dist-info"
    )


def test_one_matching_candidate_among_wrong_ones_is_no_ambiguity(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _project(
        tmp_path / "p",
        {
            "demo.dist-info": _PKG_INFO.format(name="demo", version="1"),
            "old.egg-info": _PKG_INFO.format(name="other", version="1"),
        },
    )
    with caplog.at_level(logging.WARNING, logger=_LOG):
        found = find_installed_metadata_candidate(root, "demo")
    assert found is not None
    assert [c for c, _ in coded(caplog)] == ["installed-metadata-unusable"]


# -- row 50: the declared and the installed metadata disagree ----------------


@pytest.mark.parametrize("version", ["2.0", "1.0"], ids=["differs", "same"])
def test_a_declared_and_an_installed_version_that_disagree_keep_the_declared(
    version: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _project(
        tmp_path / "p",
        {"demo.dist-info": _PKG_INFO.format(name="demo", version=version)},
    )
    with caplog.at_level(logging.WARNING, logger=_LOG):
        metadata, _, _ = read_project(root)
    assert metadata.version == "1.0"
    said = coded(caplog)
    if version == "1.0":
        assert not said
        return
    ((code, message),) = said
    assert code == "metadata-conflict"
    assert message.startswith(f"DIR={root}: version: declared and installed metadata")
    assert "kept the declared '1.0', dropped the installed '2.0'" in message


# -- rows 53 to 55: a lock file against a declared dependency ----------------


@pytest.mark.parametrize(
    ("dep", "locked", "code", "part"),
    [
        (
            "requests==2.31.0",
            "2.30.0",
            "dependency-pin-conflict",
            "PACKAGE=requests: lock and declared exact pin disagree; kept the "
            "declared '2.31.0', dropped the locked '2.30.0'",
        ),
        (
            "requests>=3",
            "2.0",
            "dependency-pin-conflict",
            "PACKAGE=requests: locked version does not satisfy the declared "
            "constraint; kept the locked '2.0', dropped the declared 'requests>=3'",
        ),
        (
            "requests ((",
            "2.0",
            "requirement-invalid",
            "locked version 2.0 used unchecked",
        ),
    ],
    ids=["exact-pin", "range", "unparseable"],
)
@pytest.mark.parametrize("warn", [True, False], ids=["said", "silent"])
def test_a_lock_that_disagrees_with_a_declaration_is_said_once_with_its_code(
    dep: str,
    locked: str,
    code: str,
    part: str,
    warn: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger=_LOG):
        _resolve_version("requests", dep, locked_version=locked, warn=warn)
    said = coded(caplog)
    if not warn:
        assert not said
        return
    ((got, message),) = said
    assert got == code
    assert part in message


@pytest.mark.parametrize(
    ("dep", "locked"),
    [("requests==2.31.0", "2.31.0"), ("requests>=2", "2.31.0"), ("requests", "1")],
    ids=["same-pin", "satisfied", "unconstrained"],
)
def test_a_lock_that_agrees_with_a_declaration_is_silent(
    dep: str, locked: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger=_LOG):
        _resolve_version("requests", dep, locked_version=locked)
    assert not caplog.records


# -- rows 40 to 43: an sdist's members --------------------------------------


def _sdist_error(tmp_path: Path, **kwargs: object) -> tuple[ValueError, Path]:
    sdist = _make_sdist(tmp_path, **kwargs)  # type: ignore[arg-type]
    with pytest.raises(ValueError) as exc:
        read_sdist(sdist)
    return exc.value, sdist


@pytest.mark.parametrize(
    ("kwargs", "member", "code"),
    [
        ({"pyproject_tail": "[tool.pitloom\nx"}, "pyproject.toml", "config-malformed"),
        (
            {"members": {"pyproject.toml": b"a = = 1\n", "PKG-INFO": None}},
            "pyproject.toml",
            "config-malformed",
        ),
        (
            {"members": {"pyproject.toml": b"\xff\xfe[x]\n"}},
            "pyproject.toml",
            "file-unreadable/not-utf8",
        ),
        (
            {
                "members": {
                    "setup.cfg": b"[tool:pitloom]\nx = \xff\n",
                    "pyproject.toml": b"[build-system]\nrequires = []\n",
                }
            },
            "setup.cfg",
            "file-unreadable/not-utf8",
        ),
    ],
    ids=["bad-toml", "bad-toml-no-pkg-info", "not-utf8-pyproject", "not-utf8-cfg"],
)
def test_an_sdist_member_that_cannot_be_read_names_itself_once(
    kwargs: dict[str, object], member: str, code: str, tmp_path: Path
) -> None:
    """Canaries: no ``config file '...':`` frame before ``FILE=``, and the
    archive member is named once."""
    error, sdist = _sdist_error(tmp_path, **kwargs)
    text = str(error)
    assert code_of(error) == code
    assert text.startswith(f"FILE={sdist}:{member}: ")
    assert text.count("FILE=") == 1 and text.count(str(sdist)) == 1
    assert "config file" not in text
    if code == "file-unreadable/not-utf8":
        assert "for the project metadata" in text


def test_an_sdists_dynamic_fields_with_no_pkg_info_are_named(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sdist = _make_sdist(
        tmp_path,
        members={
            "pyproject.toml": b'[project]\nname = "demo"\n'
            b'dynamic = ["version", "description"]\n',
            "PKG-INFO": None,
        },
    )
    with caplog.at_level(logging.WARNING, logger=_LOG):
        read_sdist(sdist)
    ((code, message),) = coded(caplog)
    assert code == "dynamic-field-needs-build"
    assert message == (
        f"FILE={sdist}:pyproject.toml: dynamic version, description not "
        "resolved without PKG-INFO; skipped"
    )


def test_an_untrusted_extra_name_in_an_sdist_is_one_escaped_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sdist = _make_sdist(
        tmp_path,
        members={
            "pyproject.toml": b'[project]\nname = "demo"\nversion = "1"\n'
            b'[project.optional-dependencies]\n"a\\nb\\u001b[31m" = 5\n',
            "PKG-INFO": None,
        },
    )
    with caplog.at_level(logging.WARNING, logger=_LOG):
        read_sdist(sdist)
    ((code, message),) = coded(caplog)
    assert code == "metadata-invalid"
    assert "\n" not in message and "\x1b" not in message
    assert message.endswith("is an integer 5, expected an array of strings; ignored")
