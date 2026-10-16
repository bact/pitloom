# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What one order-matrix script left behind, read back step by step: exit
status, stdout, stderr, the registry as the step left it, and the SBOMs it
wrote, reduced to the black-box facts the invariants compare.

See also: ``_order_invariants.py`` (the checks over these),
``_order_gen.py`` (the script that writes them).
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _order_ops import Step

FILE, PACKAGE = "software_File", "software_Package"
AI, DATASET = "ai_AIPackage", "dataset_DatasetPackage"
#: The four types a lookup reads (design section 7), with their id
#: prefixes (D2, I6); every other harvested type is a per-document record.
PREFIX = {FILE: "File", PACKAGE: "Package", AI: "AIPackage", DATASET: "DatasetPackage"}
#: The content-gated types (I1, I2; a dataset package by its digest).
GATED = frozenset({FILE, AI, DATASET})
LOOM_SURFACES = frozenset({"train", "eval"})

Key = tuple[str, str]


@dataclass(frozen=True)
class Entry:
    """One registry entry (design section 6)."""

    spdx_id: str
    sha: str | None


@dataclass(frozen=True)
class Element:
    """An SBOM element with a name, as a lookup would key it."""

    key: Key
    spdx_id: str
    sha: str | None
    name: str


def canonical(type_name: str, name: str) -> Key:
    """The registry key of an element (``_element_key``: PEP 503 for a
    ``software_Package`` name, NFC for every other)."""
    if type_name == PACKAGE:
        return type_name, re.sub(r"[-_.]+", "-", name).lower()
    return type_name, unicodedata.normalize("NFC", name)


def parse_registry(raw: bytes) -> dict[Key, Entry] | None:
    """A v3 registry file's entries; None for anything else (an injected
    failure, a partly written file)."""
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("version") != 3:
        return None
    table: dict[Key, Entry] = {}
    for type_name, names in data.get("elements", {}).items():
        for name, entry in names.items():
            table[(type_name, name)] = Entry(entry["spdxId"], entry.get("sha256"))
    return table


def _sha(element: Mapping[str, Any]) -> str | None:
    for item in element.get("verifiedUsing", []):
        if item.get("algorithm") == "sha256" and item.get("hashValue"):
            return str(item["hashValue"]).lower()
    return None


def elements(graph: Iterable[Mapping[str, Any]]) -> list[Element]:
    """The graph's named elements of the four registry types."""
    found = []
    for item in graph:
        type_name = item.get("type")
        if type_name in PREFIX and "name" in item and "spdxId" in item:
            found.append(
                Element(
                    canonical(type_name, item["name"]),
                    item["spdxId"],
                    _sha(item),
                    item["name"],
                )
            )
    return found


def unique(found: Iterable[Element]) -> dict[Key, Element]:
    """*found* by key, without keys held by two elements (I5: ambiguous)."""
    found = list(found)
    counts = Counter(e.key for e in found)
    return {e.key: e for e in found if counts[e.key] == 1}


def duplicate_ids(graph: Iterable[Mapping[str, Any]]) -> list[str]:
    """spdxIds carried by more than one element of *graph*."""
    counts = Counter(e["spdxId"] for e in graph if "spdxId" in e)
    return sorted(i for i, n in counts.items() if n > 1)


@dataclass
class Captured:
    """One step's outcome, as the script recorded it."""

    step: Step
    rc: int
    stdout: str
    stderr: str
    reg_raw: bytes | None
    #: surface -> graph, for each output that exists and parses.
    graphs: dict[str, list[dict[str, Any]]]
    #: surface -> raw bytes, or None when the file is missing.
    raw: dict[str, bytes | None]
    #: surface -> why the output is unusable (missing, bad JSON).
    broken: dict[str, str]

    @property
    def registry(self) -> dict[Key, Entry] | None:
        """The registry after the step, parsed (None: absent or not v3)."""
        return None if self.reg_raw is None else parse_registry(self.reg_raw)

    @property
    def stderr_lines(self) -> list[str]:
        """Non-blank stderr lines."""
        return [line for line in self.stderr.splitlines() if line.strip()]


def _outputs(
    work: Path, step: Step
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, bytes | None], dict[str, str]]:
    """*step*'s outputs: parsed graphs, raw bytes, and why any is unusable."""
    graphs: dict[str, list[dict[str, Any]]] = {}
    raw: dict[str, bytes | None] = {}
    broken: dict[str, str] = {}
    for surface, rel in step.outputs:
        path = work / rel
        data = path.read_bytes() if path.exists() else None
        raw[surface] = data
        if data is None:
            broken[surface] = f"{rel} missing"
            continue
        try:
            graph = json.loads(data)["@graph"]
        except (ValueError, KeyError, TypeError) as exc:
            broken[surface] = f"{rel}: {exc}"
            continue
        graphs[surface] = graph if isinstance(graph, list) else []
    return graphs, raw, broken


def capture(work: Path, steps: Iterable[Step]) -> list[Captured]:
    """Read back each of *steps* from the script's ``logs`` directory."""
    logs = work / "logs"
    result = []
    for step in steps:
        rc_file = logs / f"{step.tag}.rc"
        if not rc_file.exists():
            break  # the script stopped before this step
        reg = logs / f"{step.tag}.reg"
        graphs, raw, broken = _outputs(work, step)
        result.append(
            Captured(
                step,
                int(rc_file.read_text(encoding="utf-8").strip() or "-1"),
                (logs / f"{step.tag}.out").read_text("utf-8", errors="replace"),
                (logs / f"{step.tag}.err").read_text("utf-8", errors="replace"),
                reg.read_bytes() if reg.exists() else None,
                graphs,
                raw,
                broken,
            )
        )
    return result


def project_files(fixture: Path, step: Step, exclude: str | None) -> dict[str, str]:
    """Project-relative NFC path -> sha256 of every file on disk after *step*
    (pristine fixture plus the simulated changes), minus *exclude*."""
    files = {
        p.relative_to(fixture).as_posix(): p for p in fixture.rglob("*") if p.is_file()
    }
    shas = {rel: hashlib.sha256(p.read_bytes()).hexdigest() for rel, p in files.items()}
    for rel, data in step.overlay.items():
        if data is None:
            shas.pop(rel, None)
        else:
            shas[rel] = hashlib.sha256(data).hexdigest()
    # A registry key is NFC whatever the file system's spelling.
    shas = {unicodedata.normalize("NFC", rel): sha for rel, sha in shas.items()}
    if exclude:
        shas.pop(exclude, None)
    return shas


_GATE_DROPPED = re.compile(
    r"^INFO: ID registry: content gate dropped for (\S+) (.+): "
    r"imported id \S+ replaces \S+$"
)


def gate_dropped(stderr: str) -> list[Key]:
    """The key of each ``content gate dropped`` INFO line in *stderr*, in
    order (`id import` says so once per key)."""
    keys = []
    for line in stderr.splitlines():
        match = _GATE_DROPPED.match(line)
        if match:
            keys.append(canonical(match[1], str(ast.literal_eval(match[2]))))
    return keys


def warning_shapes(stderr: str) -> list[str]:
    """Each ``WARNING:``/``ERROR:`` line with ids, paths and numbers
    masked, for a per-check summary of what the steps logged."""
    shapes = []
    for line in stderr.splitlines():
        if line.startswith(("WARNING: ", "ERROR: ")):
            line = re.sub(r"\S*/\S*", "<path>", line)
            shapes.append(re.sub(r"\d+", "N", line)[:160])
    return shapes
