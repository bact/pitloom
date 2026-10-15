# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Fresh ids minted while merging SPDX 3 fragments.

See also: :mod:`pitloom.assemble.spdx3._fragments_unify` (unification, which
renames a fragment element whose id another element holds) and
:mod:`pitloom.assemble.spdx3.fragments` (the merged document's extra
annotations and SBOM).
"""

from __future__ import annotations

import logging
from collections.abc import Container

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._fragments_hashes import hash_conflict
from pitloom.export.spdx3_json import require_spdx_id
from pitloom.id_registry import type_id_prefix

log = logging.getLogger(__name__)


def mint_extra_id(namespace: str, prefix: str, *taken: Container[str]) -> str:
    """The first ``<namespace>#<prefix>-<n>`` id, counting from 1, that none
    of *taken* contains."""
    n = 1
    while True:
        candidate = f"{namespace}#{prefix}-{n}"
        if not any(candidate in ids for ids in taken):
            return candidate
        n += 1


def rename_id_clash(
    obj: spdx3.Element,
    holder: spdx3.SHACLObject,
    namespace: str,
    *taken: Container[str],
) -> str:
    """Give *obj* a fresh id in *namespace*, none of *taken*, because
    *holder* already holds its id (*holder* is of another type, or of the
    same type with a conflicting digest); log the one ``WARNING:`` and
    return the new id.

    Call before *obj* is indexed or its references are rewritten: a
    reference to it is a linked object and follows the new id."""
    old_id = require_spdx_id(obj)
    type_name = type(obj).__name__
    new_id = mint_extra_id(namespace, type_id_prefix(type_name), *taken)
    algorithm = hash_conflict(obj, holder) if type(holder) is type(obj) else None
    log.warning(
        "Merge: %s %r shares spdxId %s with a %s%s; keeping both, it gets new id %s.",
        type_name,
        getattr(obj, "name", None),
        old_id,
        type(holder).__name__,
        f" of a different {algorithm.upper()} hash" if algorithm else "",
        new_id,
    )
    obj.spdxId = new_id
    return new_id
