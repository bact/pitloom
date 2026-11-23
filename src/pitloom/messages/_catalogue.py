# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every catalogued message, by code.

See also: :mod:`pitloom.messages` (the public names).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Final

from pitloom.messages import (
    _build,
    _card_malformed,
    _config,
    _config_unsafe,
    _dependency,
    _file_discovery,
    _file_unreadable,
    _file_unwritable,
    _fragments,
    _fragments_merge,
    _git,
    _git_decisions,
    _hook,
    _hub,
    _input_not_found,
    _json_malformed,
    _lfs_pointer,
    _license_db,
    _license_expression,
    _license_relationship_invalid,
    _lock_entry,
    _lock_file,
    _metadata_dynamic,
    _metadata_read,
    _model_field,
    _model_stub,
    _options,
    _over_cap,
    _pypi,
    _pypi_info,
    _registry_conflict,
    _registry_file,
    _registry_keys,
    _registry_save,
    _remote_fetch,
    _sbom_input,
    _sbom_target,
    _target_input,
    _text_malformed,
    _url_credentials,
    _url_credentials_git,
    _usage_unparseable,
    _usage_unusable,
)
from pitloom.messages._summary import Summary
from pitloom.messages._types import Message


def _by_code(entries: Iterable[Message]) -> Mapping[str, Message]:
    """*entries* keyed by code, read-only.

    Raises:
        ValueError: Two entries share a code, or two of one family name
            different conditions (a variant never changes the condition).
    """
    found: dict[str, Message] = {}
    conditions: dict[str, str] = {}
    for entry in entries:
        if entry.code in found:
            raise ValueError(f"message code {entry.code!r} is catalogued twice")
        held = conditions.setdefault(entry.family, entry.condition)
        if held != entry.condition:
            raise ValueError(
                f"{entry.code}: condition {entry.condition!r}, its family's is {held!r}"
            )
        found[entry.code] = entry
    return MappingProxyType(found)


#: Every catalogued message, by code.
MESSAGES: Final = _by_code(
    (
        *_lfs_pointer.ENTRIES,
        *_over_cap.ENTRIES,
        *_model_stub.ENTRIES,
        *_model_field.ENTRIES,
        *_file_unreadable.ENTRIES,
        *_file_unwritable.ENTRIES,
        *_usage_unparseable.ENTRIES,
        *_usage_unusable.ENTRIES,
        *_text_malformed.ENTRIES,
        *_card_malformed.ENTRIES,
        *_lock_file.ENTRIES,
        *_lock_entry.ENTRIES,
        *_dependency.ENTRIES,
        *_json_malformed.ENTRIES,
        *_sbom_target.ENTRIES,
        *_input_not_found.ENTRIES,
        *_config_unsafe.ENTRIES,
        *_pypi.ENTRIES,
        *_remote_fetch.ENTRIES,
        *_hub.ENTRIES,
        *_pypi_info.ENTRIES,
        *_git.ENTRIES,
        *_git_decisions.ENTRIES,
        *_license_relationship_invalid.ENTRIES,
        *_license_expression.ENTRIES,
        *_license_db.ENTRIES,
        *_options.ENTRIES,
        *_config.ENTRIES,
        *_sbom_input.ENTRIES,
        *_target_input.ENTRIES,
        *_registry_file.ENTRIES,
        *_registry_conflict.ENTRIES,
        *_registry_keys.ENTRIES,
        *_registry_save.ENTRIES,
        *_url_credentials.ENTRIES,
        *_url_credentials_git.ENTRIES,
        *_metadata_read.ENTRIES,
        *_metadata_dynamic.ENTRIES,
        *_file_discovery.ENTRIES,
        *_build.ENTRIES,
        *_hook.ENTRIES,
        *_fragments.ENTRIES,
        *_fragments_merge.ENTRIES,
    )
)

#: Every summary: an ``INFO:`` line of no condition, printed without a code.
SUMMARIES: Final[tuple[Summary, ...]] = (
    *_registry_keys.SUMMARIES,
    *_registry_save.SUMMARIES,
    *_git.SUMMARIES,
    *_hook.SUMMARIES,
    *_fragments_merge.SUMMARIES,
)
