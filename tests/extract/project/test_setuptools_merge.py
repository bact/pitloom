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
    return (
        "py" if source.startswith(_PY) else "cfg" if source.startswith(_CFG) else source
    )


_NAMED = "[metadata]\nname = c\n"

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
    # setuptools keeps "  " (truthy) over setup.cfg; Pitloom strips it to none
    pytest.param(
        _NAMED + "description = cfg\n",
        "description='  '",
        {"description": None},
        {"description": None},
        id="py-blank-str",
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
        {"authors": "py"},
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
        {"urls": "py"},
        id="url-split",
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
    if not cfg_named:
        with pytest.raises(FileNotFoundError, match="literal setup.py"):
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
    """A non-literal, an overridden version and an unparseable file, quiet."""
    write_project(tmp_path, _NAMED + "version = 1.0\n", "name=N, version='2.0'")
    caplog.set_level(logging.WARNING)
    read_setuptools(tmp_path, quiet=True)
    (tmp_path / "setup.py").write_text("setup(\n", encoding="utf-8")
    read_setuptools(tmp_path, quiet=True)
    assert not caplog.records


def test_a_nameless_setup_cfg_pitloom_section_is_not_read(tmp_path: Path) -> None:
    """An invalid ``[tool:pitloom]`` cannot fail the read when ``setup.cfg``
    does not name the project; the name then comes from ``setup.py``."""
    write_project(
        tmp_path,
        "[metadata]\ndescription = d\n"
        "[tool:pitloom:creation]\ncreator-name = A\ncreator-type = bogus\n",
        "name='p'",
    )
    metadata, config = read_setuptools(tmp_path)
    assert (metadata.name, metadata.description) == ("p", "d")
    assert not config.creators
