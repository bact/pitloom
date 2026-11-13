# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Byte-identical wheel and sdist builders, a fake PyPI publishing them,
and readers of the acquisition record, for the ``generate_pypi_sbom`` tests.

Every archive is built with fixed dates (``ZipInfo`` at 1980, ``TarInfo``
and the gzip header at 0), so two builds give the same bytes on a clock
that moves.

See also: tests/_fake_pypi_server.py (the server),
tests/assemble/test_generate_pypi.py and test_generate_pypi_provenance.py.
"""

from __future__ import annotations

import gzip
import io
import json
import tarfile
import tempfile
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from packaging.tags import Tag

from pitloom.core.creation import CreationMetadata
from pitloom.extract.remote import pypi_select
from pitloom.messages import (
    Line,
)
from pitloom.messages.pypi import (
    PYPI_FILE_LINK_LINE,
    PYPI_INDEX_LINE,
    PYPI_OLD_HOST_LINE,
)
from tests._fake_pypi_server import Dist, FakePypi, point_at, publish, serving

NAME = "demo"
VERSION = "1.0.0"
WHEEL_NAME = f"{NAME}-{VERSION}-py3-none-any.whl"
CP_WHEEL_NAME = f"{NAME}-{VERSION}-cp313-cp313-linux_x86_64.whl"
SDIST_NAME = f"{NAME}-{VERSION}.tar.gz"
PAGE = "https://pypi.org/project/"
URL = f"{PAGE}{NAME}/{VERSION}/"
#: The running environment's tag order every test sees.
TAGS = [Tag("cp313", "cp313", "linux_x86_64"), Tag("py3", "none", "any")]
#: A creation time, so two runs (and two surfaces) give the same bytes.
CREATION = CreationMetadata(creation_datetime="2026-11-10T00:00:00Z")
#: A field only the acquisition record writes.
RECORD_FIELD = "sha256_declared"
#: ``pypi.org`` spelled with a trailing dot: read as ``pypi.org``.
DOTTED = f"https://pypi.org./project/{NAME}/{VERSION}/"
#: Each refused spelling of a PyPI-family host and the line refusing it.
REFUSED: list[tuple[str, Line]] = [
    (f"https://test.pypi.org/project/{NAME}/", PYPI_INDEX_LINE),
    (f"https://TEST.pypi.org./project/{NAME}/{VERSION}/", PYPI_INDEX_LINE),
    (f"https://pypi.python.org/pypi/{NAME}", PYPI_OLD_HOST_LINE),
    (
        f"https://files.pythonhosted.org/packages/ab/cd/{WHEEL_NAME}",
        PYPI_FILE_LINK_LINE,
    ),
    (f"https://Files.PythonHosted.org./packages/{SDIST_NAME}", PYPI_FILE_LINK_LINE),
    # Spellings a resolver (curl, git) maps to the PyPI host: an ideographic,
    # full-width or half-width ideographic dot, a percent-encoded one.
    (f"https://test\u3002pypi.org/project/{NAME}/", PYPI_INDEX_LINE),
    (f"https://test.pypi.org%2E/project/{NAME}/", PYPI_INDEX_LINE),
    (f"https://pypi%2Epython%2eorg/pypi/{NAME}", PYPI_OLD_HOST_LINE),
    (
        f"https://files\uff0epythonhosted\uff61org/packages/{WHEEL_NAME}",
        PYPI_FILE_LINK_LINE,
    ),
]
REFUSED_IDS = [
    "test-index",
    "test-index-dot",
    "old-host",
    "file-link",
    "file-link-dot",
    "test-index-ideographic",
    "test-index-encoded-dot",
    "old-host-encoded",
    "file-link-full-width",
]
#: ``pypi.org`` as a resolver maps it, each read as ``pypi.org`` and never
#: taken for a Git host.
SPELLED = [
    f"https://pypi\u3002org/project/{NAME}/{VERSION}/",
    f"https://pypi\uff0eorg/project/{NAME}/{VERSION}/",
    f"https://pypi%2Eorg/project/{NAME}/{VERSION}/",
    f"https://pypi.org%2e/project/{NAME}/{VERSION}/",
]
SPELLED_IDS = ["ideographic", "full-width", "encoded", "encoded-trailing"]


def wheel_bytes(name: str = NAME, version: str = VERSION) -> bytes:
    """A minimal wheel of *name* *version*, the same bytes every time."""
    dist_info = f"{name}-{version}.dist-info"
    members = {
        f"{name}/__init__.py": b'"""Demo."""\n',
        f"{dist_info}/METADATA": (
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
            "License-Expression: MIT\n"
        ).encode(),
        f"{dist_info}/WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\n",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for member, data in members.items():
            info = zipfile.ZipInfo(member, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    return buffer.getvalue()


def sdist_bytes(
    pyproject_tail: str = "", extra: Mapping[str, bytes] | None = None
) -> bytes:
    """A minimal ``demo-1.0.0`` sdist, *pyproject_tail* appended to its
    ``pyproject.toml`` and the *extra* members (path below the root ->
    bytes) added, the same bytes every time."""
    root = f"{NAME}-{VERSION}"
    members = {
        **{f"{root}/{name}": data for name, data in (extra or {}).items()},
        f"{root}/PKG-INFO": (
            f"Metadata-Version: 2.1\nName: {NAME}\nVersion: {VERSION}\n"
        ).encode(),
        f"{root}/pyproject.toml": (
            f'[project]\nname = "{NAME}"\nversion = "{VERSION}"\n{pyproject_tail}'
        ).encode(),
        f"{root}/src/{NAME}/__init__.py": b'"""Demo."""\n',
    }
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for member, data in members.items():
            info = tarfile.TarInfo(member)
            info.size, info.mtime, info.mode = len(data), 0, 0o644
            archive.addfile(info, io.BytesIO(data))
    packed = io.BytesIO()
    with gzip.GzipFile(fileobj=packed, mode="wb", mtime=0) as gz:
        gz.write(raw.getvalue())
    return packed.getvalue()


def publish_demo(
    fake: FakePypi,
    releases: Mapping[str, Sequence[Dist]] | None = None,
) -> None:
    """Publish ``demo`` on *fake*: by default ``1.0.0`` with one wheel and
    one sdist."""
    publish(
        fake,
        NAME,
        releases
        or {
            VERSION: [
                Dist(WHEEL_NAME, wheel_bytes()),
                Dist(SDIST_NAME, sdist_bytes()),
            ]
        },
    )


def fake_pypi(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[tuple[FakePypi, Path]]:
    """A fake PyPI the resolver asks, the tag order patched, and the system
    temporary directory (a fresh one under *tmp_path*)."""
    temp = tmp_path / "temp"
    temp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    monkeypatch.setattr(pypi_select, "_environment_tags", lambda: list(TAGS))
    with serving() as fake:
        point_at(monkeypatch, fake)
        yield fake, temp


def graph(sbom: str) -> list[dict[str, Any]]:
    """The ``@graph`` of *sbom*."""
    elements: list[dict[str, Any]] = json.loads(sbom)["@graph"]
    return elements


def record_fields(sbom: str) -> list[dict[str, dict[str, str]]]:
    """The ``fields`` of each acquisition record Annotation in *sbom*."""
    found = []
    for element in graph(sbom):
        if element.get("type") != "Annotation":
            continue
        statement = json.loads(element.get("statement", "null"))
        fields = statement.get("fields") if isinstance(statement, dict) else None
        if isinstance(fields, dict) and RECORD_FIELD in fields:
            found.append(fields)
    return found


def the_record(sbom: str) -> dict[str, dict[str, str]]:
    """The ``fields`` of the one acquisition record in *sbom*."""
    records = record_fields(sbom)
    assert len(records) == 1, records
    return records[0]


def without_record(sbom: str) -> tuple[list[dict[str, Any]], int]:
    """The graph of *sbom* without the acquisition record (its Annotation
    and its comment line), and how many parts were removed."""
    kept: list[dict[str, Any]] = []
    removed = 0
    for element in graph(sbom):
        statement = element.get("statement", "")
        if element.get("type") == "Annotation" and RECORD_FIELD in statement:
            removed += 1
            continue
        comment = element.get("comment")
        if isinstance(comment, str) and f"{RECORD_FIELD}: " in comment:
            lines = comment.split("\n")
            element = dict(element)
            rest = "\n".join(line for line in lines if f"{RECORD_FIELD}: " not in line)
            if rest:
                element["comment"] = rest
            else:
                del element["comment"]
            removed += 1
        kept.append(element)
    return kept, removed


__all__ = [
    "CP_WHEEL_NAME",
    "CREATION",
    "NAME",
    "PAGE",
    "RECORD_FIELD",
    "SDIST_NAME",
    "TAGS",
    "URL",
    "VERSION",
    "WHEEL_NAME",
    "fake_pypi",
    "graph",
    "publish_demo",
    "record_fields",
    "sdist_bytes",
    "the_record",
    "wheel_bytes",
    "without_record",
]
