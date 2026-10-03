# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``scripts/extract_wheel_sbom.py``, which the release workflow
runs to copy the build hook's SBOM out of the built wheel.

See also: tests/scripts/test_check_sbom_license.py.
"""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_SBOM_NAME = "pkg-1.0.spdx3.json"
_SBOM_ARC = f"pkg-1.0.dist-info/sboms/{_SBOM_NAME}"
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
_MAGIKA = {"method": "magika_content_detection", "tool": "magika==1.0.3"}
#: Valid JSON that re-serialising or newline translation would change.
_PAYLOAD = b'{"z": "\\u00e9 \xc3\xa9",\r\n  "@graph": [   ],\r\n\t"a": 1.50}\r\n\r\n'


@pytest.fixture(name="module")
def module_fixture(load_script: Callable[[str], ModuleType]) -> ModuleType:
    return load_script("extract_wheel_sbom")


def _record_entry(arcname: str, data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest())
    return f"{arcname},sha256={digest.decode().rstrip('=')},{len(data)}"


def _wheel(
    dist: Path,
    sboms: dict[str, bytes] | None = None,
    *,
    record: Callable[[str, bytes], str | None] = _record_entry,
    has_record: bool = True,
    name: str = "pkg-1.0-py3-none-any.whl",
) -> Path:
    """A wheel shaped like Hatchling's: payload, ``.dist-info``, ``RECORD``."""
    members = {
        "pkg/__init__.py": b"",
        "pkg-1.0.dist-info/METADATA": b"Metadata-Version: 2.4\nName: pkg\n"
        b"Version: 1.0\n",
        "pkg-1.0.dist-info/WHEEL": b"Wheel-Version: 1.0\nTag: py3-none-any\n",
    }
    members.update(
        {f"pkg-1.0.dist-info/sboms/{k}": v for k, v in (sboms or {}).items()}
    )
    lines = [record(arc, data) for arc, data in members.items()]
    if has_record:
        text = "\n".join(line for line in lines if line is not None)
        members["pkg-1.0.dist-info/RECORD"] = (text + "\n").encode()
    dist.mkdir(exist_ok=True)
    path = dist / name
    with zipfile.ZipFile(path, "w") as wheel:
        for arc, data in members.items():
            wheel.writestr(arc, data)
    return path


def _file(
    name: str, *, content_type: bool = True, empty: bool = False
) -> dict[str, Any]:
    element: dict[str, Any] = {
        "type": "software_File",
        "spdxId": f"urn:x#{name}",
        "name": name,
    }
    if content_type:
        element["contentType"] = "text/x-python"
    if empty:
        element["verifiedUsing"] = [
            {"type": "Hash", "algorithm": "sha256", "hashValue": _EMPTY_SHA256}
        ]
    return element


def _annotation(name: str, method: dict[str, str] | None) -> dict[str, Any]:
    fields = {"copyright_text": {"source": "x"}}
    if method is not None:
        fields["content_type"] = method
    return {
        "type": "Annotation",
        "subject": f"urn:x#{name}",
        "statement": json.dumps({"fields": fields, "kind": "fields"}),
    }


def _sbom(*elements: dict[str, Any]) -> bytes:
    return json.dumps({"@graph": list(elements)}).encode()


def _magika_sbom() -> bytes:
    return _sbom(
        _file("dir", content_type=False),
        _file("a.py"),
        _annotation("a.py", _MAGIKA),
        _file("b.py"),
        _annotation("b.py", _MAGIKA),
    )


def test_extracts_exact_bytes(module: ModuleType, tmp_path: Path) -> None:
    _wheel(tmp_path / "dist", {_SBOM_NAME: _PAYLOAD})
    wheel, sbom, digest = module.extract(
        tmp_path / "dist", tmp_path / "out", require_magika=False
    )
    assert wheel.name == "pkg-1.0-py3-none-any.whl"
    assert sbom == tmp_path / "out" / _SBOM_NAME
    assert sbom.read_bytes() == _PAYLOAD
    assert digest == hashlib.sha256(_PAYLOAD).hexdigest()
    # The payload is not what a JSON round trip or newline translation gives.
    assert json.dumps(json.loads(_PAYLOAD)).encode() != _PAYLOAD
    assert _PAYLOAD.replace(b"\r\n", b"\n") != _PAYLOAD


@pytest.mark.parametrize("count", [0, 2])
def test_needs_exactly_one_wheel(
    module: ModuleType, tmp_path: Path, count: int
) -> None:
    for i in range(count):
        _wheel(
            tmp_path / "dist", {_SBOM_NAME: b"{}"}, name=f"pkg{i}-1.0-py3-none-any.whl"
        )
    (tmp_path / "dist").mkdir(exist_ok=True)
    with pytest.raises(module.ExtractError, match="one wheel"):
        module.extract(tmp_path / "dist", tmp_path / "out", require_magika=False)


def test_missing_dist_dir(module: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(module.ExtractError, match="one wheel"):
        module.extract(tmp_path / "none", tmp_path / "out", require_magika=False)


@pytest.mark.parametrize(
    ("sboms", "pattern"),
    [
        ({}, "no SBOM"),
        ({"a.spdx3.json": b"{}", "b.spdx3.json": b"{}"}, "Multiple SBOMs"),
        ({"sub/a.spdx3.json": b"{}"}, "no SBOM"),
        ({"pkg-1.0.json": b"{}"}, "safe"),
        ({"a\nb.spdx3.json": b"{}"}, "safe"),
        ({"a b.spdx3.json": b"{}"}, "safe"),
        ({"a*.spdx3.json": b"{}"}, "safe"),
        ({"a:b.spdx3.json": b"{}"}, "safe"),
        ({"a%b.spdx3.json": b"{}"}, "safe"),
        ({_SBOM_NAME: b"not json"}, "not JSON"),
        ({_SBOM_NAME: b'{"@graph": {}}'}, "@graph"),
    ],
)
def test_bad_sbom_member(
    module: ModuleType, tmp_path: Path, sboms: dict[str, bytes], pattern: str
) -> None:
    _wheel(tmp_path / "dist", sboms)
    with pytest.raises(module.ExtractError, match=pattern):
        module.extract(tmp_path / "dist", tmp_path / "out", require_magika=False)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    ("record", "has_record"),
    [
        (lambda arc, data: None if "sboms/" in arc else _record_entry(arc, data), True),
        (
            lambda arc, data: (
                _record_entry(arc, data + b" ")
                if "sboms/" in arc
                else _record_entry(arc, data)
            ),
            True,
        ),
        (lambda arc, data: f"{arc},,", True),
        (_record_entry, False),
    ],
    ids=["no-entry", "wrong-hash", "empty-hash", "no-record"],
)
def test_record_must_match(
    module: ModuleType,
    tmp_path: Path,
    record: Callable[[str, bytes], str | None],
    has_record: bool,
) -> None:
    _wheel(
        tmp_path / "dist", {_SBOM_NAME: _PAYLOAD}, record=record, has_record=has_record
    )
    with pytest.raises(module.ExtractError, match="RECORD"):
        module.extract(tmp_path / "dist", tmp_path / "out", require_magika=False)
    assert not (tmp_path / "out").exists()


def test_magika_sbom_passes(module: ModuleType, tmp_path: Path) -> None:
    _wheel(tmp_path / "dist", {_SBOM_NAME: _magika_sbom()})
    module.extract(tmp_path / "dist", tmp_path / "out", require_magika=True)


def test_magika_recorded_in_comment_passes(module: ModuleType, tmp_path: Path) -> None:
    element = _file("a.py")
    element["comment"] = (
        "Metadata provenance: content_type: Source: a.py | "
        "Method: magika_content_detection | Tool: magika==1.0.3"
    )
    _wheel(tmp_path / "dist", {_SBOM_NAME: _sbom(element)})
    module.extract(tmp_path / "dist", tmp_path / "out", require_magika=True)


def test_empty_file_may_use_extension(module: ModuleType, tmp_path: Path) -> None:
    """Magika cannot classify empty content, so the extension is used there."""
    sbom = _sbom(
        _file("a.py"),
        _annotation("a.py", _MAGIKA),
        _file("__init__.py", empty=True),
        _annotation("__init__.py", {"method": "extension_guess"}),
    )
    _wheel(tmp_path / "dist", {_SBOM_NAME: sbom})
    module.extract(tmp_path / "dist", tmp_path / "out", require_magika=True)


@pytest.mark.parametrize(
    "bad",
    [
        {"method": "extension_guess"},
        {"role": "sbomAuthorSupplied"},
        None,
    ],
    ids=["extension", "override", "no-record"],
)
def test_non_magika_file_fails(
    module: ModuleType, tmp_path: Path, bad: dict[str, str] | None
) -> None:
    sbom = _sbom(
        _file("a.py"),
        _annotation("a.py", _MAGIKA),
        _file("b.py"),
        _annotation("b.py", bad),
    )
    _wheel(tmp_path / "dist", {_SBOM_NAME: sbom})
    with pytest.raises(module.ExtractError, match=r"content type of b\.py"):
        module.extract(tmp_path / "dist", tmp_path / "out", require_magika=True)
    # Without the flag the same SBOM is extracted.
    module.extract(tmp_path / "dist", tmp_path / "out", require_magika=False)


@pytest.mark.parametrize(
    ("recorded", "pattern"),
    [
        (None, "no record"),
        ({"role": "sbomAuthorSupplied"}, "role sbomAuthorSupplied"),
    ],
    ids=["no-record", "override"],
)
def test_empty_file_exemption_is_only_for_extension(
    module: ModuleType,
    tmp_path: Path,
    recorded: dict[str, str] | None,
    pattern: str,
) -> None:
    sbom = _sbom(
        _file("a.py"),
        _annotation("a.py", _MAGIKA),
        _file("__init__.py", empty=True),
        _annotation("__init__.py", recorded),
    )
    _wheel(tmp_path / "dist", {_SBOM_NAME: sbom})
    with pytest.raises(module.ExtractError, match=pattern):
        module.extract(tmp_path / "dist", tmp_path / "out", require_magika=True)


@pytest.mark.parametrize("empty", [False, True], ids=["file", "empty-file"])
@pytest.mark.parametrize("comment_first", [True, False])
def test_every_recorded_method_must_be_magika(
    module: ModuleType, tmp_path: Path, comment_first: bool, empty: bool
) -> None:
    """A comment and an Annotation that disagree fail in either graph order,
    an empty file included (its exemption needs extension_guess alone)."""
    element = _file("a.py", empty=empty)
    element["comment"] = (
        "Metadata provenance: content_type: Source: a.py | Method: extension_guess"
    )
    parts = [element, _annotation("a.py", _MAGIKA)]
    if not comment_first:
        parts = [_annotation("a.py", _MAGIKA), element]
    _wheel(tmp_path / "dist", {_SBOM_NAME: _sbom(*parts)})
    with pytest.raises(module.ExtractError, match="extension_guess, magika"):
        module.extract(tmp_path / "dist", tmp_path / "out", require_magika=True)


def test_no_content_types_fails(module: ModuleType, tmp_path: Path) -> None:
    sbom = _sbom(_file("dir", content_type=False))
    _wheel(tmp_path / "dist", {_SBOM_NAME: sbom})
    with pytest.raises(module.ExtractError, match="no file content types"):
        module.extract(tmp_path / "dist", tmp_path / "out", require_magika=True)


def _run(scripts_dir: Path, *args: str | Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(scripts_dir / "extract_wheel_sbom.py"), *map(str, args)],
        capture_output=True,
        check=False,
    )


def test_cli_success_and_github_output(scripts_dir: Path, tmp_path: Path) -> None:
    wheel = _wheel(tmp_path / "dist", {_SBOM_NAME: _PAYLOAD})
    github_output = tmp_path / "output.txt"
    github_output.write_bytes(b"earlier=1\n")
    digest = hashlib.sha256(_PAYLOAD).hexdigest()
    sbom = tmp_path / "out" / _SBOM_NAME

    result = _run(
        scripts_dir,
        tmp_path / "dist",
        tmp_path / "out",
        "--github-output",
        github_output,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.decode().splitlines() == [
        f"WHEEL={wheel} SBOM={sbom} SHA256={digest}"
    ]
    assert result.stderr == b""
    assert (
        github_output.read_bytes()
        == (
            f"earlier=1\nwheel-path={wheel}\nsbom-name={_SBOM_NAME}\n"
            f"sbom-path={sbom}\nsbom-sha256={digest}\n"
        ).encode()
    )
    assert sbom.read_bytes() == _PAYLOAD


def test_cli_failure_and_usage(scripts_dir: Path, tmp_path: Path) -> None:
    _wheel(tmp_path / "dist", {_SBOM_NAME: b"{}"})
    github_output = tmp_path / "output.txt"
    failed = _run(
        scripts_dir,
        tmp_path / "dist",
        tmp_path / "out",
        "--require-magika",
        "--github-output",
        github_output,
    )
    assert failed.returncode == 1
    assert failed.stdout == b""
    assert failed.stderr.decode().startswith("ERROR: ")
    assert not github_output.exists()
    assert _run(scripts_dir, tmp_path / "dist").returncode == 2


def test_cli_reports_os_errors(scripts_dir: Path, tmp_path: Path) -> None:
    _wheel(tmp_path / "dist", {_SBOM_NAME: _PAYLOAD})
    (tmp_path / "file").write_bytes(b"")
    blocked_out = _run(scripts_dir, tmp_path / "dist", tmp_path / "file" / "out")
    bad_output = _run(
        scripts_dir,
        tmp_path / "dist",
        tmp_path / "out",
        "--github-output",
        tmp_path / "missing" / "output.txt",
    )
    for result in (blocked_out, bad_output):
        assert result.returncode == 1
        assert result.stderr.decode().startswith("ERROR: ")
        assert b"Traceback" not in result.stderr


def test_extracted_sbom_matches_license_checker_read(
    module: ModuleType,
    load_script: Callable[[str], ModuleType],
    tmp_path: Path,
) -> None:
    """Drift guard: the licence check reads the wheel's SBOM the same way."""
    wheel = _wheel(tmp_path / "dist", {_SBOM_NAME: _magika_sbom()})
    _, sbom, _ = module.extract(
        tmp_path / "dist", tmp_path / "out", require_magika=True
    )
    checker = load_script("check_sbom_license")
    assert checker.load_sbom(wheel) == json.loads(sbom.read_bytes())
