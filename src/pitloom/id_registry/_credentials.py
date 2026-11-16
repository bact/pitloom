# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one rule for a credential in what the ID registry stores as written:
a key, an element id and the namespace. A key given follows the run's
``url-credentials`` mode (refused in ``refuse``, stored with a ``WARNING:``
in ``warn``); a namespace is refused in either mode.

See also: :func:`pitloom.core.url_masking.holds_url_credentials` (what a
credential is), :mod:`pitloom.id_registry._registry` (``register()`` and
the namespace), :mod:`pitloom.id_registry._harvest._skip` (the elements a
harvest leaves out) and :mod:`pitloom.cli.id` (``id generate -e``).
"""

from __future__ import annotations

import logging

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
    warn_registry_key_kept,
)

__all__ = [
    "check_key_credentials",
    "id_holds_credentials",
    "key_holds_credentials",
    "require_key_without_credentials",
    "require_registry_namespace",
]


def key_holds_credentials(type_name: str, name: str) -> bool:
    """Whether the registry key *name* of *type_name* holds credentials,
    read as a whole value, and a URL or an access token anywhere in it (a
    key is an identifier the registry stores, never prose). A file's key is
    a path, so a value that is an scp-style address is not one
    (``meet-10:30@ab:c.txt``); a user name alone on an ``ssh`` or ``git``
    URL that is an account name (``git@``) is how a repository is reached,
    so it is accepted, as in an SBOM."""
    return holds_url_credentials(
        name, scp=type_name != FILE_TYPE, account=True, embedded=True
    )


def id_holds_credentials(spdx_id: str) -> bool:
    """Whether the element id *spdx_id* holds credentials, a URL anywhere
    in it included. An ``ssh`` or ``git`` account name alone (``git@``) is
    none, as in a key and in an SBOM's id (a model named
    ``ssh://git@github.com/o/m`` mints one); a namespace still refuses it."""
    return holds_url_credentials(spdx_id, account=True, embedded=True)


log = logging.getLogger("pitloom.id_registry")


def check_key_credentials(type_name: str, name: str, *, refuse: bool) -> None:
    """When the registry key *name* of *type_name* holds credentials
    (:func:`key_holds_credentials`): raise with *refuse* (the ``refuse``
    mode), else one ``WARNING:`` that it is stored as written.

    Raises:
        pitloom.messages.CodedValueError: ``credentials-unsafe/registry``,
            the key shown masked, with *refuse* only.
    """
    if not key_holds_credentials(type_name, name):
        return
    if refuse:
        raise registry_key_credentials_error(name)
    warn_registry_key_kept(log, name)


def require_key_without_credentials(type_name: str, name: str) -> None:
    """Raise unless the registry key *name* of *type_name* holds no
    credentials: :func:`check_key_credentials` in the ``refuse`` mode.

    Raises:
        pitloom.messages.CodedValueError: ``credentials-unsafe/registry``,
            the key shown masked.
    """
    check_key_credentials(type_name, name, refuse=True)


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
