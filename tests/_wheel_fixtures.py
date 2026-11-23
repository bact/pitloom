# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tiny wheels built by hand for the wheel surface tests: members written
under their exact raw names with a fixed date and mode (no clock), so a
test controls each member a command reads.

See also: tests/messages/test_wheels_surfaces.py,
tests/messages/test_wheels_hostile.py and
tests/cli/test_cli_wheels_regressions.py (the users).
"""

from __future__ import annotations

import json
import sys
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from pitloom import __main__
from pitloom.messages import trusted_message

WHEEL_FILE = "demo-1.0-py3-none-any.whl"
DIST_INFO = "demo-1.0.dist-info"
_DATE = (2020, 1, 1, 0, 0, 0)
_NS = "https://spdx.org/spdxdocs/demo-1.0"


def metadata(name: str = "demo", version: str = "1.0") -> bytes:
    """A ``METADATA`` file (bytes, so a CRLF host cannot change them)."""
    return f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n".encode()


def spdx3_sbom(
    name: str | None = "demo",
    version: str | None = "1.0",
    *,
    pitloom_types: list[str] | None = None,
) -> bytes:
    """A minimal SPDX 3 JSON-LD document whose subject is *name* *version*
    (an SBOM that is not valid SPDX 3, but is one Pitloom can read); with
    *pitloom_types*, one a Pitloom agent made, of those ``sbomType`` values."""
    subject: dict[str, Any] = {"type": "software_Package", "spdxId": f"{_NS}/p"}
    if name is not None:
        subject["name"] = name
    if version is not None:
        subject["software_packageVersion"] = version
    sbom: dict[str, Any] = {
        "type": "software_Sbom",
        "spdxId": f"{_NS}/sbom",
        "rootElement": [subject["spdxId"]],
    }
    graph: list[dict[str, Any]] = [
        {
            "type": "SpdxDocument",
            "spdxId": _NS,
            "rootElement": [f"{_NS}/sbom"],
        },
        sbom,
        subject,
    ]
    if pitloom_types is not None:
        sbom["software_sbomType"] = pitloom_types
        graph.append({"type": "SoftwareAgent", "spdxId": "urn:a", "name": "Pitloom"})
    context = "https://spdx.org/rdf/3.0.1/spdx-context.jsonld"
    return json.dumps({"@context": context, "@graph": graph}).encode()


def write_wheel(
    path: Path,
    members: Mapping[str, bytes],
    *,
    mode: int = 0o644,
) -> Path:
    """A ZIP at *path* holding *members* under their raw names (``\\`` kept,
    no ``os.sep`` rewrite), each dated 2020-01-01 with *mode*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        for raw, data in members.items():
            info = zipfile.ZipInfo("placeholder", date_time=_DATE)
            info.filename = raw  # raw: ZipInfo(name) would rewrite os.sep
            info.external_attr = mode << 16
            zf.writestr(info, data)
    return path


def make_wheel(
    directory: Path,
    *,
    name: str = "demo",
    version: str = "1.0",
    sboms: Mapping[str, bytes] | None = None,
    extra: Mapping[str, bytes] | None = None,
) -> Path:
    """A conforming wheel ``<name>-<version>-py3-none-any.whl`` in
    *directory*, its ``.dist-info`` holding METADATA, WHEEL and RECORD, each
    of *sboms* under ``sboms/`` and the *extra* members as given."""
    dist_info = f"{name}-{version}.dist-info"
    members: dict[str, bytes] = {
        f"{name}/__init__.py": b"",
        f"{dist_info}/METADATA": metadata(name, version),
        f"{dist_info}/WHEEL": b"Wheel-Version: 1.0\nTag: py3-none-any\n",
        f"{dist_info}/RECORD": b"",
    }
    members.update({f"{dist_info}/sboms/{n}": d for n, d in (sboms or {}).items()})
    members.update(extra or {})
    return write_wheel(directory / f"{name}-{version}-py3-none-any.whl", members)


def patch_member_name(path: Path, old: str, new: bytes) -> None:
    """Replace the name *old* (ASCII) by the same-length bytes *new* in the
    file *path*, in the local and the central header alike."""
    raw = old.encode("ascii")
    assert len(raw) == len(new)
    data = path.read_bytes()
    assert raw in data  # the damage is real
    path.write_bytes(data.replace(raw, new))


class Run(NamedTuple):
    """What one in-process ``loom`` run left: its exit status and its lines."""

    status: int
    out: list[str]
    err: list[str]

    @property
    def codes(self) -> list[str]:
        """The code of each stderr line Pitloom trusts, in order."""
        found = (trusted_message(line) for line in self.err)
        return [m.code for m in found if m is not None]


def run_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *argv: object,
) -> Run:
    """``loom *argv`` through ``__main__.main()``, as the entry point runs it."""
    monkeypatch.setattr(sys, "argv", ["loom", *map(str, argv)])
    status = __main__.main()
    captured = capsys.readouterr()
    return Run(status, captured.out.splitlines(), captured.err.splitlines())
