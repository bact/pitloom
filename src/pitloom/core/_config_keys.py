# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The keys of ``[tool.pitloom]`` and the warning for any other key.

:data:`KNOWN_KEYS` is the one list of every key the readers in
:mod:`pitloom.core._config_parse` and :mod:`pitloom.core._config_parse_scan`
look at; ``tests/core/test_config_unknown_keys.py`` fails when the two drift.

See also: :mod:`pitloom.core._config_parse` and
:mod:`pitloom.core._config_legacy` (keys that moved, which are errors).
"""

from __future__ import annotations

import difflib
import logging
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

from pitloom.messages.config import ConfigPlace, warn_config_unknown_key

log = logging.getLogger(__name__)

_CUTOFF = 0.75

#: Every key by table, ``""`` being ``[tool.pitloom]`` itself, both
#: spellings where a reader takes two.
KNOWN_KEYS: dict[str, frozenset[str]] = {
    "": frozenset(
        {
            "accept-url-credentials",
            "content-type",
            "creation",
            "creation-comment",
            "creation-datetime",
            "creation-tool",
            "creation_comment",
            "creation_datetime",
            "creation_tool",
            "creator",
            "describe-relationship",
            "describe_relationship",
            "enrich",
            "extract-file-header",
            "fragment",
            "id-registry",
            "max-dataset-hash-bytes",
            "max-download-bytes",
            "max-model-extract-bytes",
            "offline",
            "pretty",
            "provenance",
            "sbom-basename",
            "scan-model-usage",
            "update-id-registry",
            "url-credentials",
            "use-lockfile",
        }
    ),
    "creation": frozenset(
        {
            "comment",
            "creation-comment",
            "creation-datetime",
            "creation_comment",
            "creation_datetime",
            "datetime",
            "no-creation-tool",
            "no_creation_tool",
        }
    ),
    "provenance": frozenset(
        {
            "detail",
            "format",
            "max-source-metadata-bytes",
            "max_source_metadata_bytes",
            "preserve-source-metadata",
            "preserve_source_metadata",
            "schema",
        }
    ),
    "content-type": frozenset({"enabled", "method", "override"}),
    "fragment": frozenset({"files"}),
}

#: The keys of each array of tables' entries, by ``(table, key)`` of the
#: array: ``("", "creator")`` is ``[[tool.pitloom.creator]]``, and
#: ``("fragment", "files")`` the inline tables of ``files``.
KNOWN_ENTRY_KEYS: dict[tuple[str, str], frozenset[str]] = {
    ("", "creator"): frozenset({"email", "name", "type"}),
    ("", "creation-tool"): frozenset({"name"}),
    ("", "creation_tool"): frozenset({"name"}),
    ("content-type", "override"): frozenset({"content-type", "pattern"}),
    ("fragment", "files"): frozenset(
        {
            "description",
            "link-to-main",
            "link_to_main",
            "path",
            "required",
            "role",
            "sha256",
        }
    ),
}


def _table_place(name: str) -> ConfigPlace:
    """The table *name* of :data:`KNOWN_KEYS` (``""`` for ``[tool.pitloom]``)."""
    return ConfigPlace(f"tool.pitloom.{name}" if name else "tool.pitloom")


def _same_key(key: str) -> str:
    """*key* spelled with ``-``, so ``max_source_metadata_bytes`` and
    ``max-source-metadata-bytes`` are one key."""
    return key.replace("_", "-")


def _opposite(key: str, candidate: str) -> bool:
    """Whether one of the two is the other negated (``no-creation-tool`` and
    ``creation-tool``): close in spelling, opposite in meaning."""
    one, two = _same_key(key), _same_key(candidate)
    return one == f"no-{two}" or two == f"no-{one}"


def _hint(
    key: str, known: frozenset[str], owners: tuple[ConfigPlace, ...], table_known: bool
) -> tuple[str | None, tuple[ConfigPlace, ...]]:
    """What to tell the user about the unknown *key*: the table(s) *owners*
    that know it, else the closest *known* key, else nothing. Never both."""
    if table_known and owners:
        return None, owners
    candidates = sorted(c for c in known if not _opposite(key, c))
    close = difflib.get_close_matches(key, candidates, n=1, cutoff=_CUTOFF)
    return (close[0] if close else None), ()


def _warn_unknown(
    table: dict[str, Any],
    place: ConfigPlace,
    known: frozenset[str],
    *,
    source: str | None,
    owners: Callable[[str], tuple[ConfigPlace, ...]] | None = None,
    once_label: str | None = None,
) -> None:
    """One ``WARNING:`` per key of *table* that is not in *known*, in sorted
    order, once per *source* however often it is parsed. *place* is the
    table (or the array entry) as its source spells it. *owners* maps a key
    to the other tables that know it (for a table, not an array entry).
    *once_label* names the table or array in the said-once key (*place* by
    default): an entry's index is no part of it."""
    # one file, however spelt (relative or absolute), warns once
    scope = f"{Path(source).absolute()} " if source else ""
    label = place.text if once_label is None else once_label
    for key in sorted(k for k in table if k not in known):
        setting, tables = _hint(
            key, known, owners(key) if owners else (), owners is not None
        )
        warn_config_unknown_key(
            log,
            place,
            key,
            file=source or None,
            setting=setting,
            tables=tables,
            once=f"{scope}{label} {key!r}",
        )


def _owners(key: str, current: str, is_setup_cfg: bool) -> tuple[ConfigPlace, ...]:
    """The tables other than *current* that know *key*, either spelling, as
    their source spells them."""
    return tuple(
        _table_place(name).spelt(is_setup_cfg)
        for name, keys in sorted(KNOWN_KEYS.items())
        if name != current and _same_key(key) in map(_same_key, keys)
    )


def _entry_places(name: str, key: str, is_setup_cfg: bool) -> tuple[ConfigPlace, str]:
    """The array of entries *key* of the table *name* (``""``: of
    ``[tool.pitloom]``) as a message names it (``files`` holds inline tables,
    named as a key), and its label in the said-once key."""
    if key == "files":
        table = _table_place(name).spelt(is_setup_cfg)
        return table.at(key), f"{table.text} {key!r} entry"
    array = ConfigPlace(".".join(filter(None, ("tool.pitloom", name, key))))
    array = array.spelt(is_setup_cfg)
    return array, array.text


def warn_unknown_keys(
    pitloom_data: dict[str, Any], *, is_setup_cfg: bool, source: str | None = None
) -> None:
    """Warn about every key of *pitloom_data*, a ``[tool.pitloom]`` table,
    that Pitloom does not know: the table itself, its sub-tables and the
    entries of its arrays of tables. The run goes on: the key is ignored.
    Run it before the values are read, so a misspelt required key shows its
    hint ahead of the error that follows.

    *is_setup_cfg* names the table as ``[tool:pitloom]`` does; *source* is
    the file it came from, named in the message and part of what a warning
    is deduplicated on (``None`` for a table that did not come from a file).
    """
    for name, known in KNOWN_KEYS.items():
        table = pitloom_data.get(name) if name else pitloom_data
        if isinstance(table, dict):
            owners = partial(_owners, current=name, is_setup_cfg=is_setup_cfg)
            place = _table_place(name).spelt(is_setup_cfg)
            _warn_unknown(table, place, known, source=source, owners=owners)
    for (name, key), known in KNOWN_ENTRY_KEYS.items():
        holder = pitloom_data.get(name) if name else pitloom_data
        entries = holder.get(key) if isinstance(holder, dict) else None
        array, once_label = _entry_places(name, key, is_setup_cfg)
        for index, entry in enumerate(entries if isinstance(entries, list) else ()):
            if isinstance(entry, dict):
                _warn_unknown(
                    entry,
                    array.entry_at(index),
                    known,
                    source=source,
                    once_label=once_label,
                )
