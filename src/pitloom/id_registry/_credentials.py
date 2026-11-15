# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one rule for a credential in what the ID registry stores as written:
a key, an element id and the namespace.

See also: :func:`pitloom.core.url_masking.holds_url_credentials` (what a
credential is), :mod:`pitloom.id_registry._registry` (``register()`` and
the namespace), :mod:`pitloom.id_registry._harvest._skip` (the elements a
harvest leaves out) and :mod:`pitloom.cli.id` (``id generate -e``).
"""

from __future__ import annotations

from pitloom.core.iri import (
    NAMESPACE_CREDENTIALS,
    namespace_problem,
    require_namespace_iri,
)
from pitloom.core.url_masking import holds_url_credentials
from pitloom.id_registry._types import FILE_TYPE
from pitloom.messages.url_credentials import (
    registry_key_credentials_error,
    registry_namespace_credentials_error,
)

__all__ = [
    "id_holds_credentials",
    "key_holds_credentials",
    "require_key_without_credentials",
    "require_registry_namespace",
]


def key_holds_credentials(type_name: str, name: str) -> bool:
    """Whether the registry key *name* of *type_name* holds credentials,
    read as a whole value. A file's key is a path, so only a URL counts
    (``meet 10:30@ab:c.txt`` is no scp-style address); a user name alone on
    an ``ssh`` or ``git`` URL that is an account name (``git@``) is how a
    repository is reached, so it is accepted, as in an SBOM."""
    return holds_url_credentials(name, scp=type_name != FILE_TYPE, account=True)


def id_holds_credentials(spdx_id: str) -> bool:
    """Whether the element id *spdx_id* holds credentials: any user
    information counts, as in a namespace."""
    return holds_url_credentials(spdx_id)


def require_key_without_credentials(type_name: str, name: str) -> None:
    """Raise unless the registry key *name* of *type_name* holds no
    credentials (:func:`key_holds_credentials`).

    Raises:
        pitloom.messages.CodedValueError: ``credentials-unsafe/registry``,
            the key shown masked.
    """
    if key_holds_credentials(type_name, name):
        raise registry_key_credentials_error(name)


def require_registry_namespace(namespace: str) -> str:
    """Return *namespace* when it can be a registry's namespace
    (:func:`~pitloom.core.iri.require_namespace_iri`), else raise.

    Raises:
        pitloom.messages.CodedValueError: It holds credentials
            (``credentials-unsafe/registry``), shown masked.
        ValueError: It is no namespace for another reason.
    """
    if namespace_problem(namespace) == NAMESPACE_CREDENTIALS:
        raise registry_namespace_credentials_error(namespace)
    return require_namespace_iri(namespace)
