# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Where a configuration value sits (:class:`ConfigPlace`, the
``config_key`` of a line), what it must be (:data:`EXPECTED`) and where a
moved key went (:data:`DESTINATIONS`): closed tables, so a configuration
line names a table, a key and a requirement only in these spellings.

:class:`ConfigPlace` is the one place that spells a table the
``pyproject.toml`` way (``[tool.pitloom.provenance]``) or the ``setup.cfg``
way (``[tool:pitloom:provenance]``). A reader builds a place in the TOML
spelling; :meth:`pitloom.messages.config.ConfigError.located` spells it for
``setup.cfg``.

This module imports no catalogue entry: the fields
(:mod:`pitloom.messages._fields_config`) are built from it, and the core
configuration readers import it through :mod:`pitloom.messages.config`.

See also: :mod:`pitloom.messages._config_found` (what was found),
:mod:`pitloom.messages._config` (the entries).
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from pitloom.core.internal_error import InternalError

#: The configuration tables a line names, dotted as in ``pyproject.toml``,
#: without brackets. A drift test holds the ``[tool.pitloom...]`` ones equal
#: to :data:`pitloom.core._config_keys.KNOWN_KEYS`.
TABLES: Final[tuple[str, ...]] = (
    "tool",
    "tool.pitloom",
    "tool.pitloom.content-type",
    "tool.pitloom.creation",
    "tool.pitloom.fragment",
    "tool.pitloom.provenance",
    "tool.hatch.build.hooks.pitloom",
)
#: The arrays of tables a line names (``[[tool.pitloom.creator]]``), each
#: key spelling a reader takes. A drift test holds them equal to the arrays
#: of :data:`pitloom.core._config_keys.KNOWN_ENTRY_KEYS` (``files`` is an
#: array of inline tables under a key, named as a key).
ARRAY_TABLES: Final[tuple[str, ...]] = (
    "tool.pitloom.content-type.override",
    "tool.pitloom.creation-tool",
    "tool.pitloom.creation_tool",
    "tool.pitloom.creator",
)

#: A key as a reader names it: lower-case, ``-`` or ``_`` between words.
KEY: Final = r"[a-z][a-z0-9_-]*"
_KEY_RE: Final = re.compile(KEY)
#: An entry's position in an array, counted from 0.
_INDEX: Final = r"(?:0|[1-9][0-9]*)"


def _table_text(table: str, setup_cfg: bool) -> str:
    """*table* (one of :data:`TABLES` or :data:`ARRAY_TABLES`) in brackets:
    dotted, an array in double brackets; for ``setup.cfg`` joined by ``:``
    in single brackets (INI has no arrays of tables: an array's entries are
    read from the section of that name)."""
    if setup_cfg:
        return f"[{table.replace('.', ':')}]"
    return f"[[{table}]]" if table in ARRAY_TABLES else f"[{table}]"


#: Every table as a line names it, in either spelling.
TABLE_PATTERN: Final = "|".join(
    re.escape(_table_text(table, setup_cfg))
    for table in (*TABLES, *ARRAY_TABLES)
    for setup_cfg in (False, True)
)
#: A ``config_key`` value: a table, then a key, an entry and the entry's
#: key, each when given.
PLACE_PATTERN: Final = rf"(?:{TABLE_PATTERN})(?: {KEY})?(?: entry {_INDEX})?(?: {KEY})?"


@dataclass(frozen=True)
class ConfigPlace:
    """Where a value sits in a configuration: *table* (one of
    :data:`TABLES` or :data:`ARRAY_TABLES`, dotted, no brackets), then the
    *key* in it, the *entry* of an array (counted from 0) and the *sub* key
    of that entry, each when given. Written as ``[tool.pitloom] pretty``,
    ``[tool.pitloom.fragment] files entry 2 role``, ``[[tool.pitloom.creator]]
    entry 0 type`` or ``[tool.pitloom.provenance]`` (the table itself);
    *setup_cfg* spells the table ``setup.cfg``'s way
    (``[tool:pitloom:provenance]``).

    An array of tables takes no *key*: its entries are tables, so
    ``ConfigPlace("tool.pitloom.creator", entry=0, sub="type")``. A key that
    holds inline tables takes its entry after it:
    ``ConfigPlace("tool.pitloom.fragment", "files", entry=2, sub="role")``.

    Raises:
        pitloom.core.internal_error.InternalError: The table is not in the
            closed tables, a key is not a key, an entry is not a whole
            number, or the parts do not nest (a *sub* without an *entry*, a
            *key* of an array, an *entry* of a plain table without a key).
    """

    table: str
    key: str | None = None
    entry: int | None = None
    sub: str | None = None
    setup_cfg: bool = False

    def __post_init__(self) -> None:
        """Check the place against the closed tables and the nesting."""
        array = self.table in ARRAY_TABLES
        problem = next(
            (
                why
                for ok, why in (
                    (array or self.table in TABLES, "an unknown table"),
                    (
                        all(
                            k is None
                            or (isinstance(k, str) and _KEY_RE.fullmatch(k) is not None)
                            for k in (self.key, self.sub)
                        ),
                        "a key that is not one",
                    ),
                    (
                        self.entry is None
                        or (
                            isinstance(self.entry, int)
                            and not isinstance(self.entry, bool)
                            and self.entry >= 0
                        ),
                        "an entry that is not a whole number",
                    ),
                    (self.sub is None or self.entry is not None, "a sub without entry"),
                    (not (array and self.key is not None), "a key of an array"),
                    (
                        self.entry is None or array or self.key is not None,
                        "an entry of a table without a key",
                    ),
                )
                if not ok
            ),
            None,
        )
        if problem is not None:
            raise InternalError(f"config place {self!r}: {problem}")

    @property
    def text(self) -> str:
        """The place as a line names it."""
        parts = [_table_text(self.table, self.setup_cfg)]
        if self.key is not None:
            parts.append(self.key)
        if self.entry is not None:
            parts.append(f"entry {self.entry}")
        if self.sub is not None:
            parts.append(self.sub)
        return " ".join(parts)

    def at(self, name: str) -> ConfigPlace:
        """The place of *name* inside this one: a key of a table, or the
        key of an entry (``ConfigPlace("tool.pitloom").at("pretty")``).

        Raises:
            pitloom.core.internal_error.InternalError: This place holds no
                keys (it names a key already, or an array not at an entry).
        """
        if self.entry is not None and self.sub is None:
            return dataclasses.replace(self, sub=name)
        if self.entry is None and self.key is None and self.table not in ARRAY_TABLES:
            return dataclasses.replace(self, key=name)
        raise InternalError(f"config place {self!r} holds no key {name!r}")

    def entry_at(self, index: int) -> ConfigPlace:
        """The place of entry *index* of this array (an array of tables, or
        a key holding inline tables).

        Raises:
            pitloom.core.internal_error.InternalError: This place is no
                array, or names an entry already.
        """
        array = self.table in ARRAY_TABLES or self.key is not None
        if self.entry is not None or not array:
            raise InternalError(f"config place {self!r} has no entry {index!r}")
        return dataclasses.replace(self, entry=index)

    def spelt(self, setup_cfg: bool) -> ConfigPlace:
        """This place, the table spelt for ``setup.cfg`` when *setup_cfg*."""
        return dataclasses.replace(self, setup_cfg=setup_cfg)


@dataclass(frozen=True)
class Parameter:
    """A library parameter a value was given as (``max_model_extract_bytes``,
    ``PitloomConfig.max_download_bytes``), or a command-line option a
    library function was handed it from (``--sbom-basename``): the stage
    flag of a shared validator that, given a :class:`ConfigPlace` instead,
    says ``config-invalid``.

    Raises:
        pitloom.core.internal_error.InternalError: *name* is neither a
            dotted Python name nor a long option.
    """

    name: str

    def __post_init__(self) -> None:
        """Check the name."""
        if not isinstance(self.name, str) or _PARAMETER_RE.fullmatch(self.name) is None:
            raise InternalError(f"parameter {self.name!r} is not a Python name")


_PARAMETER_RE: Final = re.compile(
    r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*|--[a-z][a-z0-9-]*", re.ASCII
)


#: ``max-source-metadata-bytes``'s smallest budget but 0: a drift test holds
#: it equal to :data:`pitloom.core.provenance.MIN_SOURCE_METADATA_BYTES`.
BUDGET_MINIMUM: Final = 8
#: What a URL credential fingerprint looks like. A refusal says this, never
#: the value given: it may be the credential itself, pasted by mistake.
FINGERPRINT_SHAPE: Final = "sha256: and 16 to 64 lowercase hex digits"

#: What a value must be, by id, as a line says it after ``must be``: a
#: closed table. The ``one-of-*`` texts list each choice sorted; a drift test
#: holds each equal to the reader's set of choices.
EXPECTED: Final[Mapping[str, str]] = MappingProxyType(
    {
        "boolean": "true or false",
        "integer": "an integer",
        "positive": "an integer of at least 1",
        "budget": f"0 (no cap) or an integer of at least {BUDGET_MINIMUM}",
        "string": "a string",
        "non-empty": "a non-empty string",
        "string-or-table": "a string or an inline table",
        "table": "a table",
        "array": "an array",
        "array-of-tables": "an array of tables",
        "array-of-strings": "an array of strings",
        "string-or-array": "a string or an array of strings",
        "one-of-format": "one of annotation, both, comment",
        "one-of-detail": "one of full, minimal",
        "one-of-schema": "one of pitloom/1",
        "one-of-preserve": "one of always, auto, never",
        "one-of-method": "one of auto, extension, magika",
        "creator-type": "one of agent, organization, person, software-agent",
        "media-type": "a media type type/subtype (image/png)",
        "file-name": "a file name, not a path",
        "bare-file-name": "a plain file name (not a path, not only .spdx3.json)",
        "datetime": "an ISO 8601 date and time",
        "config-source": "a path to a configuration file, or a PitloomConfig",
        "fingerprint": f"a fingerprint ({FINGERPRINT_SHAPE})",
        "fingerprints": "an array of fingerprints",
        "sha-256": "a SHA-256 in hex (64 characters)",
        "url-credentials-mode": '"warn" or "refuse"',
        "sbom-content": "an SBOM, not empty or white space only",
        "local-file": "a local file, not a URL",
        "local-model": "a local model file, not a Hugging Face model "
        "(generate_model_sbom reads one)",
    }
)


def expected_text(expected: object) -> str:
    """The text of the id *expected* (:data:`EXPECTED`).

    Raises:
        ValueError: It is not an id of the table.
    """
    if not isinstance(expected, str) or expected not in EXPECTED:
        raise ValueError(f"not an expected id: {expected!r}")
    return EXPECTED[expected]


#: Where a moved key went, as a ``config-moved`` line names it: a closed
#: table, in the ``pyproject.toml`` spelling whatever the source (setup.cfg
#: has no arrays of tables to point at). A drift test holds every
#: destination of the moved-key tables of :mod:`pitloom.core._config_legacy`
#: and :mod:`pitloom.plugins._hatch_config` in it.
DESTINATIONS: Final[tuple[str, ...]] = (
    "[[tool.pitloom.creation-tool]] name",
    "[[tool.pitloom.creator]] email",
    "[[tool.pitloom.creator]] name",
    "[[tool.pitloom.creator]] type",
    "[tool.pitloom.fragment] files",
    "[tool.pitloom] extract-file-header and [tool.pitloom.content-type]",
    "[tool.pitloom] id-registry",
    "[tool.pitloom] sbom-basename",
    "[tool.pitloom] update-id-registry",
)


def place_text(value: object) -> str:
    """A :class:`ConfigPlace` as a line names it.

    Raises:
        ValueError: *value* is no place.
    """
    if not isinstance(value, ConfigPlace):
        raise ValueError(f"not a config place: {value!r}")
    return value.text


def tables_text(value: object) -> str:
    """A list or tuple of places that each name a table only, joined by
    `` or ``; an empty one writes nothing, which the field's shape refuses.

    Raises:
        ValueError: It is neither, or holds a place naming a key.
    """
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"not a list: {value!r}")
    texts = []
    for place in value:
        if not isinstance(place, ConfigPlace) or place.key or place.entry is not None:
            raise ValueError(f"not a table: {place!r}")
        texts.append(place.text)
    return " or ".join(texts)
