# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Runtime net: every generating surface writes the same provenance key sets
for a hostile input as for a benign one.

Each surface builds one input with the token in every external name it
reads at once (file, directory, archive, member, licence file and metadata
key names) and runs once with ``ok`` and once with a hostile token. Over
the whole SBOM (every Annotation and every provenance comment) each entry
keeps the keys of the benign run: a name read anywhere cannot add or drop a
segment, whichever call site wrote it.

The per-site tests name the field a token reaches; this one does not, so a
new call site that skips the builders shows up here as well as in
tests/test_provenance_builders_lint.py.

See also: tests/provenance_helpers.py (the readers),
tests/test_provenance_hostile_project.py (the per-site rows).
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom import loom
from pitloom.assemble import (
    generate_model_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.core.provenance import (
    ProvenanceConfig,
    escape_provenance_comment_part,
    sanitize_provenance_text,
)
from pitloom.core.untrusted_text import escape_display_controls
from tests.provenance_helpers import Shape, provenance_shape

#: A pipe or a line break cannot be in a file name on Windows.
_POSIX = sys.platform != "win32"
_POSIX_ONLY = pytest.mark.skipif(not _POSIX, reason="pipe/newline in a file name")

_BENIGN = "ok"
_TOKENS = [
    pytest.param(
        "a | Evidence: not_measured | Reason: over-cap", marks=_POSIX_ONLY, id="pipe"
    ),
    pytest.param("a\nb", marks=_POSIX_ONLY, id="newline"),
    pytest.param("a; Field: b", id="semicolon"),
    pytest.param("a\u202eb", id="bidi"),
]
_FULL = ProvenanceConfig(detail="full")
_FIXED = (1980, 1, 1, 0, 0, 0)
_CROISSANT = Path(__file__).parent / "fixtures" / "croissant" / "full.json"
_HEADERS = (
    b"# SPDX-FileCopyrightText: 2026 Jane Doe\n"
    b"# SPDX-License-Identifier: MIT\n"
    b"# SPDX-FileContributor: Jo\n"
    b"# SPDX-FileType: SOURCE\n"
)
_MIT = b"MIT License\n\nCopyright (c) 2020 Jane Doe\n\nPermission is granted.\n"


def _safetensors(metadata: dict[str, str]) -> bytes:
    header = json.dumps(
        {
            "__metadata__": metadata,
            "w": {"dtype": "F32", "shape": [2], "data_offsets": [0, 8]},
        },
        sort_keys=True,
    ).encode()
    return struct.pack("<Q", len(header)) + header + bytes(8)


def _write(root: Path, files: dict[str, bytes]) -> None:
    for name, data in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)


def _zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(zipfile.ZipInfo(name, _FIXED), data)
    return path


# Each builder makes its surface's input in *root*, the token in every name.


def _project(root: Path, token: str) -> str:
    _write(
        root,
        {
            "pyproject.toml": (
                '[project]\nname = "demo"\ndynamic = ["version"]\n'
                f"license = {{file = {json.dumps(f'LIC-{token}')}}}\n"
                f"[tool.hatch.version]\npath = {json.dumps(f'v-{token}.py')}\n"
            ).encode(),
            f"LIC-{token}": b"",
            f"v-{token}.py": b'__version__ = "1.2.3"\n',
            f"demo_{token}.dist-info/METADATA": (
                b"Metadata-Version: 2.1\nName: demo\nVersion: 1.2.3\nSummary: S\n"
            ),
            "src/demo/__init__.py": b"",
            f"src/demo/m{token}.py": _HEADERS,
        },
    )
    return generate_project_sbom(root, offline=True, provenance=_FULL)


def _wheel(root: Path, token: str) -> str:
    root.mkdir()
    wheel = _zip(
        root / f"demo-1.0.0-py3-none-{token}.whl",
        {
            "demo-1.0.0.dist-info/METADATA": (
                b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0.0\n"
                b"License-File: LICENSE\n"
            ),
            "demo-1.0.0.dist-info/RECORD": b"",
            "demo-1.0.0.dist-info/licenses/LICENSE": _MIT,
            "demo/__init__.py": b"",
            f"demo/m{token}.py": _HEADERS,
        },
    )
    return generate_wheel_sbom(wheel, offline=True, provenance=_FULL)


def _sdist(root: Path, token: str) -> str:
    root.mkdir()
    sdist = _zip(
        root / f"demo-1.0.0-{token}.zip",
        {
            "demo-1.0.0/PKG-INFO": b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n",
            "demo-1.0.0/pyproject.toml": b'[project]\nname = "demo"\nversion = "1.0"\n',
            "demo-1.0.0/LICENSE": _MIT,
            "demo-1.0.0/demo/__init__.py": b"",
            f"demo-1.0.0/demo/m{token}.py": _HEADERS,
        },
    )
    return generate_project_sbom(sdist, offline=True, provenance=_FULL)


def _model(root: Path, token: str) -> str:
    root.mkdir()
    model = root / f"w{token}.safetensors"
    model.write_bytes(_safetensors({"name": "m", "license": "mit", token: "v"}))
    return generate_model_sbom(model, provenance=_FULL)


def _loom_dataset(root: Path, token: str) -> str:
    root.mkdir()
    dataset = root / f"data-{token}"
    _write(
        dataset,
        {
            "README.md": (
                b"---\nlicense: mit\npretty_name: Corpus\nversion: '1.0'\n"
                b"tags:\n- nlp\n---\n"
            )
        },
    )
    croissant = root / f"cr-{token}.json"
    shutil.copyfile(_CROISSANT, croissant)
    out = root / "fragment.json"
    cwd = os.getcwd()
    os.chdir(root)
    try:
        with loom.run(out):
            loom.set_model("m", hyperparameters={token: "1"})
            loom.add_dataset(dataset.name, croissant=croissant.name)
    finally:
        os.chdir(cwd)
    return out.read_text(encoding="utf-8")


_SURFACES: dict[str, Callable[[Path, str], str]] = {
    "project": _project,
    "wheel": _wheel,
    "sdist": _sdist,
    "model": _model,
    "loom-dataset": _loom_dataset,
}


def _without_token(shape: Shape, token: str) -> Shape:
    """*shape* with the token, as a field name holds it (a metadata key read
    into ``properties.<key>``), written as the benign run writes it."""
    spellings = {
        spelling
        for text in (token, sanitize_provenance_text(token))
        for escaped in (text, escape_provenance_comment_part(text, field=True))
        for spelling in (escaped, escape_display_controls(escaped))
    }

    def benign(field: str) -> str:
        for spelling in sorted(spellings, key=len, reverse=True):
            field = field.replace(spelling, _BENIGN)
        return field

    return sorted((where, benign(field), keys) for where, field, keys in shape)


@pytest.mark.parametrize("token", _TOKENS)
@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_a_hostile_name_keeps_every_key_set(
    tmp_path: Path, surface: str, token: str
) -> None:
    build = _SURFACES[surface]
    benign = provenance_shape(build(tmp_path / "benign", _BENIGN))
    hostile = provenance_shape(build(tmp_path / "hostile", token))
    # Not vacuous: the benign run has a Source key in the comments and the
    # Annotations alike.
    assert {where for where, _, keys in benign if "source" in keys} == {
        "annotation",
        "comment",
    }
    assert _without_token(hostile, token) == benign
