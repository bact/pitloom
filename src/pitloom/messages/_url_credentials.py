# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``credentials-unsafe``: a URL in what the SBOM would state holds user
information or a secret query value, so it is removed, or a value that only
sometimes is one, which is kept (``WARNING``).
``credentials-unsafe/registry``: an ID registry key or namespace holds one,
and the registry would store it, so it is refused (``ERROR``) or the element
skipped, or the entry of a registry file dropped (``WARNING``).
``credentials-unsafe/id-collision``: two element ids differ only by
credentials (``ERROR``).

See also: :mod:`pitloom.messages.url_credentials` (the helpers every site
says them through), :mod:`pitloom.messages._url_credentials_git` (the
family's Git variants) and :func:`pitloom.core.url_masking.strip_url_secrets`
(what is removed).
"""

from __future__ import annotations

from typing import Final

from pitloom.core.iri import NAMESPACE_CREDENTIALS
from pitloom.messages._types import ASK_FIRST, Line, Message

_SINCE: Final = "0.25.0"
#: The phrase of each line of the SBOM strip.
_HOLDS: Final = (
    "holds user information or a secret query value, or a query nested too "
    "deeply to read"
)
#: The phrase of each refusal of a stored value, a namespace refusal's too
#: (what :func:`pitloom.core.url_masking.find_url_credentials` refuses).
_REFUSED: Final = NAMESPACE_CREDENTIALS
_KEPT: Final = "a code, session, ticket, sid or otp parameter or an ssh user name"

#: A URL of the project's own data, in the SBOM.
STRIPPED_LINE: Final = Line(
    level="WARNING",
    template=f"URL=%(url)s: {_HOLDS}; removed from the SBOM",
)
#: Same, and a value that only sometimes is a credential stays.
STRIPPED_KEPT_LINE: Final = Line(
    level="WARNING",
    template=f"URL=%(url)s: {_HOLDS}; removed from the SBOM, except {_KEPT}, "
    "which it keeps as written",
)
#: A URL whose only possible credential is one the SBOM keeps.
KEPT_LINE: Final = Line(
    level="WARNING",
    template=f"URL=%(url)s: holds {_KEPT} that the SBOM keeps as written",
)
#: A registry key the registry would store as written.
KEY_LINE: Final = Line(
    level="ERROR",
    template=f"URL=%(url)s: {_REFUSED}; an ID registry key is stored as "
    "written, so it is refused",
)
#: A document namespace the registry would store as written.
NAMESPACE_CREDENTIALS_LINE: Final = Line(
    level="ERROR",
    template=f"URL=%(url)s: {_REFUSED}; an ID registry namespace is stored as "
    "written, so it is refused",
)
#: An element whose key or id an import or harvest would store as written.
KEY_SKIPPED_LINE: Final = Line(
    level="WARNING",
    template=f"URL=%(url)s: {_REFUSED}; the ID registry stores an element's key "
    "and id as written, so the element is skipped",
)
#: An entry of a registry file whose key or id holds one.
ENTRY_DROPPED_LINE: Final = Line(
    level="WARNING",
    template=f"URL=%(url)s: {_REFUSED}; the ID registry entry is dropped and "
    "the next save writes the file without it",
)
#: Two element ids differ only by credentials.
ID_COLLISION_LINE: Final = Line(
    level="ERROR",
    template="URL=%(url)s: another element has this id once its credentials "
    "are removed; no SBOM is written",
)

CREDENTIALS_UNSAFE: Final = Message(
    code="credentials-unsafe",
    condition="unsafe",
    lines=(STRIPPED_LINE, STRIPPED_KEPT_LINE, KEPT_LINE),
    summary="A URL a project declares (a dependency's direct URL, a project "
    "URL, a model card's link) holds a user name or password, or a query "
    "parameter named like a secret (token, key, signature), or a query with "
    "so many nested ? that it cannot be read safely. An SBOM can be "
    "published, so it must not carry any.",
    did="Removed the user information and each such parameter from the URL "
    "in the SBOM, its provenance and its comments, and went on; said once "
    "per URL, shown masked. A parameter named code, session, ticket, sid or "
    "otp, and a user name alone on an ssh or git URL (git@), are kept as "
    "written, and said too (the log line may still mask the value). A "
    "parameter whose value holds more than 16 ? is removed as a "
    "precaution, not necessarily a credential.",
    effect="thinner",
    actor="user",
    advice="Tell the user which URL, as the line shows it, and that the SBOM "
    "states it without the credential, or keeps the value the line names. "
    "A credential in a project's files is also in its history: they should "
    "consider it exposed and rotate it, and check that a kept code, session "
    "or ssh user name is no credential. "
    f"Do not edit their files; {ASK_FIRST}",
    subject_key="URL",
    since=_SINCE,
)

CREDENTIALS_UNSAFE_REGISTRY: Final = Message(
    code="credentials-unsafe/registry",
    condition="unsafe",
    lines=(
        KEY_LINE,
        NAMESPACE_CREDENTIALS_LINE,
        KEY_SKIPPED_LINE,
        ENTRY_DROPPED_LINE,
    ),
    summary="A key or namespace given to the ID registry (an external "
    "reference URL), or the key or id of an SBOM element it would record, "
    "holds a user name or password, a query parameter named like a secret "
    "or an access token (also percent-encoded in a PURL qualifier). The "
    "registry file stores a key, an id and its namespace as written.",
    did="Refused the key or namespace and stored nothing (error), or left the "
    "SBOM element out of the registry and wrote the rest (warning). An entry "
    "of a registry file holding one is dropped when the file is loaded, "
    "said once per value, and a save writes the file without it (warning).",
    effect="thinner",
    actor="user",
    advice="Tell the user which value, as the line shows it. For an error, "
    "they give the value without the credential and run again; a credential "
    "typed on a command line is exposed in their shell history. For a "
    "warning, the value came from an SBOM ('loom id import'), the run's own "
    "data or their registry file: that element has no stable id (a new one "
    "is minted next run), and a credential in a shared SBOM, a project's "
    "files or a committed registry file is exposed, in its history too. "
    "Either way they should rotate it. Do "
    f"not edit their registry file; {ASK_FIRST}",
    subject_key="URL",
    since=_SINCE,
)

CREDENTIALS_UNSAFE_ID_COLLISION: Final = Message(
    code="credentials-unsafe/id-collision",
    condition="unsafe",
    lines=(ID_COLLISION_LINE,),
    summary="Two element ids of the SBOM (of a merged fragment) differ only by "
    "user information or a secret query value, so they would be the same id "
    "once the credentials are removed.",
    did="Wrote no SBOM.",
    effect="not-written",
    actor="user",
    advice="Tell the user which id, as the line shows it, and that two "
    "elements carry it with different credentials. They give the elements "
    "ids without credentials, in the fragment, and run again. Do not edit "
    f"their fragment; {ASK_FIRST}",
    subject_key="URL",
    since=_SINCE,
)

ENTRIES: Final = (
    CREDENTIALS_UNSAFE,
    CREDENTIALS_UNSAFE_REGISTRY,
    CREDENTIALS_UNSAFE_ID_COLLISION,
)
