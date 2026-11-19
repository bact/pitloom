# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The project-metadata and file-discovery lines where a user meets them:
``loom`` in a child process (the exact stderr line, its ``[code]`` and the
exit status), the Hatchling hook, ``loom fragment list`` and the library
(``pitloom_code`` on the raised error).

See also: tests/messages/test_metadata.py (the readers),
tests/messages/test_metadata_relays.py (the relays) and
tests/core/test_project_toml.py (the loader).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.core.creation import CreationMetadata
from pitloom.extract.project.sdist import read_sdist
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import code_of
from tests._code_records import coded
from tests._loom_child import coded_lines, run_loom
from tests.assemble.conftest import _make_sdist
from tests.extract.conftest import make_hook, staged_sbom

pytestmark = pytest.mark.platform

_ARGS = ["--offline", "--creation-datetime", "2026-01-01T00:00:00Z"]
_HEAD = '[project]\nname = "demo"\nversion = "1.0"\n'
#: A ``version`` with a number past the digit cap.
_BIG_VERSION = '[project]\nname = "demo"\nversion = "1.' + "9" * 700 + '"\n'


def _demo(root: Path, **files: str | bytes) -> Path:
    """A project named ``demo`` with a package, plus *files* (``_`` is a
    ``.`` in a name)."""
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "__init__.py").write_bytes(b"")
    for name, content in files.items():
        data = content.encode() if isinstance(content, str) else content
        (root / name.replace("_", ".")).write_bytes(data)
    return root


def _loom(root: Path, *extra: str) -> tuple[int, str]:
    """``loom project`` on *root* in a child process: the exit status and
    stderr, decoded strictly."""
    out = root.parent / f"{root.name}.spdx3.json"
    done = run_loom(["project", str(root), "-o", str(out), *_ARGS, *extra], root.parent)
    return done.returncode, done.stderr.decode("utf-8")


# -- the command line ---------------------------------------------------------


@pytest.mark.parametrize(
    ("files", "code", "part"),
    [
        (
            {"pyproject_toml": _BIG_VERSION},
            "metadata-invalid",
            "project.version has a number over 640 digits",
        ),
        (
            {"pyproject_toml": 'a = 1\r\nb = "x"\r\nc = = 3\r\n'},
            "config-malformed",
            "not valid TOML; ",
        ),
        (
            {"pyproject_toml": b"\xff\xfe[project]\n"},
            "file-unreadable/not-utf8",
            "could not read for the project metadata; ",
        ),
        ({"pyproject_toml": "project = 'x'\n"}, "metadata-invalid", "[project] is "),
        (
            {"pyproject_toml": "[project]\nname = 5\n"},
            "metadata-invalid",
            "project.name is an integer 5, expected a string",
        ),
        (
            {"setup_cfg": "[metadata\nname = demo\n"},
            "config-malformed",
            "not valid INI; ",
        ),
        (
            {"setup_cfg": "[metadata]\nname = demo\nversion = 100%\n"},
            "config-malformed",
            "not valid INI interpolation; ",
        ),
        (
            {"setup_cfg": "[metadata]\nversion = 1\n"},
            "project-name-missing",
            "no project name in setup.cfg [metadata]",
        ),
    ],
    ids=[
        "number",
        "crlf-toml",
        "not-utf8",
        "project-string",
        "name-integer",
        "ini",
        "interpolation",
        "no-name",
    ],
)
def test_loom_project_prints_the_error_with_its_code_and_exits_1(
    files: dict[str, str | bytes], code: str, part: str, tmp_path: Path
) -> None:
    root = _demo(tmp_path / "p", **files)
    status, err = _loom(root)
    assert status == 1
    lines = [ln for ln in err.splitlines() if ln.startswith("ERROR: ")]
    assert len(lines) == 1, err  # one line: no stack, no continuation
    (line,) = lines
    assert line.endswith(f" [{code}]")
    assert part in line
    assert line in coded_lines(err.encode())  # a line of the catalogue
    assert "Traceback" not in err and "config file '" not in err


def test_a_toml_error_names_line_3_of_a_crlf_file(tmp_path: Path) -> None:
    root = _demo(tmp_path / "p", pyproject_toml=b'a = 1\r\nb = "x"\r\nc = = 3\r\n')
    _, err = _loom(root)
    assert "line 3, column" in err


_CFG = "[metadata]\nname = real\nversion = 1.2.3\n"


def test_loom_project_says_a_project_table_with_no_name_as_a_warning(
    tmp_path: Path,
) -> None:
    root = _demo(
        tmp_path / "p", pyproject_toml='[project]\nname = ""\n', setup_cfg=_CFG
    )
    status, err = _loom(root)
    assert status == 0, err
    (line,) = [ln for ln in err.splitlines() if "[metadata-invalid]" in ln]
    assert line.startswith("WARNING: FILE=") and line.endswith(" [metadata-invalid]")
    assert "[project] has no name" in line
    assert line in coded_lines(err.encode())


def test_loom_project_prints_nothing_for_a_build_system_only_layout(
    tmp_path: Path,
) -> None:
    """Absent data is not a metadata warning: a legacy layout has no
    ``[project]`` table, so only file discovery says so (it has no table to
    read the files from), not the metadata reader, even with ``-v``."""
    root = _demo(
        tmp_path / "p",
        pyproject_toml='[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "custom_wrapper"\n',
        setup_cfg=_CFG,
    )
    for extra in ((), ("-v",)):
        status, err = _loom(root, *extra)
        assert status == 0, err
        said = [ln for ln in err.splitlines() if ln.startswith(("WARNING", "ERROR"))]
        # Only file discovery speaks (the backend is unknown to it); the
        # metadata reader says nothing about the missing [project] table.
        assert said and all(ln.endswith(" [file-discovery-needs-build]") for ln in said)
        assert "no [tool.poetry] fallback" not in err  # the DEBUG line stays DEBUG


def test_loom_project_says_why_setup_py_failed_before_the_missing_name(
    tmp_path: Path,
) -> None:
    """D2: two lines, each one cause: the ``setup.py`` that is no Python (a
    ``WARNING:``, relayed), then the name nothing gives (the ``ERROR:``)."""
    root = _demo(tmp_path / "p", setup_py="setup(name='demo'\n")
    status, err = _loom(root)
    assert status == 1
    lines = [ln for ln in err.splitlines() if ln.startswith(("WARNING", "ERROR"))]
    assert [ln.rpartition(" ")[2] for ln in lines] == [
        "[metadata-malformed]",
        "[project-name-missing]",
    ]
    assert "not valid Python; " in lines[0] and "Could not parse" not in err
    assert all(ln in coded_lines(err.encode()) for ln in lines)


def test_loom_fragment_list_names_a_bad_pyproject_with_its_code(tmp_path: Path) -> None:
    root = _demo(tmp_path / "p", pyproject_toml='[project\nname = "demo"\n')
    done = run_loom(["fragment", "list", "--project-dir", str(root)], tmp_path)
    err = done.stderr.decode("utf-8")
    assert done.returncode == 1
    (line,) = [ln for ln in err.splitlines() if ln.startswith("ERROR: ")]
    assert line.endswith(" [config-malformed]")
    assert f"FILE={root / 'pyproject.toml'}: not valid TOML; " in line


# -- the hook ----------------------------------------------------------------


def _hook(root: Path, caplog: pytest.LogCaptureFixture) -> Path | None:
    build_data: dict[str, Any] = {}
    hook = make_hook(str(root), {})
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        hook.initialize("standard", build_data)
        hook.finalize("standard", build_data, "")
    return staged_sbom(build_data)


_HATCH = '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'


def test_the_hook_says_a_failed_discoverer_with_its_code(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Hatchling's own heuristic fails (no package directory): the line is
    ``file-discovery-unusable``, the SBOM is still written."""
    root = tmp_path / "p"
    root.mkdir()
    (root / "pyproject.toml").write_text(_HATCH + _HEAD, encoding="utf-8")
    assert _hook(root, caplog) is not None
    unusable = [m for c, m in coded(caplog) if c == "file-discovery-unusable"]
    assert len(unusable) == 1
    assert unusable[0].startswith(f"DIR={root}: Hatchling file discovery failed; ")


def test_the_hook_says_a_poetry_declaration_with_no_effect(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _demo(
        tmp_path / "p",
        pyproject_toml=_HATCH + _HEAD + '[tool.poetry]\ndescription = "d"\n',
    )
    assert _hook(root, caplog) is not None
    said = [m for c, m in coded(caplog) if c == "metadata-no-effect"]
    assert len(said) == 1
    assert "[tool.poetry] description not read" in said[0]


def test_the_hook_fails_the_build_on_a_pyproject_that_is_not_toml(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The hook reads the project's configuration through the same loader:
    the failure carries the code (the build fails, as for any ERROR)."""
    root = tmp_path / "p"
    root.mkdir()
    (root / "pyproject.toml").write_bytes(b"a = = 1\n")
    hook = make_hook(str(root), {})
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with pytest.raises(ValueError) as exc:
            hook.initialize("standard", {})
    assert code_of(exc.value) == "config-malformed"
    assert str(exc.value).startswith(f"FILE={root / 'pyproject.toml'}: not valid TOML")


# -- the library -------------------------------------------------------------


@pytest.mark.parametrize(
    ("files", "code"),
    [
        ({"setup_cfg": "[metadata\nname = demo\n"}, "config-malformed"),
        ({"pyproject_toml": _BIG_VERSION}, "metadata-invalid"),
        ({"pyproject_toml": b"\xff[project]\n"}, "file-unreadable/not-utf8"),
        ({"setup_cfg": "[metadata]\nversion = 1\n"}, "project-name-missing"),
    ],
    ids=["ini", "number", "not-utf8", "no-name"],
)
def test_the_library_raises_the_coded_error(
    files: dict[str, str | bytes], code: str, tmp_path: Path
) -> None:
    root = _demo(tmp_path / "p", **files)
    with pytest.raises((ValueError, FileNotFoundError)) as exc:
        generate_project_sbom(
            root,
            output_path=tmp_path / "sbom.spdx3.json",
            creation_metadata=CreationMetadata(),
            offline=True,
        )
    assert getattr(exc.value, CODE_ATTR) == code


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"pyproject_tail": "[tool.pitloom\nx"}, "config-malformed"),
        ({"members": {"pyproject.toml": b"\xff[x]\n"}}, "file-unreadable/not-utf8"),
    ],
    ids=["toml", "not-utf8"],
)
def test_read_sdist_raises_the_coded_error(
    kwargs: dict[str, object], code: str, tmp_path: Path
) -> None:
    sdist = _make_sdist(tmp_path, **kwargs)  # type: ignore[arg-type]
    with pytest.raises(ValueError) as exc:
        read_sdist(sdist)
    assert code_of(exc.value) == code


def test_a_relay_through_the_library_carries_the_inner_code(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``poetry.lock`` read beside a Poetry table that names nothing: the
    relayed ``WARNING:`` keeps ``project-name-missing`` on its record, once."""
    root = _demo(
        tmp_path / "p",
        pyproject_toml='[tool.poetry]\nversion = "1"\n',
        poetry_lock='[[package]]\nname = "requests"\nversion = "2.31.0"\n'
        'groups = ["main"]\n[metadata]\nlock-version = "2.1"\n',
    )
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        generate_project_sbom(
            root,
            output_path=tmp_path / "sbom.spdx3.json",
            creation_metadata=CreationMetadata(),
            offline=True,
        )
    assert [c for c, _ in coded(caplog)].count("project-name-missing") == 1
