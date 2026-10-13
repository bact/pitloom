# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Optional dependencies as a built wheel's ``Requires-Dist`` lists them,
read from a directory's ``pyproject.toml`` (the CLI and the Hatchling hook),
``setup.py`` / ``setup.cfg`` and an sdist's ``pyproject.toml`` fallback.

See also: tests/core/test_requirements.py (the shared helper).
"""

from __future__ import annotations

import io
import logging
import tarfile
from pathlib import Path
from typing import Any

import hatchling.metadata.core as hatchling_metadata_core
import pytest
from hatchling.plugin.manager import PluginManager

from pitloom.core.models import compute_doc_uuid
from pitloom.core.project import ProjectMetadata
from pitloom.extract.project import read_project
from pitloom.extract.project.hatchling import metadata_from_hatchling
from pitloom.extract.project.pyproject import read_pyproject
from pitloom.extract.project.sdist import read_sdist
from pitloom.extract.project.setuptools import read_setuptools

from ..conftest import _fake_hatch_metadata, write_pyproject

_HEAD = '[project]\nname = "demo"\nversion = "1.0"\n'
_BOTH = "project.dependencies, project.optional-dependencies"
_ONLY = "project.dependencies"
_OPT = "project.optional-dependencies"
_NO_TABLE = object()

#: (extra [project] lines, expected dependencies, expected provenance field
#: text; _NO_TABLE = no provenance)
_PROJECT_ROWS: list[Any] = [
    pytest.param("", [], _NO_TABLE, id="absent"),
    pytest.param('dependencies = ["a"]\n', ["a"], _ONLY, id="deps-only"),
    pytest.param("optional-dependencies = {}\n", [], _OPT, id="empty-table"),
    pytest.param(
        '[project.optional-dependencies]\ndev = ["b"]\n',
        ['b; extra == "dev"'],
        _OPT,
        id="extras-only",
    ),
    # Limit: expanded as Hatchling writes it; setuptools and flit_core keep
    # `demo[dev]; extra == "all"` (a rewrite, but the same assembled edges).
    pytest.param(
        '[project.optional-dependencies]\ndev = ["b"]\nall = ["demo[dev]"]\n',
        ['b; extra == "all"', 'b; extra == "dev"'],
        _OPT,
        id="self-reference-limit",
    ),
    pytest.param(
        'dependencies = ["a"]\n[project.optional-dependencies]\ndev = []\n',
        ["a"],
        _BOTH,
        id="empty-extra",
    ),
    pytest.param(
        'dependencies = ["a>=1"]\n[project.optional-dependencies]\n'
        'Foo_Bar = ["b", "c; python_version < \'3.11\'"]\n',
        [
            "a>=1",
            'b; extra == "foo-bar"',
            'c; python_version < "3.11" and extra == "foo-bar"',
        ],
        _BOTH,
        id="canonical-name-and-marker",
    ),
    pytest.param(
        'dynamic = ["optional-dependencies"]\ndependencies = ["a"]\n',
        ["a"],
        _ONLY,
        id="dynamic-extras",
    ),
]


def _fields(source: str | None) -> Any:
    return _NO_TABLE if source is None else source.rpartition("Field: ")[2]


@pytest.mark.parametrize(("lines", "expected", "fields"), _PROJECT_ROWS)
def test_directory_routes_list_extras(
    tmp_path: Path,
    lines: str,
    expected: list[str],
    fields: Any,
) -> None:
    """CLI and Hatchling-hook routes give the same list and provenance."""
    # `[project.x]` sub-tables must follow the plain keys of [project]
    write_pyproject(tmp_path, _HEAD + lines)
    path = tmp_path / "pyproject.toml"
    cli, _ = read_pyproject(path)
    hatch = hatchling_metadata_core.ProjectMetadata(str(tmp_path), PluginManager())
    hook = metadata_from_hatchling(hatch, tmp_path)
    assert cli.dependencies == expected
    assert hook.dependencies == expected
    assert _fields(cli.provenance.get("dependencies")) == fields
    assert _fields(hook.provenance.get("dependencies")) == fields
    if fields is not _NO_TABLE:  # one file, named once
        assert cli.provenance["dependencies"] == (
            f"Source: pyproject.toml | Field: {fields}"
        )


@pytest.mark.parametrize(
    "extras",
    [
        pytest.param('dev = ["c", "b"]\nall = ["demo[dev]"]\n', id="one"),
        pytest.param(
            'dev = ["b"]\ntest = ["demo[dev]", "c"]\nall = ["Demo[Test]", "b"]\n',
            id="chain-spelling-repeat",
        ),
        pytest.param('all = ["demo", "x"]\n', id="no-extras"),
    ],
)
def test_self_reference_cli_matches_hook(tmp_path: Path, extras: str) -> None:
    """``demo[dev]`` in an extra: the CLI expands it as Hatchling's own
    ``optional_dependencies`` does for the hook, so both seed the same
    document UUID (Hatchling sorts an extra's requirements: compare sorted)."""
    write_pyproject(tmp_path, _HEAD + "[project.optional-dependencies]\n" + extras)
    cli, _ = read_pyproject(tmp_path / "pyproject.toml")
    hatch = hatchling_metadata_core.ProjectMetadata(str(tmp_path), PluginManager())
    hook = metadata_from_hatchling(hatch, tmp_path)
    assert not [d for d in cli.dependencies if d.startswith("demo")]
    assert sorted(cli.dependencies) == sorted(hook.dependencies)
    assert compute_doc_uuid("demo", "1.0", cli.dependencies) == compute_doc_uuid(
        "demo", "1.0", hook.dependencies
    )


def test_hatchling_fake_declared_empty_table_has_provenance() -> None:
    """A declared empty ``optional-dependencies`` is authoritative (the
    raw key's presence, not the resolved value, gates the provenance)."""
    fake = _fake_hatch_metadata(core={"optional_dependencies": {}})
    meta = metadata_from_hatchling(fake, Path("."))
    assert meta.dependencies == []
    assert meta.provenance["dependencies"].endswith(f"Field: {_OPT}")


@pytest.mark.parametrize(
    ("cfg", "py", "expected", "fields"),
    [
        pytest.param(
            "[options]\ninstall_requires = a\n[options.extras_require]\n"
            "Dev =\n    b\n    c>=1; os_name=='nt'\n",
            None,
            ["a", 'b; extra == "dev"', 'c>=1; os_name == "nt" and extra == "dev"'],
            "options.install_requires, options.extras_require",
            id="cfg-lines",
        ),
        # Limit: setuptools 84 writes `pkg[dev]; extra == "all"` unexpanded.
        pytest.param(
            "[options.extras_require]\ndev = b\nall = pkg[dev]\n",
            None,
            ['b; extra == "all"', 'b; extra == "dev"'],
            "options.extras_require",
            id="cfg-self-reference-limit",
        ),
        pytest.param(
            "[options.extras_require]\n",
            None,
            [],
            "options.extras_require",
            id="cfg-empty-section",
        ),
        pytest.param(
            None,
            "install_requires=['a'], extras_require={'x:os_name==\"nt\"': 'b\\nc;"
            " python_version>\"3\"', ':os_name==\"nt\"': 'e', 'y': ['d', 'bad !!'],"
            " 'z:??': ['q']}",
            [
                "a",
                'e; os_name == "nt"',
                'b; os_name == "nt" and extra == "x"',
                'c; (python_version > "3" and os_name == "nt") and extra == "x"',
                'd; extra == "y"',
            ],
            "setup(install_requires=...), setup(extras_require=...)",
            id="py-newline-string-marker-invalid",
        ),
        pytest.param(
            "[options.extras_require]\ndev = z\n",
            "extras_require={}",  # not given: setup.cfg's stays
            ['z; extra == "dev"'],
            "options.extras_require",
            id="py-empty-keeps-cfg",
        ),
        # As setuptools 84: `v:` has no marker, ` w : ` an invalid blank one
        # (it fails the build), ` u : os_name=="nt"` a valid one.
        pytest.param(
            None,
            "extras_require={' w : ': 'f', 'v:': 'g', ' u : os_name==\"nt\"': 'h'}",
            ['h; os_name == "nt" and extra == "u"', 'g; extra == "v"'],
            "setup(extras_require=...)",
            id="py-key-parts",
        ),
    ],
)
def test_setuptools_extras_require(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    cfg: str | None,
    py: str | None,
    expected: list[str],
    fields: str,
) -> None:
    """``extras_require`` (both files) is listed as a wheel lists it."""
    if cfg is not None:
        (tmp_path / "setup.cfg").write_bytes(f"[metadata]\nname = pkg\n{cfg}".encode())
    if py is not None:
        (tmp_path / "setup.py").write_bytes(
            f"from setuptools import setup\nsetup(name='pkg', {py})\n".encode()
        )
    with caplog.at_level(logging.WARNING):
        meta, _ = read_setuptools(tmp_path)
    assert meta.dependencies == expected
    assert _fields(meta.provenance["dependencies"]) == fields
    for needle in ("bad !!", "z:??", "' w : '"):
        assert (needle in caplog.text) == (needle.strip("'") in (py or ""))


@pytest.mark.parametrize("value", ["['a']", "{'x': 5}", "{1: ['a']}"], ids=str)
def test_setuptools_unreadable_extras_require_is_undeclared(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, value: str
) -> None:
    """A value of a type setuptools would not take gives way to setup.cfg's,
    with a ``WARNING:``."""
    (tmp_path / "setup.cfg").write_text("[options.extras_require]\ndev = z\n")
    (tmp_path / "setup.py").write_text(f"setup(name='pkg', extras_require={value})\n")
    with caplog.at_level(logging.WARNING):
        meta, _ = read_setuptools(tmp_path)
    assert meta.dependencies == ['z; extra == "dev"']
    assert "extras_require" in caplog.text


_CFG_FILE_EXTRA = (
    "setup.cfg",
    "[metadata]\nname = pkg\n[options.extras_require]\na = file: req.txt\n",
    "'file: req.txt' of 'a' (extras_require): not a valid PEP 508 requirement",
)
_PY_MARKER_EXTRA = (
    "setup.py",
    "setup(name='pkg', extras_require={'b:os_name==1': ['c']})\n",
    "'c' of 'b:os_name==1' (extras_require): not a valid PEP 508 requirement or marker",
)


@pytest.mark.parametrize("quiet", [False, True], ids=["warns", "quiet"])
@pytest.mark.parametrize(
    ("filename", "text", "message"),
    [_CFG_FILE_EXTRA, _PY_MARKER_EXTRA],
    ids=["cfg-file", "py-marker"],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_setuptools_invalid_extra_warning_names_extras_require(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    filename: str,
    text: str,
    message: str,
    quiet: bool,
) -> None:
    """The ``WARNING:`` for an unusable ``extras_require`` entry names that
    table; ``read_project(quiet=True)`` (``embed-wheel --project-dir``'s
    peek) records none."""
    (tmp_path / filename).write_text(text)
    with caplog.at_level(logging.WARNING):
        meta = read_project(tmp_path, quiet=quiet)[0]
    assert meta.dependencies == []
    assert caplog.messages == ([] if quiet else [f"Skipping extra entry {message}"])


def _sdist(tmp_path: Path, pyproject: str) -> ProjectMetadata:
    path = tmp_path / "demo-1.0.tar.gz"
    data = pyproject.encode()
    with tarfile.open(path, "w:gz") as tf:
        info = tarfile.TarInfo(name="demo-1.0/pyproject.toml")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    return read_sdist(path)[0]


@pytest.mark.parametrize(("lines", "expected", "fields"), _PROJECT_ROWS)
def test_sdist_pyproject_fallback_lists_extras(
    tmp_path: Path, lines: str, expected: list[str], fields: Any
) -> None:
    """The sdist's ``pyproject.toml`` fallback lists extras too, with the
    directory routes' provenance."""
    meta = _sdist(tmp_path, _HEAD + lines)
    assert meta.dependencies == expected
    assert _fields(meta.provenance.get("dependencies")) == fields


def test_sdist_pyproject_fallback_drops_invalid_extra(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The sdist fallback reads the raw table, so a bad string reaches the
    helper: warned and dropped, never listed as a required dependency."""
    # Hatchling rejects two spellings of one extra; the raw table merges them
    lines = (
        '[project.optional-dependencies]\ndev = ["ok", "not a requirement !!"]\n'
        'Dev = ["more"]\n'
    )
    with caplog.at_level(logging.WARNING):
        meta = _sdist(tmp_path, _HEAD + lines)
    assert meta.dependencies == ['ok; extra == "dev"', 'more; extra == "dev"']
    assert "not a requirement !!" in caplog.text


@pytest.mark.parametrize(
    ("lines", "expected", "needle"),
    [
        pytest.param(
            'optional-dependencies = ["x"]\n', [], "is list", id="table-is-list"
        ),
        pytest.param(
            "[project.optional-dependencies]\ndev = [1]\n",
            [],
            "optional-dependencies.dev' is list",
            id="item-is-int",
        ),
        pytest.param(
            '[project.optional-dependencies]\ndev = "pytest"\n',
            [],
            "optional-dependencies.dev' is str",
            id="value-is-str",
        ),
        pytest.param(
            '[project.optional-dependencies]\ndev = "pytest"\nok = ["a"]\n',
            ['a; extra == "ok"'],
            "optional-dependencies.dev",
            id="other-extra-kept",
        ),
    ],
)
def test_sdist_pyproject_fallback_malformed_extras(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    lines: str,
    expected: list[str],
    needle: str,
) -> None:
    """A wrongly typed extras table or entry is ignored with one ``WARNING:``."""
    with caplog.at_level(logging.WARNING):
        meta = _sdist(tmp_path, _HEAD + lines)
    assert meta.dependencies == expected
    warned = [r.getMessage() for r in caplog.records if needle in r.getMessage()]
    assert len(warned) == 1


@pytest.mark.parametrize("value", ['"x"', '["a"]'], ids=["str", "list"])
def test_sdist_pyproject_fallback_non_table_extras_not_credited(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, value: str
) -> None:
    """A non-table ``optional-dependencies`` is ignored: one ``WARNING:``,
    and the ``dependencies`` provenance does not name it."""
    with caplog.at_level(logging.WARNING):
        meta = _sdist(
            tmp_path, _HEAD + f'dependencies = ["a"]\noptional-dependencies = {value}\n'
        )
    assert meta.dependencies == ["a"]
    assert _fields(meta.provenance["dependencies"]) == _ONLY
    assert len(caplog.records) == 1
    assert "'project.optional-dependencies' is" in caplog.messages[0]
