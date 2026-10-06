# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Ground truth for the ``setup.py`` / ``setup.cfg`` merge: Pitloom's read of a
project directory must match the ``METADATA`` real setuptools writes for a copy
of it (``build_meta.prepare_metadata_for_build_wheel``, offline).

Each row gives a literal ``expect`` that both sides must equal, and ``differ``
for the accepted differences, asserted as ``(Pitloom, built)``:

* a placeholder licence (``UNKNOWN``) gives way to a real one in the other file
  (Pitloom), where setuptools writes the ``setup()`` placeholder;
* ``setup.py`` is read statically: a variable keyword is ignored (Pitloom).

Not compared: ``Home-page`` vs ``Homepage`` key spelling (``urls`` keys are
compared as Pitloom's reader names them on both sides), ``Description`` and
``Classifier`` headers (no comparable ProjectMetadata field).

See also: test_setuptools_merge.py (the merge rule),
test_setuptools_merge_license.py (the licence).
"""

from __future__ import annotations

import email
import os
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any

import pytest

from pitloom.extract.project.installed import read_installed_metadata
from pitloom.extract.project.setuptools import read_setuptools
from tests.extract.project.test_setuptools_merge import write_project

_BUILD = (
    "import sys, setuptools.build_meta as b;"
    " print(b.prepare_metadata_for_build_wheel(sys.argv[1]))"
)
_DEFAULTS: dict[str, Any] = {
    "name": "c",
    "version": "1",
    "description": None,
    "license_name": None,
    "requires_python": None,
    "dependencies": [],
    "keywords": [],
    "author": None,
    "urls": {},
}
_BASE = "[metadata]\nname = c\nversion = 1\n"
_MIT_CLS = "classifiers =\n    License :: OSI Approved :: MIT License\n"
_BSD_CLS = "License :: OSI Approved :: BSD License"


def _built_view(copy: Path, tmp_path: Path) -> dict[str, Any]:
    """Build *copy* with setuptools; the comparable view of its METADATA."""
    out = tmp_path / "out"
    out.mkdir()
    env = {k: v for k, v in os.environ.items() if k != "PYTHONWARNINGS"}
    run = subprocess.run(  # nosec B603
        [sys.executable, "-c", _BUILD, str(out)],
        cwd=copy,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=120,
        check=False,
        env=env,
    )
    assert run.returncode == 0, run.stderr.decode(errors="replace")
    path = next(out.glob("*.dist-info/METADATA"))
    meta = read_installed_metadata(path, "built", quiet=True)
    assert meta is not None
    msg = email.message_from_bytes(path.read_bytes())
    author = (msg.get("Author"), msg.get("Author-email"))
    return _view(meta, author, msg.get_all("Requires-Dist") or [])


def _view(meta: Any, author: tuple[Any, Any], deps: list[str]) -> dict[str, Any]:
    return {
        "name": meta.name,
        "version": meta.version,
        "description": meta.description,
        "license_name": meta.license_name,
        "requires_python": meta.requires_python,
        "dependencies": sorted(deps),
        "keywords": meta.keywords,
        "author": None if author == (None, None) else author,
        "urls": meta.urls,
    }


def _pitloom_view(project: Path) -> dict[str, Any]:
    meta = read_setuptools(project, quiet=True)[0]
    people = [(a.get("name"), a.get("email")) for a in meta.authors]
    return _view(meta, people[0] if people else (None, None), meta.dependencies)


#: (cfg, setup() kwargs, setup.py prelude, expect overrides, differ)
_ROWS: list[Any] = [
    pytest.param(
        "[metadata]\nname = c\nversion = 1.0\ndescription = cfg\nlicense = BSD\n"
        "keywords = x, y\n[options]\npython_requires = >=3.9\n"
        "install_requires = requests\n",
        "name='p', version='2.0', description='py', license='MIT',"
        " keywords=['a', 'b'], python_requires='>=3.8',"
        " install_requires=['numpy']",
        "",
        {
            "name": "p",
            "version": "2.0",
            "description": "py",
            "license_name": "MIT",
            "requires_python": ">=3.8",
            "dependencies": ["numpy"],
            "keywords": ["a", "b"],
        },
        {},
        id="both-real-all",
    ),
    pytest.param(
        _BASE + "classifiers =\n    " + _BSD_CLS + "\n",
        "name=NAME, license='MIT'",
        'NAME = "p"\n',
        {"license_name": "MIT"},
        {"name": ("c", "p")},
        id="py-name-var",
    ),
    pytest.param(
        _BASE + "license = UNKNOWN\n",
        "license='MIT'",
        "",
        {"license_name": "MIT"},
        {},
        id="cfg-unknown-py-mit",
    ),
    pytest.param(
        _BASE + "license = MIT\n",
        "license='UNKNOWN'",
        "",
        {},
        {"license_name": ("MIT", "UNKNOWN")},
        id="cfg-mit-py-unknown",
    ),
    pytest.param(
        "[metadata]\nname = c\nversion = 1.0\n",
        "version=VERSION",
        'VERSION = "2.0"\n',
        {"version": "1.0"},
        {"version": ("1.0", "2.0")},
        id="py-version-var",
    ),
    pytest.param(
        _BASE + "description = cfgd\n",
        "description=''",
        "",
        {"description": "cfgd"},
        {},
        id="py-empty-description",
    ),
    pytest.param(
        _BASE + "[options]\npython_requires =\n",
        "python_requires='>=3.8'",
        "",
        {"requires_python": ">=3.8"},
        {},
        id="cfg-empty-python-requires",
    ),
    pytest.param(
        _BASE + _MIT_CLS,
        "classifiers=['Topic :: Utilities']",
        "",
        {},
        {},
        id="py-classifiers-replace",
    ),
    pytest.param(
        _BASE + "[options]\ninstall_requires = requests\n",
        "install_requires=[]",
        "",
        {"dependencies": ["requests"]},
        {},
        id="py-empty-install-requires",
    ),
    pytest.param(
        _BASE + "author = Cfg\nauthor_email = c@x.org\n",
        "author='Py'",
        "",
        {"author": ("Py", "c@x.org")},
        {},
        id="author-email-split",
    ),
    pytest.param(
        _BASE + "url = https://cfg.example\n",
        "project_urls={'Docs': 'https://d.example'}",
        "",
        {"urls": {"Homepage": "https://cfg.example", "Docs": "https://d.example"}},
        {},
        id="url-project-urls-split",
    ),
    pytest.param(
        _BASE,
        "name=''",
        "",
        {},
        {},
        id="py-name-empty-literal",
    ),
    pytest.param(
        _BASE + "license = MIT\n",
        "license=None",
        "",
        {"license_name": "MIT"},
        {},
        id="py-none-keeps-cfg-license",
    ),
    pytest.param(
        _BASE + "license = MIT\n",
        "classifiers=['" + _BSD_CLS + "']",
        "",
        {"license_name": "MIT"},
        {},
        id="cfg-field-vs-py-classifier",
    ),
    pytest.param(
        _BASE + "license = Apache-2.0\n",
        "license='UNKNOWN', classifiers=['License :: OSI Approved :: MIT License']",
        "",
        {"license_name": "MIT License"},
        {},
        id="weak-py-own-classifier",
    ),
    pytest.param(
        _BASE.replace("\n", "\r\n") + "description = d\r\n",
        "keywords=['k']",
        "",
        {"description": "d", "keywords": ["k"]},
        {},
        id="crlf-setup-cfg",
    ),
]


@pytest.mark.parametrize(("cfg", "py", "prelude", "expect", "differ"), _ROWS)
def test_directory_read_matches_setuptools_build(
    tmp_path: Path,
    cfg: str,
    py: str,
    prelude: str,
    expect: dict[str, Any],
    differ: dict[str, tuple[Any, Any]],
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    write_project(project, None, py)
    (project / "setup.cfg").write_bytes(cfg.encode("utf-8"))
    if prelude:
        text = (project / "setup.py").read_text(encoding="utf-8")
        (project / "setup.py").write_text(prelude + text, encoding="utf-8")
    copy = tmp_path / "copy"
    shutil.copytree(project, copy)

    pitloom = _pitloom_view(project)
    built = _built_view(copy, tmp_path)

    want = {**_DEFAULTS, **expect}
    assert pitloom == {**want, **{k: v[0] for k, v in differ.items()}}
    assert built == {**want, **{k: v[1] for k, v in differ.items()}}
