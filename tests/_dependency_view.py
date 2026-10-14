# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The root package and dependencies of an SBOM, as the route-parity
tests compare them.

See also: tests/test_dependency_spelling_surfaces.py and
tests/test_requirements_file_surfaces.py (the users).
"""

from __future__ import annotations

import json
from typing import Any


def _graph(sbom: str) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    """The nodes of *sbom*, the same keyed by ``spdxId``, and the root's id."""
    graph = json.loads(sbom)["@graph"]
    by_id = {node["spdxId"]: node for node in graph if "spdxId" in node}
    (root,) = next(n for n in graph if n["type"] == "software_Sbom")["rootElement"]
    return graph, by_id, root


def root_package(sbom: str) -> tuple[str, str | None]:
    """The root package's name and PURL."""
    _, by_id, root = _graph(sbom)
    return by_id[root]["name"], by_id[root].get("software_packageUrl")


def dependency_view(sbom: str) -> list[tuple[Any, ...]]:
    """Each dependency of the root package, sorted: the package's name,
    PURL and declared constraint, the edge's type, scope and comment.
    What a route reads from (a file name, ``PKG-INFO``) is left out."""
    graph, by_id, root = _graph(sbom)
    declared = {
        node["subject"]: json.loads(node["statement"])["fields"]
        .get("declared_constraint", {})
        .get("note")
        for node in graph
        if node["type"] == "Annotation" and '"fields"' in node.get("statement", "")
    }
    rows = []
    for edge in graph:
        if edge.get("from") != root or edge.get("relationshipType") not in (
            "dependsOn",
            "hasOptionalDependency",
        ):
            continue
        for target in edge["to"]:
            package = by_id[target]
            rows.append(
                (
                    package["name"],
                    package.get("software_packageUrl"),
                    declared.get(target),
                    edge["relationshipType"],
                    edge.get("scope"),
                    edge.get("comment"),
                )
            )
    return sorted(rows, key=repr)
