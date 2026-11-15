# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``credentials-unsafe``: a URL in what the SBOM would state holds user
information or a secret query value, so it is removed (``WARNING``).
``credentials-unsafe/registry``: an ID registry key holds one,
and the registry would store it, so it is refused (``ERROR``).

See also: :mod:`pitloom.messages.url_credentials` (the helpers every site
says them through) and :func:`pitloom.core.url_masking.strip_url_secrets`
(what is removed).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import ASK_FIRST, Line, Message

_SINCE: Final = "0.24.1"
_HOLDS: Final = "holds user information or a secret query value"

#: A URL of the project's own data, in the SBOM.
STRIPPED_LINE: Final = Line(
    level="WARNING",
    template=f"URL=%(url)s: {_HOLDS}; removed from the SBOM",
)
#: A Git URL's credentials hold a line break, so they cannot be handed to
#: ``git`` and the fetch is anonymous.
GIT_LINE: Final = Line(
    level="WARNING",
    template="URL=%(url)s: credentials holding a line break are not sent to git",
)
#: A registry key the registry would store as written.
KEY_LINE: Final = Line(
    level="ERROR",
    template=f"URL=%(url)s: {_HOLDS}; an ID registry key is stored as "
    "written, so it is refused",
)

#: A key an import or harvest would store as written.
KEY_SKIPPED_LINE: Final = Line(
    level="WARNING",
    template=f"URL=%(url)s: {_HOLDS}; an ID registry key is stored as "
    "written, so it is skipped",
)

URL_CREDENTIALS: Final = Message(
    code="credentials-unsafe",
    condition="unsafe",
    lines=(STRIPPED_LINE, GIT_LINE),
    summary="A URL a project declares (a dependency's direct URL, a project "
    "URL, a model card's link) holds a user name or password, or a query "
    "parameter named like a secret (token, key, signature). An SBOM can be "
    "published, so it must not carry either.",
    did="Removed the user information and each such parameter from the URL "
    "in the SBOM, its provenance and its comments, and went on; said once "
    "per URL, shown masked. A parameter named code, session, ticket, sid or "
    "otp, and a user name alone on an ssh or git URL (git@), are kept as "
    "written. A Git URL whose user name or password holds a "
    "line break is fetched without credentials.",
    effect="thinner",
    actor="user",
    advice="Tell the user which URL, as the line shows it, and that the SBOM "
    "states it without the credential. A credential in a project's files "
    "is also in its history: they should consider it exposed and rotate it, "
    "and check a code or session parameter the SBOM still states. "
    f"Do not edit their files; {ASK_FIRST}",
    subject_key="URL",
    since=_SINCE,
)

URL_CREDENTIALS_REGISTRY: Final = Message(
    code="credentials-unsafe/registry",
    condition="unsafe",
    lines=(KEY_LINE, KEY_SKIPPED_LINE),
    summary="A key given to the ID registry (an external reference URL) "
    "holds a user name or password, or a query parameter named like a "
    "secret. The registry file stores a key as written.",
    did="Stored nothing: refused the key (error), or left the SBOM element "
    "out of the registry and went on (warning).",
    effect="not-written",
    actor="user",
    advice="Tell the user which value, as the line shows it, and that it "
    "must be given without the credential. They correct it and run again; "
    "a credential they typed is exposed in their shell history. Do not edit "
    f"their registry file; {ASK_FIRST}",
    subject_key="URL",
    since=_SINCE,
)

ENTRIES: Final = (URL_CREDENTIALS, URL_CREDENTIALS_REGISTRY)
