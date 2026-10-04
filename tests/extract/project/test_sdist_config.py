# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An sdist reads its own ``[tool.pitloom]`` as its unpacked directory does.

The same ``pyproject.toml``/``setup.cfg`` gives the same config (or the same
failure) whether it is read from a directory or from a ``.tar.gz``/``.zip``
of it -- one rule, :func:`pitloom.core.config.select_project_config`, picks
the source for both, by presence of ``[tool.pitloom]``, never by value. Only
``id-registry`` and fragments differ: they cannot apply to an archive, so they
are dropped (documented, not warned).

See also:
- :mod:`tests.extract.project.test_sdist` for sdist metadata and files.
- :mod:`tests.assemble.test_sdist_own_config` for the SBOM it produces.
"""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path

import pytest

from pitloom.core.config import PitloomConfig, pyproject_config_applies
from pitloom.extract.project import read_project, sdist_config_source
from pitloom.extract.project.sdist import CONFIG_MEMBER_MAX_BYTES, read_sdist
from tests.assemble.conftest import _make_sdist

_NAMED = '[project]\nname = "demo"\nversion = "1.0.0"\n'
_UNNAMED = '[build-system]\nrequires = ["setuptools"]\n'
_CFG_PRETTY = (
    "[metadata]\nname = demo\nversion = 1.0.0\n\n[tool:pitloom]\npretty = true\n"
)

#: id -> (root members, the member the config comes from, whether that
#: config differs from the defaults -- so the parity check is not vacuous)
_SHAPES: dict[str, tuple[dict[str, str], str | None, bool]] = {
    "pyproject": (
        {"pyproject.toml": _NAMED + "[tool.pitloom]\npretty = true\n"},
        "pyproject.toml",
        True,
    ),
    "named pyproject beats setup.cfg": (
        {"pyproject.toml": _NAMED, "setup.cfg": _CFG_PRETTY},
        "pyproject.toml",
        False,  # setup.cfg's pretty = true is not read
    ),
    "unnamed empty pyproject defers to setup.cfg": (
        {"pyproject.toml": _UNNAMED, "setup.cfg": _CFG_PRETTY},
        "setup.cfg",
        True,
    ),
    "pyproject config beats setup.cfg even unnamed": (
        {
            "pyproject.toml": _UNNAMED + "[tool.pitloom]\nsbom-basename = 'x'\n",
            "setup.cfg": _CFG_PRETTY,
        },
        "pyproject.toml",
        True,
    ),
    "setup.cfg only": ({"setup.cfg": _CFG_PRETTY}, "setup.cfg", True),
    "tool is not a table": (
        {"pyproject.toml": _NAMED + "tool = 3\n"},
        "pyproject.toml",
        False,
    ),
    "poetry-named pyproject beats setup.cfg": (
        {
            "pyproject.toml": "[tool.poetry]\nname = 'demo'\nversion = '1.0.0'\n",
            "setup.cfg": _CFG_PRETTY,
        },
        "pyproject.toml",
        False,
    ),
    "empty pyproject defers to setup.cfg": (
        {"pyproject.toml": "", "setup.cfg": _CFG_PRETTY},
        "setup.cfg",
        True,
    ),
    # A declared [tool.pitloom] is the user's config even when it sets
    # nothing, or only the defaults: presence decides, never the values.
    "unnamed pyproject with an empty table beats setup.cfg": (
        {"pyproject.toml": _UNNAMED + "[tool.pitloom]\n", "setup.cfg": _CFG_PRETTY},
        "pyproject.toml",
        False,
    ),
    "unnamed pyproject setting a default beats setup.cfg": (
        {
            "pyproject.toml": _UNNAMED + "[tool.pitloom]\npretty = false\n",
            "setup.cfg": _CFG_PRETTY,
        },
        "pyproject.toml",
        False,
    ),
    "creators and comment": (
        {
            "pyproject.toml": _NAMED
            + "[tool.pitloom.creation]\ncreation-comment = 'c'\n"
            + "[[tool.pitloom.creator]]\nname = 'A'\n"
        },
        "pyproject.toml",
        True,
    ),
}


def _directory(tmp_path: Path, members: dict[str, str]) -> Path:
    project = tmp_path / "dir"
    project.mkdir()
    for name, text in members.items():
        (project / name).write_text(text, encoding="utf-8")
    return project


def _sdist(tmp_path: Path, members: dict[str, str], fmt: str) -> Path:
    """An sdist whose root holds exactly *members* (plus PKG-INFO)."""
    root = tmp_path / fmt
    root.mkdir()
    return _make_sdist(
        root,
        members={
            "pyproject.toml": None,
            **{k: v.encode("utf-8") for k, v in members.items()},
        },
        fmt=fmt,
    )


@pytest.mark.parametrize("fmt", ["tar", "zip"])
@pytest.mark.parametrize("shape", list(_SHAPES))
def test_sdist_config_matches_its_directory(
    tmp_path: Path, shape: str, fmt: str
) -> None:
    """Drift guard: one rule for both targets."""
    members, member, changed = _SHAPES[shape]
    _, dir_config, dir_path = read_project(_directory(tmp_path, members))
    sdist = _sdist(tmp_path, members, fmt)
    contents = read_sdist(sdist)
    assert contents.config == dir_config
    assert contents.config_member == member
    # The directory names the same source (what -v labels values with).
    assert dir_path is not None and dir_path.name == member
    assert (contents.config != PitloomConfig()) is changed


@pytest.mark.parametrize("fmt", ["tar", "zip"])
def test_invalid_config_raises_naming_the_member(tmp_path: Path, fmt: str) -> None:
    sdist = _make_sdist(tmp_path, "[tool.pitloom]\npretty = 'yes'\n", fmt=fmt)
    with pytest.raises(ValueError, match=f"{sdist.name}:pyproject.toml"):
        read_sdist(sdist)
    with pytest.raises(ValueError, match=f"{sdist.name}:pyproject.toml"):
        read_project(sdist)


_FMT = pytest.mark.parametrize("fmt", ["tar", "zip"])


@_FMT
def test_invalid_setup_cfg_config_raises_naming_the_member(
    tmp_path: Path, fmt: str
) -> None:
    sdist = _sdist(
        tmp_path,
        {"setup.cfg": "[metadata]\nname = demo\n[tool:pitloom]\npretty = maybe\n"},
        fmt,
    )
    with pytest.raises(ValueError, match=f"{sdist.name}:setup.cfg"):
        read_sdist(sdist)


def test_read_config_false_does_not_parse_the_config(tmp_path: Path) -> None:
    """An explicit config replaces the archive's, so a fault in it cannot
    fail the read; metadata still comes from PKG-INFO."""
    sdist = _make_sdist(tmp_path, "[tool.pitloom]\npretty = 'yes'\n")
    contents = read_sdist(sdist, read_config=False)
    assert contents.config == PitloomConfig()
    assert contents.config_member is None
    assert contents.metadata.name == "demo"
    _, config, path = read_project(sdist, read_config=False)
    assert config == PitloomConfig() and path is None


def test_own_id_registry_is_dropped_silently(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sdist = _make_sdist(tmp_path, "[tool.pitloom]\nid-registry = 'ids.json'\n")
    with caplog.at_level(logging.WARNING):
        config = read_sdist(sdist).config
    assert config.id_registry is None
    assert not caplog.records
    # the directory keeps it: a deliberate difference (as for fragments)
    _, dir_config, _ = read_project(
        _directory(
            tmp_path,
            {"pyproject.toml": _NAMED + "[tool.pitloom]\nid-registry = 'ids.json'\n"},
        )
    )
    assert dir_config.id_registry is not None
    assert dataclasses.replace(dir_config, id_registry=None) == config


def test_read_project_names_the_member(tmp_path: Path) -> None:
    sdist = _make_sdist(tmp_path, "[tool.pitloom]\npretty = true\n")
    _, config, path = read_project(sdist)
    assert config.pretty is True
    assert path == sdist / "pyproject.toml"


@_FMT
def test_nested_pyproject_is_not_the_config(tmp_path: Path, fmt: str) -> None:
    """Only the archive's root ``pyproject.toml`` is the project's."""
    sdist = _make_sdist(
        tmp_path,
        members={"pkg/sub/pyproject.toml": b"[tool.pitloom]\npretty = true\n"},
        fmt=fmt,
    )
    assert read_sdist(sdist).config.pretty is False


@_FMT
def test_first_top_level_directory_wins(tmp_path: Path, fmt: str) -> None:
    """Two top-level directories: the first root-level member in archive
    order is the project's, as for its metadata."""
    sdist = _make_sdist(
        tmp_path,
        "[tool.pitloom]\npretty = true\n",
        members={"/other-2.0/pyproject.toml": b"[tool.pitloom]\npretty = 'bad'\n"},
        fmt=fmt,
    )
    assert read_sdist(sdist).config.pretty is True


def test_dot_slash_tar_member_names_are_root_members(tmp_path: Path) -> None:
    """``tar -czf x.tar.gz ./demo-1.0.0`` stores ``./demo-1.0.0/...``."""
    sdist = _make_sdist(
        tmp_path,
        members={
            "PKG-INFO": None,
            "pyproject.toml": None,
            "/./demo-1.0.0/PKG-INFO": b"Metadata-Version: 2.1\nName: demo\n",
            "/./demo-1.0.0/pyproject.toml": _NAMED.encode()
            + b"[tool.pitloom]\npretty = true\n",
        },
    )
    contents = read_sdist(sdist)
    assert contents.config.pretty is True
    assert contents.config_member == "pyproject.toml"


_OVERSIZE = b"[tool.pitloom]\npretty = true\n#" + b"x" * CONFIG_MEMBER_MAX_BYTES


@_FMT
@pytest.mark.parametrize(
    "raw",
    [
        b'[project]\nname = "demo"\n[tool.pitloom\n',  # not TOML
        b'[project]\nname = "d\xe9mo"\n',  # Latin-1, not UTF-8
        b'\xef\xbb\xbf[project]\nname = "demo"\n',  # BOM: tomllib rejects it
        _OVERSIZE,
    ],
    ids=["invalid-toml", "non-utf8", "bom", "oversize"],
)
def test_unreadable_pyproject_raises_and_never_falls_to_setup_cfg(
    tmp_path: Path, raw: bytes, fmt: str
) -> None:
    """A root ``pyproject.toml`` the config cannot be read from fails the
    read, as a directory's does -- never a silent switch to ``setup.cfg``'s
    ``[tool:pitloom]``. Given an explicit config (``read_config=False``),
    PKG-INFO still gives the metadata."""
    sdist = _make_sdist(
        tmp_path,
        members={"pyproject.toml": raw, "setup.cfg": _CFG_PRETTY.encode()},
        fmt=fmt,
    )
    with pytest.raises(ValueError, match=f"{sdist.name}:pyproject.toml"):
        read_sdist(sdist)
    assert read_sdist(sdist, read_config=False).metadata.name == "demo"


def test_pyproject_at_the_cap_is_read(tmp_path: Path) -> None:
    """Exactly :data:`CONFIG_MEMBER_MAX_BYTES` is read; one more is not."""
    raw = _OVERSIZE[:CONFIG_MEMBER_MAX_BYTES]
    sdist = _make_sdist(tmp_path, members={"pyproject.toml": raw})
    assert read_sdist(sdist).config.pretty is True


@_FMT
def test_unreadable_pyproject_without_pkg_info_still_raises(
    tmp_path: Path, fmt: str
) -> None:
    """No PKG-INFO: the config read still fails; it does not fall back to
    an ``unknown`` project."""
    sdist = _make_sdist(
        tmp_path,
        members={"PKG-INFO": None, "pyproject.toml": b"[project\n"},
        fmt=fmt,
    )
    with pytest.raises(ValueError, match=f"{sdist.name}:pyproject.toml"):
        read_sdist(sdist)


def test_unreadable_pyproject_without_config_logs_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sdist = _make_sdist(tmp_path, members={"pyproject.toml": _OVERSIZE})
    with caplog.at_level(logging.WARNING):
        read_sdist(sdist, read_config=False)
    assert not caplog.records


@_FMT
def test_oversize_first_member_still_wins_over_a_later_one(
    tmp_path: Path, fmt: str
) -> None:
    """Archive order decides even when the first member is over the cap."""
    sdist = _make_sdist(
        tmp_path,
        members={
            "pyproject.toml": _OVERSIZE,
            "/other-2.0/pyproject.toml": b"[tool.pitloom]\npretty = true\n",
        },
        fmt=fmt,
    )
    with pytest.raises(ValueError, match=rf"{sdist.name}:pyproject.toml: over"):
        read_sdist(sdist)


@_FMT
@pytest.mark.parametrize(
    "text",
    [
        "[metadata]\nname = demo\n#" + "x" * CONFIG_MEMBER_MAX_BYTES,  # oversize
        "[metadata]\nname = demo\n[tool:pitloom]\nsbom-basename = 100% x\n",
        "no section header\n",  # not INI
    ],
    ids=["oversize", "interpolation", "not-ini"],
)
def test_unreadable_setup_cfg_raises_naming_it(
    tmp_path: Path, fmt: str, text: str
) -> None:
    sdist = _sdist(tmp_path, {"setup.cfg": text}, fmt)
    with pytest.raises(ValueError, match=f"{sdist.name}:setup.cfg"):
        read_sdist(sdist)


def test_config_source_names_member_and_table(tmp_path: Path) -> None:
    sdist = _make_sdist(
        tmp_path,
        "[tool.pitloom]\npretty = true\n",
        members={"src/demo/pyproject.toml": b"[tool.pitloom]\npretty = 'bad'\n"},
    )
    assert sdist_config_source(sdist) == ("pyproject.toml", {"pretty": True})
    cfg_only = _sdist(tmp_path, {"setup.cfg": _CFG_PRETTY}, "zip")
    assert sdist_config_source(cfg_only) == ("setup.cfg", {})


@_FMT
def test_setup_cfg_without_a_name_gives_the_defaults(tmp_path: Path, fmt: str) -> None:
    """As :func:`read_setup_cfg` for a directory: ``[tool:pitloom]`` counts
    only in a ``setup.cfg`` that names the project."""
    sdist = _sdist(tmp_path, {"setup.cfg": "[tool:pitloom]\npretty = true\n"}, fmt)
    assert read_sdist(sdist).config == PitloomConfig()


def test_config_source_raises_as_the_read_does(tmp_path: Path) -> None:
    """``-v`` re-reads the member; an invalid one fails the same way."""
    sdist = _make_sdist(tmp_path, members={"pyproject.toml": b"not = [toml"})
    with pytest.raises(ValueError, match=f"{sdist.name}:pyproject.toml"):
        sdist_config_source(sdist)


def test_pyproject_metadata_fallback_with_a_non_table_project(
    tmp_path: Path,
) -> None:
    """No PKG-INFO, and ``project`` is not a table: the name is unknown."""
    sdist = _make_sdist(
        tmp_path,
        members={"PKG-INFO": None, "pyproject.toml": b"project = 3\n"},
    )
    assert read_sdist(sdist).metadata.name == "unknown"


@_FMT
def test_a_file_under_a_directory_named_like_a_config_is_not_it(
    tmp_path: Path, fmt: str
) -> None:
    """Only ``<top>/pyproject.toml`` is the root member, not
    ``<top>/pyproject.toml/<file>``."""
    sdist = _sdist(
        tmp_path, {"pyproject.toml/x": "[tool.pitloom]\npretty = true\n"}, fmt
    )
    contents = read_sdist(sdist)
    assert contents.config_member is None
    assert contents.config == PitloomConfig()


def test_oversize_pyproject_without_pkg_info_or_config_warns_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Metadata only (no PKG-INFO, config not read): one ``WARNING:`` naming
    the lost fields, and the name stays unknown."""
    sdist = _make_sdist(
        tmp_path, members={"PKG-INFO": None, "pyproject.toml": _OVERSIZE}
    )
    with caplog.at_level(logging.WARNING):
        assert read_sdist(sdist, read_config=False).metadata.name == "unknown"
    assert len(caplog.records) == 1
    assert "pyproject.toml" in caplog.records[0].getMessage()


@_FMT
def test_percent_outside_tool_pitloom_does_not_fail(tmp_path: Path, fmt: str) -> None:
    """Only ``[tool:pitloom]`` is interpolated: a ``%`` in a ``[metadata]``
    description (metadata comes from PKG-INFO) does not fail the read."""
    sdist = _sdist(
        tmp_path,
        {"setup.cfg": "[metadata]\nname = demo\ndescription = 100% pure\n"},
        fmt,
    )
    assert read_sdist(sdist).config == PitloomConfig()


def test_setup_cfg_parse_error_is_one_line(tmp_path: Path) -> None:
    """``configparser`` spreads a parse error over lines; the ``ERROR:`` a
    CLI prints from it must be one line, naming the file, not ``<string>``."""
    sdist = _sdist(tmp_path, {"setup.cfg": "[metadata]\nname = demo\njunk\n"}, "tar")
    with pytest.raises(ValueError) as info:
        read_sdist(sdist)
    message = str(info.value)
    assert "\n" not in message and "<string>" not in message
    assert f"{sdist.name}:setup.cfg" in message


@pytest.mark.parametrize(
    ("data", "applies"),
    [
        ({}, False),
        ({"tool": {"other": {}}}, False),
        ({"build-system": {"requires": []}}, False),
        ({"tool": {"pitloom": {}}}, True),  # declared, even empty
        ({"tool": {"pitloom": {"pretty": False}}}, True),  # only a default
        ({"project": {"name": "demo"}}, True),
        ({"project": {"name": "  "}}, False),
        ({"tool": {"poetry": {"name": "demo"}}}, True),
        ("not a table", False),
    ],
)
def test_pyproject_config_applies_by_presence(data: object, applies: bool) -> None:
    assert pyproject_config_applies(data) is applies


def test_percent_in_the_project_name_is_read_raw(tmp_path: Path) -> None:
    """``[metadata] name`` is only checked for presence, never interpolated."""
    text = "[metadata]\nname = 100% demo\n[tool:pitloom]\npretty = true\n"
    sdist = _sdist(tmp_path, {"setup.cfg": text}, "tar")
    assert read_sdist(sdist).config.pretty is True


def test_error_names_the_archive_path_as_given(tmp_path: Path) -> None:
    """As ``load_config_file()`` names a ``--config`` path: the directory is
    part of the message, not only the archive's file name."""
    nested = tmp_path / "dist" / "nested"
    nested.mkdir(parents=True)
    sdist = _make_sdist(nested, "[tool.pitloom]\npretty = 'yes'\n")
    with pytest.raises(ValueError) as info:
        read_sdist(sdist)
    assert f"config file {sdist}:pyproject.toml:" in str(info.value)


@_FMT
def test_unused_invalid_setup_cfg_config_fails_neither_target(
    tmp_path: Path, fmt: str
) -> None:
    """The pyproject's declared ``[tool.pitloom]`` applies, so ``setup.cfg``'s
    is never parsed -- an invalid one fails neither the directory nor the
    sdist of the same project."""
    members = {
        "pyproject.toml": _UNNAMED + "[tool.pitloom]\npretty = true\n",
        "setup.cfg": "[metadata]\nname = demo\n[tool:pitloom]\noffline = notabool\n",
    }
    _, dir_config, dir_path = read_project(_directory(tmp_path, members))
    contents = read_sdist(_sdist(tmp_path, members, fmt))
    assert dir_config.pretty is True and contents.config == dir_config
    assert dir_path is not None and dir_path.name == contents.config_member
    # not vacuous: that setup.cfg config is invalid when it is the one used
    members["pyproject.toml"] = _UNNAMED
    (tmp_path / "used").mkdir()
    with pytest.raises(ValueError, match="offline"):
        read_sdist(_sdist(tmp_path / "used", members, fmt))
