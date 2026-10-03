# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Check and extract the SBOM the build hook embedded in a built wheel.

The release workflow (``pypi-publish.yml``) and ``build.yml`` run this on
the wheel Hatchling built, so the SBOM released is the one the build hook
wrote: no second generation. DIST_DIR must hold exactly one wheel. Its
embedded SBOM is found as ``loom verify-wheel`` finds it
(:func:`pitloom.embed.find_embedded_sbom`), must be named ``*.spdx3.json``,
and must match its ``RECORD`` hash. The bytes are copied unchanged to
OUT_DIR.

``--require-magika`` also fails unless every file's content type in the
SBOM was detected by magika (``Method: magika_content_detection``): a
build without Pitloom's ``content-type`` extra silently falls back to file
extensions. A file with no content type (a directory) is ignored, and so is
an empty file, which magika cannot classify.

Prints ``WHEEL=... SBOM=... SHA256=...``. ``--github-output`` appends
``wheel-path``, ``sbom-name``, ``sbom-path`` and ``sbom-sha256`` to that
file, LF-terminated. Errors print ``ERROR: ...`` and exit 1. Never uses
the network.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import posixpath
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

from pitloom.embed import find_embedded_sbom
from pitloom.export.spdx3_json import SPDX3_JSONLD_EXTENSION

_MAGIKA_METHOD = "magika_content_detection"
# Magika cannot classify empty content, so Pitloom falls back to the file
# extension there (an empty ``__init__.py``): such a file is not a failure.
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
# A content type recorded in a ``comment`` instead of an Annotation.
_SAFE_NAME = re.compile(r"[A-Za-z0-9._+-]+")
_COMMENT_RE = re.compile(r"content_type: [^;\n]*? \| (Method|Role): (\w+)")


class ExtractError(ValueError):
    """The wheel or its SBOM fails a check."""


def _has_control(text: str) -> bool:
    """Whether *text* holds a control character (it could end an output line)."""
    return any(ord(c) < 32 or c == "\x7f" for c in text)


def _unsafe(name: str) -> bool:
    """Whether *name* strays outside a plain file name: it ends up in
    ``$GITHUB_OUTPUT``, sigstore inputs and attest subjects, where a glob,
    space or ``:`` would mean something else."""
    return _SAFE_NAME.fullmatch(name) is None


def _find_wheel(dist_dir: Path) -> Path:
    wheels = sorted(dist_dir.glob("*.whl")) if dist_dir.is_dir() else []
    if len(wheels) != 1:
        raise ExtractError(f"expected one wheel in {dist_dir}, found {len(wheels)}")
    if _has_control(str(wheels[0])):
        raise ExtractError(f"unsafe wheel path: {wheels[0]!r}")
    return wheels[0]


def _record_hash(wheel: Path, dist_info: str, arcname: str) -> str | None:
    """The ``RECORD`` hash entry for *arcname*, or ``None`` if there is none."""
    try:
        with zipfile.ZipFile(wheel) as zf, zf.open(f"{dist_info}/RECORD") as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
            for row in csv.reader(text):
                if row and row[0] == arcname:
                    return row[1] if len(row) > 1 else ""
    except (KeyError, OSError, UnicodeDecodeError, csv.Error, zipfile.BadZipFile):
        raise ExtractError("cannot read RECORD") from None
    return None


def _check_record(wheel: Path, arcname: str, data: bytes) -> None:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest())
    expected = "sha256=" + digest.decode("ascii").rstrip("=")
    actual = _record_hash(wheel, posixpath.dirname(posixpath.dirname(arcname)), arcname)
    if actual != expected:
        raise ExtractError(f"RECORD hash of {arcname} is {actual!r}, not {expected}")


def _add_method(methods: dict[str, set[str]], subject: object, how: str) -> None:
    methods.setdefault(str(subject), set()).add(how)


def _content_type_methods(graph: list[Any]) -> dict[str, set[str]]:
    """Every content-type method recorded per ``software_File`` spdxId, from
    its comment and its Annotations alike: graph order must not matter."""
    methods: dict[str, set[str]] = {}
    for element in graph:
        if not isinstance(element, dict):
            continue
        if element.get("type") == "software_File":
            match = _COMMENT_RE.search(str(element.get("comment", "")))
            if match:
                kind, value = match.groups()
                how = value if kind == "Method" else f"role {value}"
                _add_method(methods, element.get("spdxId"), how)
        elif element.get("type") == "Annotation":
            try:
                recorded = json.loads(element.get("statement", ""))["fields"][
                    "content_type"
                ]
                how = (
                    str(recorded["method"])
                    if "method" in recorded
                    else (f"role {recorded.get('role', 'unknown')}")
                )
            except (TypeError, ValueError, KeyError, AttributeError):
                continue
            _add_method(methods, element.get("subject"), how)
    return methods


def _is_empty(element: dict[str, Any]) -> bool:
    hashes = element.get("verifiedUsing")
    return isinstance(hashes, list) and any(
        isinstance(h, dict)
        and h.get("algorithm") == "sha256"
        and h.get("hashValue") == _EMPTY_SHA256
        for h in hashes
    )


def _check_magika(graph: list[Any]) -> None:
    methods = _content_type_methods(graph)
    typed = [
        e
        for e in graph
        if isinstance(e, dict)
        and e.get("type") == "software_File"
        and "contentType" in e
    ]
    if not typed:
        raise ExtractError("SBOM records no file content types: magika did not run")
    for element in typed:
        found = methods.get(str(element.get("spdxId")), set())
        if found == {_MAGIKA_METHOD}:
            continue
        # Magika cannot classify empty content: the extension is expected.
        if found == {"extension_guess"} and _is_empty(element):
            continue
        how = ", ".join(sorted(found)) or "no record"
        raise ExtractError(
            f"content type of {element.get('name')} came from {how}, not magika"
        )


def _parse_graph(data: bytes) -> list[Any]:
    try:
        sbom = json.loads(data)
    except ValueError as exc:
        raise ExtractError(f"SBOM is not JSON: {exc}") from exc
    graph = sbom.get("@graph") if isinstance(sbom, dict) else None
    if not isinstance(graph, list):
        raise ExtractError("SBOM has no @graph list")
    return graph


def extract(
    dist_dir: Path, out_dir: Path, *, require_magika: bool
) -> tuple[Path, Path, str]:
    """Check the wheel's SBOM and write it to *out_dir*.

    Returns the wheel, the written SBOM and its SHA-256.
    """
    wheel = _find_wheel(dist_dir)
    try:
        found = find_embedded_sbom(wheel)
    except (OSError, ValueError) as exc:
        raise ExtractError(f"cannot read {wheel}: {exc}") from exc
    if found is None:
        raise ExtractError(f"no SBOM under .dist-info/sboms/ in {wheel}")
    name = posixpath.basename(found.arcname)
    if _unsafe(name) or not name.endswith(SPDX3_JSONLD_EXTENSION):
        raise ExtractError(
            f"SBOM name is not a safe *{SPDX3_JSONLD_EXTENSION}: {name!r}"
        )
    _check_record(wheel, found.arcname, found.data)
    graph = _parse_graph(found.data)
    if require_magika:
        _check_magika(graph)

    digest = hashlib.sha256(found.data).hexdigest()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / name
    if _has_control(str(target)):
        raise ExtractError(f"unsafe output path: {target!r}")
    target.write_bytes(found.data)
    if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
        raise ExtractError(f"{target} differs from the wheel's SBOM after writing")
    return wheel, target, digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check and extract the SBOM embedded in a built wheel."
    )
    parser.add_argument("dist_dir", type=Path, help="directory with one wheel")
    parser.add_argument("out_dir", type=Path, help="where to write the SBOM")
    parser.add_argument("--github-output", type=Path, help="GITHUB_OUTPUT file")
    parser.add_argument(
        "--require-magika",
        action="store_true",
        help="fail unless every content type was detected by magika",
    )
    args = parser.parse_args(argv)

    try:
        wheel, sbom, digest = extract(
            args.dist_dir, args.out_dir, require_magika=args.require_magika
        )
        print(f"WHEEL={wheel} SBOM={sbom} SHA256={digest}")
        if args.github_output:
            lines = (
                f"wheel-path={wheel}",
                f"sbom-name={sbom.name}",
                f"sbom-path={sbom}",
                f"sbom-sha256={digest}",
            )
            with args.github_output.open("ab") as out:
                out.write(("\n".join(lines) + "\n").encode("utf-8"))
    except (ExtractError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
