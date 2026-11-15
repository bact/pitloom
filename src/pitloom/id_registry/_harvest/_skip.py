# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The elements a harvest leaves out of the ID registry for their key or id.

See also: :mod:`pitloom.id_registry._harvest` (its user) and
:mod:`pitloom.id_registry._credentials` (the credential rule).
"""

from __future__ import annotations

import logging

from pitloom.id_registry._credentials import (
    id_holds_credentials,
    key_holds_credentials,
)
from pitloom.id_registry._types import is_utf8_text
from pitloom.messages.files import warn_registry_name_skipped
from pitloom.messages.url_credentials import warn_registry_key_credentials_skipped

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
