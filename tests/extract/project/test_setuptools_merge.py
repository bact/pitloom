# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``setup.py`` and ``setup.cfg`` merged as setuptools merges them: a given
``setup()`` keyword overrides the ``setup.cfg`` option, per option.

See also: test_setuptools_merge_license.py (the licence and the conflicts),
test_setuptools_build_parity.py (against real setuptools builds).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom.core.project import ProjectMetadata
from pitloom.extract.project.setuptools import read_setuptools

_PY = "Source: setup.py"
_CFG = "Source: setup.cfg"
_BOTH = "Source: setup.py, setup.cfg"


def write_project(root: Path, cfg: str | None, py: str | None) -> None:
    """``setup.cfg`` with *cfg* as is; ``setup.py`` calling ``setup(<py>)``."""
    # Bytes: no newline translation, so a CRLF row is CRLF on every OS.
    if cfg is not None:
        (root / "setup.cfg").write_bytes(cfg.encode())
    if py is not None:
        (root / "setup.py").write_bytes(
            f"from setuptools import setup\nsetup({py})\n".encode()
        )


def _origin(metadata: ProjectMetadata, key: str) -> str | None:
    source = metadata.provenance.get(key)
    if source is None:
        return None
    for origin, prefix in (("both", _BOTH), ("py", _PY), ("cfg", _CFG)):
        if source.startswith(prefix):
            return origin
    return source


_NAMED = "[metadata]\nname = c\n"
_BAD_CONFIG = "[tool:pitloom:creation]\ncreator-name = A\ncreator-type = bogus\n"

#: (cfg, py, expected fields, expected provenance origin per key; None = no
#: provenance)
_ROWS: list[Any] = [
    pytest.param(
        "[metadata]\nname = c\nversion = 1.0\ndescription = cfg\nkeywords = x, y\n"
        "[options]\npython_requires = >=3.9\ninstall_requires = requests\n",
        "name='p', version='1.0', description='py', keywords=['a'],"
        " python_requires='>=3.8', install_requires=['numpy']",
        {
            "name": "p",
            "description": "py",
            "keywords": ["a"],
            "requires_python": ">=3.8",
            "dependencies": ["numpy"],
        },
        {"name": "py", "description": "py", "keywords": "py", "dependencies": "py"},
        id="both-real",
    ),
    pytest.param(
        "[metadata]\ndescription = d\n",
        "name='p'",
        {"name": "p", "description": "d"},
        {"name": "py", "description": "cfg"},
        id="cfg-nameless",
    ),
    pytest.param(
        _NAMED,
        "name=NAME, version='2.0', install_requires=['numpy']",
        {"name": "c", "version": "2.0", "dependencies": ["numpy"]},
        {"name": "cfg", "version": "py", "dependencies": "py"},
        id="py-name-var",
    ),
    pytest.param(
        _NAMED,
        "name='', version='2.0'",
        {"name": "c"},
        {"name": "cfg"},
        id="py-name-empty",
    ),
    pytest.param(
        _NAMED + "description = cfg\n",
        "description=''",
        {"description": "cfg"},
        {"description": "cfg"},
        id="py-empty-str",
    ),
    pytest.param(
        _NAMED + "description = cfg\n",
        "description=None",
        {"description": "cfg"},
        {"description": "cfg"},
        id="py-none",
    ),
    pytest.param(
        _NAMED,
        "install_requires=[]",
        {"dependencies": []},
        {"dependencies": "py"},
        id="py-empty-list-alone",
    ),
    pytest.param(
        _NAMED + "[options]\ninstall_requires = requests\n",
        "install_requires=[]",
        {"dependencies": ["requests"]},
        {"dependencies": "cfg"},
        id="py-empty-list",
    ),
    pytest.param(
        _NAMED + "[options]\ninstall_requires = requests\n",
        "install_requires=DEPS",
        {"dependencies": ["requests"]},
        {"dependencies": "cfg"},
        id="py-list-var",
    ),
    pytest.param(
        _NAMED + "[options]\npython_requires =\n",
        "python_requires='>=3.8'",
        # an empty value overridden is no conflict
        {"requires_python": ">=3.8", "field_conflicts": {}},
        {"requires_python": "py"},
        id="cfg-empty-py-real",
    ),
    pytest.param(
        _NAMED + "[options]\npython_requires =\n",
        "",
        {"requires_python": None},
        {"requires_python": "cfg"},
        id="cfg-empty-alone",
    ),
    pytest.param(
        "[DEFAULT]\nauthor = D\n" + _NAMED,
        "",
        {"authors": [{"name": "D"}]},
        {"authors": None},
        id="default-inherited",
    ),
    pytest.param(
        "[DEFAULT]\nauthor = D\n" + _NAMED,
        "author='P'",
        {"authors": [{"name": "P"}]},
        {"authors": "py"},
        id="default-overridden",
    ),
    pytest.param(
        _NAMED + "author = C\nauthor_email = c@x.org\n",
        "author='P'",
        {"authors": [{"name": "P", "email": "c@x.org"}]},
        {"authors": "both"},
        id="author-split",
    ),
    pytest.param(
        _NAMED + "author =\n",
        "author='P'",
        {"authors": [{"name": "P"}]},
        {"authors": "py"},
        id="cfg-author-empty",
    ),
    pytest.param(
        _NAMED + "author_email = c@x.org\n",
        "author=''",
        {"authors": [{"email": "c@x.org"}]},
        {"authors": "cfg"},
        id="py-author-empty-cfg-email",
    ),
    pytest.param(
        _NAMED + "project_urls =\n    S = https://s\n",
        "url=''",
        {"urls": {"S": "https://s"}},
        {"urls": "cfg"},
        id="py-url-empty-cfg-urls",
    ),
    pytest.param(
        _NAMED + "author = C\n",
        "author=''",
        {"authors": [{"name": "C"}]},
        {"authors": "cfg"},
        id="py-author-empty",
    ),
    pytest.param(
        None,
        "name='p', author_email='e@x.org'",
        {"authors": [{"email": "e@x.org"}]},
        {"authors": "py"},
        id="py-email-only",
    ),
    pytest.param(
        _NAMED + "project_urls =\n    Source = https://s.example\n",
        "url='https://py.example'",
        {"urls": {"Homepage": "https://py.example", "Source": "https://s.example"}},
        {"urls": "both"},
        id="url-split",
    ),
    pytest.param(
        _NAMED + "description = A\nsummary = B\n",
        None,
        {"description": "A"},
        {"description": "cfg"},
        id="cfg-description-over-summary",
    ),
    pytest.param(
        _NAMED + "description =\nsummary = B\n",
        None,
        {"description": "B"},
        {"description": "cfg"},
        id="cfg-summary",
    ),
    pytest.param(
        _NAMED + "author_email = a@b.c\n",
        None,
        {"authors": [{"email": "a@b.c"}]},
        {"authors": "cfg"},
        id="cfg-email-only",
    ),
    pytest.param(
        _NAMED.replace("\n", "\r\n") + "license = MIT\r\n",
        None,
        {"name": "c", "license_name": "MIT"},
        {"license": "cfg"},
        id="cfg-crlf",
    ),
]


@pytest.mark.parametrize(("cfg", "py", "fields", "origins"), _ROWS)
def test_setup_py_overrides_setup_cfg_per_option(
    cfg: str | None,
    py: str | None,
    fields: dict[str, Any],
    origins: dict[str, str | None],
    tmp_path: Path,
) -> None:
    write_project(tmp_path, cfg, py)
    metadata, _ = read_setuptools(tmp_path, quiet=True)
    assert {k: getattr(metadata, k) for k in fields} == fields
    assert {k: _origin(metadata, k) for k in origins} == origins
    # inferred from the authors kept, never from the other file's
    inferred = bool(metadata.authors) and "authors" in metadata.provenance
    assert ("copyright_text" in metadata.provenance) is inferred


@pytest.mark.parametrize(
    ("cfg", "py", "key", "fields"),
    [
        (
            "author = C\n",
            "author_email='p@x.org'",
            "authors",
            "setup(author=...), metadata.author/author_email",
        ),
        (
            "url = https://c\n",
            "project_urls={'S': 'https://s'}",
            "urls",
            "setup(url=...), metadata.url/project_urls",
        ),
    ],
    ids=["cfg-author-py-email", "cfg-url-py-urls"],
)
def test_a_field_built_from_both_files_names_both(
    cfg: str, py: str, key: str, fields: str, tmp_path: Path
) -> None:
    """setup.py first, whichever file states which part."""
    write_project(tmp_path, _NAMED + cfg, py)
    metadata, _ = read_setuptools(tmp_path, quiet=True)
    assert metadata.provenance[key] == f"{_BOTH} | Field: {fields}"


@pytest.mark.parametrize(
    ("py", "cfg", "field", "expected", "warning"),
    [
        # setuptools keeps "  " over setup.cfg's; Pitloom has no value in it
        ("description='  '", "description = d", "description", "d", "is blank"),
        ("license=' '", "license = MIT", "license_name", "MIT", "is blank"),
        # types setuptools takes
        ("version=1.5", "version = 2.0", "version", "1.5", None),
        # setuptools normalises these first: "0" is given, [] is not
        ("version=0", "version = 2.0", "version", "0", None),
        (
            "install_requires=['# x']",
            "[options]\ninstall_requires = z",
            "dependencies",
            ["z"],
            None,
        ),
        ("classifiers=None", "license = MIT", "license_name", "MIT", None),
        (
            "install_requires='x>=1 # c\\n# c\\ny \\\\\\n  >=2'",
            "[options]\ninstall_requires = z",
            "dependencies",
            ["x>=1", "y>=2"],
            None,
        ),
        (
            "install_requires=['x>=1 # c', '# c', 'y \\\\', '>=2']",
            "[options]\ninstall_requires = z",
            "dependencies",
            ["x>=1", "y>=2"],
            None,
        ),
        (
            "url='u', project_urls={'Homepage': 'h'}",
            "",
            "urls",
            {"Homepage": "h"},  # project_urls after url
            None,
        ),
        # types Pitloom cannot read: setup.cfg's is used, not lost
        ("version=True", "version = 2.0", "version", "2.0", "(True)"),
        ("version=1e999", "version = 2.0", "version", "2.0", "(inf)"),
        ("version=0x" + "f" * 4000, "version = 2.0", "version", "2.0", "(<int>)"),
        ("url=1", "url = https://c", "urls", {"Homepage": "https://c"}, "(1)"),
        (
            "project_urls={'a': 1}",
            "project_urls =\n    a = https://c",
            "urls",
            {"a": "https://c"},
            "({'a': 1})",
        ),
        ("classifiers='x'", "license = MIT", "license_name", "MIT", "('x')"),
        (
            "install_requires=[1]",
            "[options]\ninstall_requires = z",
            "dependencies",
            ["z"],
            "([1])",
        ),
    ],
    ids=[
        "blank-str",
        "blank-licence",
        "number-version",
        "zero-version",
        "comment-requirements",
        "none-classifiers",
        "str-requirements",
        "list-requirements",
        "url-and-project-urls",
        "bool-version",
        "inf-version",
        "huge-int-version",
        "int-url",
        "int-url-value",
        "str-classifiers",
        "int-requirement",
    ],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_a_setup_py_value_setuptools_would_take_or_reject(
    py: str,
    cfg: str,
    field: str,
    expected: Any,
    warning: str | None,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    write_project(tmp_path, f"{_NAMED}{cfg}\n", py)
    caplog.set_level(logging.WARNING)
    metadata, _ = read_setuptools(tmp_path)
    assert getattr(metadata, field) == expected
    # the conflict WARNING of a real overridden version aside
    unusable = [
        r.getMessage() for r in caplog.records if "undeclared" in r.getMessage()
    ]
    assert len(unusable) == (warning is not None)
    if warning is not None:
        assert warning in unusable[0]


@pytest.mark.parametrize(
    "content",
    [
        b"[metadata]\nname = c\n[metadata]\n",
        b"name = c\n",
        b"[metadata]\nname = c\ndescription = 100% pure\n",
        b"[metadata]\nname = \xe9\n",
        b"[metadata]\nname = c\n[tool:pitloom]\npretty = 100% x\n",
    ],
    ids=[
        "duplicate-section",
        "no-section",
        "interpolation",
        "not-utf8",
        "pitloom-interpolation",
    ],
)
def test_an_unreadable_setup_cfg_is_one_error_line(
    content: bytes, tmp_path: Path
) -> None:
    """Never skipped, never a multi-line ``ERROR:``; with a ``setup.py`` too."""
    write_project(tmp_path, None, "name='p'")
    (tmp_path / "setup.cfg").write_bytes(content)
    with pytest.raises(ValueError, match="^Could not parse setup.cfg: ") as caught:
        read_setuptools(tmp_path)
    assert "\n" not in str(caught.value)


@pytest.mark.parametrize(
    "source",
    [b"setup(\n", b"setup(name='p')\x00\n", b"setup(name='\xe9')\n"],
    ids=["syntax", "null-byte", "not-utf8"],
)
@pytest.mark.parametrize("cfg_named", [True, False], ids=["cfg", "no-cfg"])
def test_an_unparseable_setup_py_warns_only_beside_a_named_setup_cfg(
    source: bytes, cfg_named: bool, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_project(tmp_path, _NAMED if cfg_named else "[metadata]\n", None)
    (tmp_path / "setup.py").write_bytes(source)
    caplog.set_level(logging.WARNING)
    if not cfg_named:  # the cause is named in the one error
        with pytest.raises(FileNotFoundError, match="Could not parse setup.py"):
            read_setuptools(tmp_path)
        assert not caplog.records
        return
    assert read_setuptools(tmp_path)[0].name == "c"
    (record,) = caplog.records
    assert "Could not parse setup.py" in record.getMessage()
    assert "reading setup.cfg alone" in record.getMessage()


def test_quiet_silences_every_setuptools_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A non-literal, a blank, an unread type, an overridden version and an
    unparseable file, quiet."""
    write_project(
        tmp_path,
        _NAMED + "version = 1.0\n",
        "name=N, version='2.0', description=' ', url=1",
    )
    caplog.set_level(logging.WARNING)
    read_setuptools(tmp_path, quiet=True)
    (tmp_path / "setup.py").write_text("setup(\n", encoding="utf-8")
    read_setuptools(tmp_path, quiet=True)
    assert not caplog.records


@pytest.mark.parametrize(
    ("source", "name"),
    [
        (b"\xef\xbb\xbfsetup(name='p')\n", "p"),
        (b"# -*- coding: latin-1 -*-\nsetup(name='\xe9')\n", "\xe9"),
    ],
    ids=["bom", "coding-line"],
)
def test_setup_py_encoding_is_read_as_python_reads_it(
    source: bytes, name: str, tmp_path: Path
) -> None:
    (tmp_path / "setup.py").write_bytes(source)
    assert read_setuptools(tmp_path)[0].name == name


def test_a_setup_cfg_directory_is_no_setup_cfg(tmp_path: Path) -> None:
    """As for setuptools: the project is built from ``setup.py`` alone."""
    write_project(tmp_path, None, "name='p'")
    (tmp_path / "setup.cfg").mkdir()
    assert read_setuptools(tmp_path)[0].name == "p"


@pytest.mark.parametrize(
    "cfg",
    [
        # not named: [tool:pitloom] is never parsed
        "[metadata]\nname =\n" + _BAD_CONFIG,
        # named, but its config replaced by the caller (read_config=False)
        _NAMED + _BAD_CONFIG,
    ],
    ids=["unnamed", "not-read"],
)
def test_an_unused_pitloom_section_cannot_fail_the_read(
    cfg: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_project(tmp_path, cfg, "name='p'")
    read_config = "name =\n" in cfg
    metadata, config = read_setuptools(tmp_path, read_config=read_config)
    assert metadata.name in {"p", "c"}
    assert not config.creators
    # an unnamed setup.cfg with an unparseable setup.py: one error, no WARNING
    (tmp_path / "setup.py").write_bytes(b"setup(\n")
    caplog.set_level(logging.WARNING)
    if read_config:
        with pytest.raises(FileNotFoundError):
            read_setuptools(tmp_path)
        assert not caplog.records
