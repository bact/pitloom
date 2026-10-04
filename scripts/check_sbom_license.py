# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Check that an SPDX 3 SBOM's root package declares and concludes a licence.

The release workflow (``pypi-publish.yml``) runs this on Pitloom's own
release SBOM, both the copy embedded in the wheel and the standalone one,
so a release never ships an SBOM that lost either licence. Its ``build``
job has no licenseid database: if ``codemeta.json`` lost its licence, the
concluded licence would fall back to licence-text detection and silently
disappear.

Each PATH is an SBOM JSON file or a wheel (``.whl``), whose one embedded
SBOM is found as ``loom verify-wheel`` finds it
(:func:`pitloom.embed.find_embedded_sbom`). The root package is the
single ``software_Package`` in the single ``software_Sbom``'s
``rootElement``. It must have exactly one ``hasDeclaredLicense`` and one
``hasConcludedLicense`` relationship, each to exactly one licence whose
text equals ``--license``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pitloom.core.license_individuals import INDIVIDUAL_BY_REFERENCE
from pitloom.core.wheel_dist_info import looks_like_wheel_path
from pitloom.embed import find_embedded_sbom

_LICENSE_TEXT_KEYS = (
    "simplelicensing_licenseExpression",
    "simplelicensing_licenseText",
)
_RELATIONSHIP_TYPES = ("hasDeclaredLicense", "hasConcludedLicense")


class SbomLicenseError(ValueError):
    """The SBOM is unreadable or its root package's licence is wrong."""


def load_sbom(path: Path) -> Any:
    """Parse *path*, or the one SBOM embedded in it when it is a wheel."""
    try:
        if not looks_like_wheel_path(path):
            return json.loads(path.read_bytes())
        found = find_embedded_sbom(path)
        if found is None:
            raise SbomLicenseError("no SBOM under .dist-info/sboms/")
        return json.loads(found.data)
    except (OSError, ValueError) as exc:
        if isinstance(exc, SbomLicenseError):
            raise
        raise SbomLicenseError(f"cannot read SBOM: {exc}") from exc


def _root_package(graph: list[Any]) -> str:
    sboms = [
        e for e in graph if isinstance(e, dict) and e.get("type") == "software_Sbom"
    ]
    if len(sboms) != 1:
        raise SbomLicenseError(f"expected one software_Sbom, found {len(sboms)}")
    roots = sboms[0].get("rootElement")
    if not isinstance(roots, list) or len(roots) != 1:
        raise SbomLicenseError(f"expected one software_Sbom root element: {roots}")
    root = roots[0]
    if not any(
        isinstance(e, dict)
        and e.get("spdxId") == root
        and e.get("type") == "software_Package"
        for e in graph
    ):
        raise SbomLicenseError(f"root element is not a software_Package: {root}")
    return str(root)


def _license_texts(graph: list[Any], root: str, relationship_type: str) -> list[str]:
    by_id = {
        e["spdxId"]: e
        for e in graph
        if isinstance(e, dict) and isinstance(e.get("spdxId"), str)
    }
    targets: list[Any] = []
    for rel in graph:
        if not (
            isinstance(rel, dict)
            and rel.get("type") == "Relationship"
            and rel.get("from") == root
            and str(rel.get("relationshipType", "")).rsplit("/", 1)[-1]
            == relationship_type
        ):
            continue
        if not isinstance(rel.get("to"), list):
            raise SbomLicenseError(f"{relationship_type} has no 'to' list")
        targets.extend(rel["to"])
    texts: list[str] = []
    for target in targets:
        if isinstance(target, str) and target in INDIVIDUAL_BY_REFERENCE:
            texts.append(INDIVIDUAL_BY_REFERENCE[target].spdx_name)
            continue
        element = by_id.get(target, {}) if isinstance(target, str) else {}
        text = next((element[k] for k in _LICENSE_TEXT_KEYS if k in element), None)
        if not isinstance(text, str):
            raise SbomLicenseError(
                f"{relationship_type} target has no licence text: {target}"
            )
        texts.append(text)
    return texts


def check_sbom_license(sbom: Any, expected: str) -> None:
    """Raise :class:`SbomLicenseError` unless the root package declares and
    concludes exactly *expected*."""
    graph = sbom.get("@graph") if isinstance(sbom, dict) else None
    if not isinstance(graph, list):
        raise SbomLicenseError("SBOM has no @graph list")
    root = _root_package(graph)
    for relationship_type in _RELATIONSHIP_TYPES:
        texts = _license_texts(graph, root, relationship_type)
        if texts != [expected]:
            raise SbomLicenseError(
                f"root package {relationship_type} is {texts}, expected [{expected!r}]"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check an SBOM's root package declares and concludes a licence."
    )
    parser.add_argument("--license", required=True, help="expected licence, exact")
    parser.add_argument("paths", nargs="+", type=Path, help="SBOM JSON or wheel")
    args = parser.parse_args(argv)

    failed = False
    for path in args.paths:
        try:
            check_sbom_license(load_sbom(path), args.license)
        except SbomLicenseError as exc:
            print(f"ERROR: FILE={path}: {exc}", file=sys.stderr)
            failed = True
        else:
            print(f"FILE={path} LICENSE={args.license}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
