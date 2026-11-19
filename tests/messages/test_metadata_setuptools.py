# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The setuptools readers' lines through the real readers: a ``setup.cfg``
that cannot be read or parsed (``file-unreadable``, ``config-malformed``), a
``setup.py`` that is no Python (``metadata-malformed``) or does not name the
project (``project-name-missing``), a ``setup()`` keyword Pitloom cannot read
(``metadata-invalid``), two files that disagree (``metadata-conflict``), the
dynamic requirements files a ``pyproject.toml`` lists (``metadata-invalid``,
``metadata-no-effect``) and an ``attr:`` line too deeply nested.

See also: tests/messages/test_metadata_relays.py (``setup.py`` beside
``setup.cfg`` and the dynamic-field relay).
"""

# pylint: disable=protected-access

from __future__ import annotations

import ast
import logging
import sys
import types
from pathlib import Path

import pytest

from pitloom.extract.project import _setup_cfg_directives
from pitloom.extract.project.pyproject import read_pyproject
from pitloom.extract.project.setuptools import read_setuptools
from pitloom.extract.project.setuptools_cfg import read_setup_cfg
from pitloom.extract.project.setuptools_py import read_setup_py, read_setup_py_options
from pitloom.messages import CodedValueError, code_of
from tests._code_records import coded
from tests._unreadable_path import unreadable

pytestmark = pytest.mark.platform

_PY = "from setuptools import setup\nsetup({})\n"
#: A NUL is a ``ValueError`` before Python 3.12, a ``SyntaxError`` after.
_NUL_IS_VALUE_ERROR = sys.version_info < (3, 12)


def _project(root: Path, **files: str | bytes) -> Path:
    root.mkdir(exist_ok=True)
    for name, content in files.items():
        data = content.encode() if isinstance(content, str) else content
        (root / name.replace("_", ".")).write_bytes(data)
    return root


# -- rows 29 to 32: setup.cfg -------------------------------------------------

_CFG = {
    "ini": (b"[metadata\nname = demo\n", "config-malformed", "not valid INI; "),
    "interpolation": (
        b"[metadata]\nname = demo\ndescription = 100% sure\n",
        "config-malformed",
        "not valid INI interpolation; ",
    ),
    "pitloom-interpolation": (
        b"[metadata]\nname = demo\n[tool:pitloom]\ncreation-tool-name = 5%\n",
        "config-malformed",
        "not valid INI interpolation; ",
    ),
    "not-utf8": (
        b"[metadata]\nname = d\x80\xff\n",
        "file-unreadable/not-utf8",
        "for the project metadata; not UTF-8",
    ),
}


@pytest.mark.parametrize("which", sorted(_CFG))
def test_a_setup_cfg_that_cannot_be_parsed_is_coded_naming_the_file_once(
    which: str, tmp_path: Path
) -> None:
    content, code, part = _CFG[which]
    root = _project(tmp_path / "p", setup_cfg=content)
    with pytest.raises(ValueError) as exc:
        read_setup_cfg(root)
    text = str(exc.value)
    assert code_of(exc.value) == code
    assert text.startswith(f"FILE={root / 'setup.cfg'}: ")
    assert part in text
    assert text.count(str(root)) == 1  # the path once, even in a parser's text
    assert "Could not parse" not in text


def test_a_setup_cfg_that_cannot_be_opened_is_unreadable(tmp_path: Path) -> None:
    root = _project(tmp_path / "p", setup_cfg="[metadata]\nname = demo\n")
    with pytest.raises(ValueError) as exc:
        read_setup_cfg(unreadable(root, "setup.cfg"))
    assert code_of(exc.value) == "file-unreadable"
    assert "for the project metadata" in str(exc.value)


def test_a_setup_cfg_without_a_name_is_the_coded_subclass_of_value_error(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path / "p", setup_cfg="[metadata]\nversion = 1\n")
    with pytest.raises(ValueError) as exc:
        read_setup_cfg(root)
    assert isinstance(exc.value, CodedValueError)  # callers catch ValueError
    assert code_of(exc.value) == "project-name-missing"
    assert str(exc.value).startswith(f"FILE={root / 'setup.cfg'}: ")


# -- rows 28, 34, 35: setup.py ------------------------------------------------


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(b"setup(name='a'\n", id="syntax"),
        pytest.param(
            b"setup(name='a')\x00\n",
            id="nul-value-error",
            marks=pytest.mark.skipif(not _NUL_IS_VALUE_ERROR, reason="3.12+"),
        ),
        pytest.param(
            b"setup(name='a')\x00\n",
            id="nul-syntax-error",
            marks=pytest.mark.skipif(_NUL_IS_VALUE_ERROR, reason="before 3.12"),
        ),
    ],
)
def test_a_setup_py_that_is_no_python_is_malformed(
    content: bytes, tmp_path: Path
) -> None:
    root = _project(tmp_path / "p", setup_py=content)
    with pytest.raises(ValueError) as exc:
        read_setup_py_options(root)
    assert code_of(exc.value) == "metadata-malformed"
    assert str(exc.value).startswith(f"FILE={root / 'setup.py'}: not valid Python; ")
    assert "Could not parse" not in str(exc.value)


@pytest.mark.parametrize(
    "error", [RecursionError(), MemoryError()], ids=["deep", "mem"]
)
def test_a_setup_py_nested_too_deeply_is_malformed(
    error: BaseException, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path / "p", setup_py=_PY.format("name='a'"))

    def fail(*_args: object, **_kwargs: object) -> object:
        raise error

    monkeypatch.setattr(
        "pitloom.extract.project.setuptools_py.ast",
        types.SimpleNamespace(**{**vars(ast), "parse": fail}),
    )
    with pytest.raises(ValueError) as exc:
        read_setup_py_options(root)
    assert code_of(exc.value) == "metadata-malformed"


def test_a_setup_py_that_cannot_be_read_is_unreadable_not_malformed(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path / "p", setup_py=_PY.format("name='a'"))
    with pytest.raises(ValueError) as exc:
        read_setup_py_options(unreadable(root, "setup.py"))
    assert code_of(exc.value) == "file-unreadable"


@pytest.mark.parametrize(
    ("name_kw", "line"),
    [("name=compute()", "setup(name=...) is not a string literal"), ("", "")],
    ids=["computed", "absent"],
)
def test_a_setup_py_with_no_literal_name_is_named_for_the_file(
    name_kw: str, line: str, tmp_path: Path
) -> None:
    root = _project(tmp_path / "p", setup_py=_PY.format(name_kw))
    with pytest.raises(ValueError) as exc:
        read_setup_py(root)
    assert code_of(exc.value) == "project-name-missing"
    assert str(exc.value).startswith(f"FILE={root / 'setup.py'}: no project name")
    if line:
        assert line in str(exc.value)


def test_no_name_in_either_file_is_the_directory_line_not_a_stack(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path / "p", setup_cfg="[metadata]\nversion = 1\n")
    with pytest.raises(FileNotFoundError) as exc:
        read_setuptools(root)
    assert code_of(exc.value) == "project-name-missing"
    assert str(exc.value).startswith(f"DIR={root}: no project name in setup.cfg")
    assert "\n" not in str(exc.value)


# -- row 33: a setup() keyword Pitloom cannot read ---------------------------


@pytest.mark.parametrize(
    ("kwargs", "part"),
    [
        ("name='a', **extra", "setup() keyword **extra is not read"),
        ("name='a', version=get()", "setup() keyword version is not a literal"),
        ("name='a', classifiers=5", "keyword classifiers has a value Pitloom does not"),
        ("name='a', version='  '", "setup() keyword version is blank"),
    ],
    ids=["unpacked", "not-literal", "unread", "blank"],
)
@pytest.mark.parametrize("quiet", [False, True], ids=["said", "quiet"])
def test_a_setup_keyword_pitloom_cannot_read_is_treated_as_undeclared(
    kwargs: str,
    part: str,
    quiet: bool,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    root = _project(tmp_path / "p", setup_py=_PY.format(kwargs))
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        read_setup_py_options(root, quiet=quiet)
    said = coded(caplog)
    if quiet:
        assert not said
        return
    ((code, message),) = said
    assert code == "metadata-invalid"
    assert message.startswith(f"FILE={root / 'setup.py'}: ")
    assert part in message
    assert message.endswith("; treated as undeclared")


def test_a_value_pitloom_does_not_read_is_shown_on_one_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _project(
        tmp_path / "p",
        setup_py=_PY.format("name='a', install_requires={'a\\n\\x1b': 1}"),
    )
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        read_setup_py_options(root)
    ((_, message),) = coded(caplog)
    assert "\n" not in message and "\x1b" not in message


# -- row 38: setup.py and setup.cfg disagree --------------------------------


@pytest.mark.parametrize(
    ("cfg", "py", "part"),
    [
        (
            "[metadata]\nname = a\nversion = 1\n",
            _PY.format("name='a', version='2'"),
            "version: setup.py and setup.cfg disagree; kept setup.py's '2', "
            "dropped setup.cfg's '1'",
        ),
        (  # a licence field beats a classifier, whichever file states it
            "[metadata]\nname = a\nlicense = MIT\n",
            _PY.format(
                "name='a', classifiers=['License :: OSI Approved :: Apache Software "
                "License']"
            ),
            "kept setup.cfg's ",
        ),
    ],
    ids=["py-kept", "cfg-kept"],
)
def test_two_setup_files_that_disagree_say_which_was_kept(
    cfg: str, py: str, part: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _project(tmp_path / "p", setup_cfg=cfg, setup_py=py)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        read_setuptools(root)
    ((code, message),) = coded(caplog)
    assert code == "metadata-conflict"
    assert message.startswith(f"DIR={root}: ")
    assert part in message


# -- rows 36, 51, 52: the requirements a pyproject.toml lists ------------------

_DYNAMIC = (
    '[project]\nname = "a"\nversion = "1"\ndynamic = ["dependencies"]\n'
    "[tool.setuptools.dynamic]\n"
)


@pytest.mark.parametrize(
    ("entry", "code", "part"),
    [
        (
            'dependencies = {file = "missing.txt"}',
            "metadata-invalid",
            ", not found; skipped",
        ),
        (
            'dependencies = {file = "a\\u0000b.txt"}',
            "metadata-invalid",
            ", not a file name; skipped",
        ),
        (
            "dependencies = {file = 5}",
            "metadata-invalid",
            "is an integer 5, expected a ",
        ),
        (
            'dependencies = {attr = "x"}',
            "metadata-invalid",
            "has 'attr', not supported",
        ),
        ('dependencies = "x"', "metadata-invalid", "is not a table with 'file'"),
    ],
    ids=["absent", "nul", "file-type", "attr", "not-a-table"],
)
def test_a_dynamic_requirements_entry_pitloom_cannot_use_is_said_with_its_cause(
    entry: str, code: str, part: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _project(tmp_path / "p", pyproject_toml=_DYNAMIC + entry + "\n")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        read_pyproject(root / "pyproject.toml")
    ((got, message),) = coded(caplog)
    assert got == code
    assert "tool.setuptools.dynamic.dependencies" in message
    assert part in message
    assert "could not read" not in message  # not file-unreadable's line


def test_pip_option_lines_in_a_requirements_file_are_named(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _project(
        tmp_path / "p",
        pyproject_toml=_DYNAMIC + 'dependencies = {file = "r.txt"}\n',
        r_txt="-r other.txt\n--index-url x\nrequests\n",
    )
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        metadata, _ = read_pyproject(root / "pyproject.toml")
    assert metadata.dependencies == ["requests"]
    ((code, message),) = coded(caplog)
    assert code == "metadata-no-effect"
    assert (
        "pip option lines --index-url, -r, which setuptools does not accept" in message
    )


# -- row 39: an attr: line too deeply nested ----------------------------------


def test_a_nested_attr_line_is_said_once_per_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    files = {
        "setup_cfg": "[metadata]\nname = a\nversion = attr: m.__version__\n",
        "m_py": "__version__ = '1'\n",
    }
    first = _project(tmp_path / "p", **files)
    second = _project(
        tmp_path / "q",
        setup_cfg=files["setup_cfg"].replace("m.", "n."),
        n_py=files["m_py"],
    )

    def fail(*_args: object, **_kwargs: object) -> object:
        raise RecursionError()

    monkeypatch.setattr(
        _setup_cfg_directives,
        "ast",
        types.SimpleNamespace(**{**vars(ast), "parse": fail}),
    )
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        read_setup_cfg(first)
        read_setup_cfg(first)  # the same file and field again: nothing new
        read_setup_cfg(second)  # another module: said again
    said = coded(caplog)
    assert [c for c, _ in said] == ["metadata-malformed"] * 2
    assert all("too deeply nested to parse; skipped for" in m for _, m in said)
    assert said[0][1].startswith("FILE=m.py: ")
    assert said[1][1].startswith("FILE=n.py: ")
