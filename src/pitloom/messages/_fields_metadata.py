# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The values the project-metadata and file-discovery lines name: a
declared build backend, the discoverer that read a project's files, the
``setup()`` keywords passed imperatively and the dynamic fields left
unresolved.

See also: :mod:`pitloom.messages._fields` (every field, these included),
:mod:`pitloom.messages._metadata_read`, :mod:`pitloom.messages._metadata_dynamic`
and :mod:`pitloom.messages._file_discovery` (the lines).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from pitloom.messages._field_type import Field
from pitloom.messages._field_writers import free_text, joined, plain_text

#: The file discoverers a line names, as Pitloom names each one.
DISCOVERERS: Final = ("Flit", "Hatchling", "PDM", "Poetry", "Setuptools")

#: One ``setup()`` keyword, or the ``**kwargs`` unpack standing for any.
_KWARG: Final = r"(?:\*\*)?[A-Za-z_][A-Za-z0-9_]*"
#: One ``[project]`` key.
_PROJECT_KEY: Final = r"[a-z][a-z0-9-]*"

#: The project-metadata and file-discovery lines' fields.
METADATA_FIELDS: Final[Mapping[str, Field]] = MappingProxyType(
    {
        "backend": Field(
            r".+",
            free_text,
            "<backend>",
            "the build backend a pyproject.toml declares in [build-system] "
            "build-backend, as written; escaped when it holds a control "
            "character",
            free=True,
        ),
        "discoverer": Field(
            "|".join(re.escape(name) for name in DISCOVERERS),
            plain_text,
            "<discoverer>",
            "the file discoverer of the project's build backend: "
            + ", ".join(f"`{name}`" for name in DISCOVERERS),
        ),
        "kwargs": Field(
            rf"{_KWARG}(?:, {_KWARG})*",
            joined,
            "<kwargs>",
            "the file-selection `setup()` keywords a setup.py passes, "
            "comma-separated (`packages, package_dir`); `**kwargs` for an "
            "unpacked mapping",
        ),
        "metadata_fields": Field(
            rf"{_PROJECT_KEY}(?:, {_PROJECT_KEY})*",
            joined,
            "<metadata-fields>",
            "[project] keys, comma-separated (`version, dependencies`)",
        ),
    }
)
