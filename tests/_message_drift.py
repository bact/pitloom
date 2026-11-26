# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Helpers of the catalogue's drift tests (tests/messages/test_drift_*.py and
the autouse record check in ``tests/conftest.py``): does a log record, a
source module or a quoted line still agree with :mod:`pitloom.messages`?

See also: tests/_message_quotes.py (does a quoted line match the catalogue),
tests/messages/test_drift_records.py, test_drift_sources.py and
test_drift_quotes.py.
"""

from __future__ import annotations

import ast
import importlib
import logging
import re
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from pitloom.logging_config import CODE_ATTR, escape_controls
from pitloom.messages import (
    MESSAGES,
    TOPIC_TITLES,
    Message,
    code_of,
    trusted_message,
)
from pitloom.messages.config import ConfigPlace
from tests import _strict_uncoded
from tests._docs_scan import REPO_ROOT
from tests._strict_uncoded import strict_finding

SRC_ROOT = REPO_ROOT / "src" / "pitloom"

#: A logger named like this belongs to a test that feeds the catalogue odd
#: text on purpose; its records are not checked
#: (:data:`tests._strict_uncoded.TEST_LOGGER_PREFIX`).
TEST_LOGGER_PREFIX = _strict_uncoded.TEST_LOGGER_PREFIX

#: A value of each field, as a caller passes it.
SAMPLES: dict[str, object] = {
    "activity": "the build",
    "answered": "other-project",
    "archive": "demo-1.0-py3-none-any.whl",
    "arity": "one argument",
    "backend": "mesonpy",
    "card": "model card",
    "classifiers": ["License :: OSI Approved :: MIT License"],
    "claimant": "src/a.txt",
    "command": "clone",
    "command_line": "git clone --depth 1 https://example.org/r.git",
    "config_key": ConfigPlace("tool.pitloom.fragment", "files", entry=2, sub="role"),
    "count": 2,
    "datetime": datetime(1970, 1, 1, tzinfo=timezone.utc),
    "declared": "b" * 64,
    "declared_in": "optional-dependencies",
    "digest": "d" * 64,
    "destination": "[tool.pitloom] id-registry",
    "dependency": "demo[dev]",
    "dropped": ("1.0", "2.0"),
    "extra_name": "dev",
    "kept": "uv.lock",
    "line_number": 3,
    "lock_key": "package",
    "lock_value": "==1.*",
    "package": "flask",
    "source_kind": "git",
    "value_type": [],
    "dir": "m/sub",
    "discoverer": "Setuptools",
    "element": "https://example.org/ns#Package-1",
    "element_type": "software_File",
    "element_kind": "dataset package",
    "elements": ("model-architecture (written in ai_typeOfModel)",),
    "entities": ("software_File 'a.txt'", "src/a.txt"),
    "entries": ("prety", "fragments-dir"),
    "entity": "data/imdb",
    "entry_key": "sbom.vendor",
    "entry": "archive/data.pkl",
    "error": "Error while deserializing header: invalid header length",
    "exception_type": EOFError(),
    "extension": ".spdx3.json",
    "exit_code": -9,
    "expected": "boolean",
    "expression": "Apache-2.0 AND MIT",
    "failure": PermissionError(13, "Permission denied", "/abs/m/a.bin"),
    "field": "project.readme",
    "file": "m/a.bin",
    "files": "a.gguf, b.bin and 3 more",
    "fingerprint": "sha256:0123456789abcdef",
    "format": "gguf",
    "formats": ["gguf", "onnx"],
    "hash_algorithm": "sha256",
    "holder_type": "software_Package",
    "hosts": "files.pythonhosted.org",
    "identity_part": "name",
    "install_name": "demo/a.py",
    "input": "wheel file",
    "key": "FIELD",
    "later_member": "demo\\a.py",
    "key_reason": "outside the project root",
    "kwargs": ["packages", "**kwargs"],
    "license": "MIT OR",
    "license_reason": "not found: Acme-Terms",
    "limit": 1024,
    "fields": ("type_of_model", "properties.tags (kept as raw string)"),
    "folders": "'svc', 'lib' and 1 more",
    "measured": "a" * 64,
    "member": "demo-1.0.dist-info/METADATA",
    "members": (
        "demo-1.0.dist-info/sboms/a.spdx3.json",
        "demo-1.0.dist-info/sboms/b.json",
    ),
    "minimum_version": "1.29.0",
    "metadata_fields": ["version", "optional-dependencies"],
    "module": "h5py",
    "name": "a.txt",
    "namespace": "https://example.org/ns",
    "namespace_problem": "must not contain '#'",
    "new_id": "https://example.org/ns#File-2",
    "given_namespace": "https://example.org/other",
    "got": "maybe",
    "number": 2,
    "oid": "0f" * 32,
    "other_digest": "c" * 64,
    "option": "--allow-build",
    "other": "--pretty",
    "outcome": "skipped",
    "output": "ERROR Backend subprocess exited when trying to invoke build_wheel",
    "part": "training_config.optimizer",
    "path": "m.gguf",
    "pointer": "software_downloadLocation",
    "process_group": 4242,
    "project_paths": ("src/a.py",),
    "property": "from_",
    "provenance_field": "byte_size",
    "root": "proj",
    "sbom_filename": "demo.spdx3.json",
    "sbom_value": "other-project",
    "project_value": "other",
    "purpose": "per-wheel model-scan budget",
    "python": "3.10",
    "reason": "GGUF header declares 1000000 tensors",
    "ref": "v1.0",
    "ref_kind": "tag",
    "reference": "https://example.org/ns#Package-9",
    "refusal": "invalid choice: 'x'",
    "registry_part": "spdxId",
    "requirement": "pitloom[gguf]",
    "duration": 30,
    "setting": "url-credentials",
    "settings": ("tool.setuptools.cmdclass", "metadata.version"),
    "signal": "SIGTERM",
    "size": 3,
    "skipped": 1,
    "source": "the PyPI JSON API",
    "spdx_id": "https://example.org/ns#File-1",
    "steps": "separator, version_spelling",
    "subcommand": "fragment validate",
    "table": "[tool.pitloom]",
    "tables": (ConfigPlace("tool.pitloom.provenance"), ConfigPlace("tool.pitloom")),
    "target": "https://example.org/x.whl",
    "unit": "byte",
    "url": "https://pypi.org/project/demo/1.0/",
    "use": "for file scanning",
    "value": "-1",
    "version": "1.0",
    "wheel_value": "demo",
    "when": "without --allow-build",
    "why": "not https",
    "authors": ["Doe, Jane", "Ann and Bob"],
    "base_name": "sbom",
    "author_key": "MAINTAINER_EMAIL",
    "entry_count": 2,
    "dependency_count": 3,
    "dataset": "imdb-clean",
    "dataset_input": "imdb",
    "dataset_spelling": "Org/Imdb",
    "dataset_source": "corpus/README.md",
    "dataset_field": "version",
    "dataset_value_type": 1.1,
    "model": "org/tiny-model",
    "properties": ["dataset name", "name"],
}


def record_problem(record: logging.LogRecord) -> str | None:
    """What is wrong with *record* as a catalogued one, or ``None``: first
    the strict check's finding (:func:`tests._strict_uncoded.strict_finding`:
    a record said without a code), then ``None`` when it has no
    :data:`~pitloom.logging_config.CODE_ATTR`, it is a ``DEBUG`` record
    (printed without its code: a message said once repeats at ``DEBUG``), or
    its code is catalogued and its text one of the entry's lines at its
    level."""
    finding = strict_finding(record)
    if finding is not None:
        return finding.problem
    code = getattr(record, CODE_ATTR, None)
    if (
        code is None
        or record.levelno <= logging.DEBUG
        or record.name.startswith(TEST_LOGGER_PREFIX)
    ):
        return None
    if not isinstance(code, str) or code not in MESSAGES:
        return f"uncatalogued code {code!r}"
    text = escape_controls(record.getMessage())
    line = f"{record.levelname}: {text} [{code}]"
    if trusted_message(line) is not MESSAGES[code]:
        return f"{line!r} is not the text or level of {code!r}"
    return None


def raised_as(exc: BaseException, message: Message) -> bool:
    """Whether *exc* says *message*: it carries the code
    (:func:`~pitloom.messages.code_of`), and its text, printed as the
    command line prints an error, is one of the entry's ``ERROR`` lines."""
    printed = f"ERROR: {escape_controls(str(exc))} [{message.code}]"
    return code_of(exc) == message.code and trusted_message(printed) is message


def family_names() -> dict[str, tuple[str, ...]]:
    """Each family to the names its topic module
    (``pitloom.messages.<topic>``) exports for its entries
    (``LFS_POINTER``)."""
    found: dict[str, list[str]] = {}
    for topic in TOPIC_TITLES:
        module = importlib.import_module(f"pitloom.messages.{topic.replace('-', '_')}")
        for name in module.__all__:
            value = getattr(module, name)
            if isinstance(value, Message):
                found.setdefault(value.family, []).append(name)
    return {family: tuple(sorted(names)) for family, names in found.items()}


def source_modules() -> Iterator[tuple[str, ast.Module]]:
    """Each module of ``src/pitloom`` but the catalogue's own, as its
    path under the package (POSIX) and its syntax tree."""
    for path in sorted(SRC_ROOT.rglob("*.py")):
        rel = path.relative_to(SRC_ROOT).as_posix()
        if not rel.startswith("messages/"):
            yield rel, ast.parse(path.read_bytes())


def referenced_names(tree: ast.AST) -> set[str]:
    """Every name *tree* reads, imports or takes from a module."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            found.update(a.name.rpartition(".")[2] for a in node.names)
    return found


def _docstring_ids(tree: ast.AST) -> set[int]:
    return {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        )
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }


def string_constants(tree: ast.AST) -> list[str]:
    """Every string constant of *tree* but a docstring, with the literal
    parts of an f-string."""
    skip = _docstring_ids(tree)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in skip
    ]


_EDGE = " :;,()"


_VALUE = re.compile(r"%\([a-z_]+\)s|%s")


def cores(text: str) -> list[str]:
    """The literal pieces of *text* (a template, or a string of the source)
    between its values (``%(name)s``, ``%s``), trimmed of edge punctuation,
    20 characters or more."""
    pieces = (piece.strip(_EDGE) for piece in _VALUE.split(text))
    return [piece for piece in pieces if len(piece) >= 20]


def family_cores() -> dict[str, set[str]]:
    """Each family to the cores of its entries' lines."""
    found: dict[str, set[str]] = {}
    for entry in MESSAGES.values():
        for line in entry.lines:
            found.setdefault(entry.family, set()).update(cores(line.template))
    return found


def families_said_by(texts: list[str], *, whole: bool = False) -> set[str]:
    """The families whose line text any of *texts* holds, or is part of;
    with *whole*, only those whose text one of *texts* holds whole."""
    said = family_cores()
    return {
        family
        for family, family_texts in said.items()
        for text in texts
        for piece in cores(text)
        for core in family_texts
        if core in piece or (not whole and piece in core)
    }


def relative(path: Path) -> str:
    """*path* under the repository, POSIX."""
    return path.relative_to(REPO_ROOT).as_posix()
