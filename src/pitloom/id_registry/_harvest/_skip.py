# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The elements a harvest leaves out of the ID registry for their key or id,
and the registry file refused (or, in the ``warn`` mode, loaded with a
``WARNING:``) when an entry of it holds a credential.

See also: :mod:`pitloom.id_registry._harvest` (its user) and
:mod:`pitloom.id_registry._credentials` (the credential rule).
"""

from __future__ import annotations

import logging
import os

from pitloom.id_registry._credentials import (
    id_holds_credentials,
    key_holds_credentials,
)
from pitloom.id_registry._types import RegistryEntry, is_utf8_text
from pitloom.messages.files import warn_registry_name_skipped
from pitloom.messages.url_credentials import (
    registry_file_refused_error,
    warn_registry_file_entry_kept,
    warn_registry_key_credentials_skipped,
)

log = logging.getLogger("pitloom.id_registry")


def unrecordable(label: str, key: tuple[str, str], spdx_id: str) -> bool:
    """Whether the element, its *key* (type and name, called *label*) or
    *spdx_id* is left out of the registry: a text its UTF-8 file cannot
    hold, or one holding credentials; says so with one ``WARNING:``."""
    for what, text in ((label, key[1]), ("spdxId", spdx_id)):
        if not is_utf8_text(text):
            warn_registry_name_skipped(log, what, text)
            return True
    for text, holds in (
        (key[1], key_holds_credentials(*key)),
        (spdx_id, id_holds_credentials(spdx_id)),
    ):
        if holds:
            warn_registry_key_credentials_skipped(log, text)
            return True
    return False


def check_entries_credentials(
    elements: dict[tuple[str, str], RegistryEntry],
    file: str | os.PathLike[str],
    *,
    refuse: bool,
) -> None:
    """Check each entry of *elements* (as the registry *file* holds them)
    for a key or id that holds credentials, named (masked), the key's when
    both hold one. With *refuse* (the ``refuse`` mode) the first in key
    order refuses the file, never rewritten; else each is one ``WARNING:``
    and the file is loaded as it is.

    Raises:
        pitloom.messages.CodedValueError: ``credentials-unsafe/registry``,
            with *refuse* only.
    """
    for key, entry in sorted(elements.items()):
        text = next(
            (
                text
                for text, holds in (
                    (key[1], key_holds_credentials(*key)),
                    (entry.spdx_id, id_holds_credentials(entry.spdx_id)),
                )
                if holds
            ),
            None,
        )
        if text is None:
            continue
        if refuse:
            raise registry_file_refused_error(file, text) from None
        warn_registry_file_entry_kept(log, file, text)
