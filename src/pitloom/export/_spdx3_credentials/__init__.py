# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The check of an SBOM whose URL-typed fields hold a credential: the one
check every surface's SBOM passes (the exporter's last step, and
``embed-wheel --sbom`` on the file it embeds). A value is never rewritten:
in the ``warn`` mode (the default) it is stated as written with a
``WARNING:``; in the ``refuse`` mode the SBOM is refused unless the run
accepts the value by its fingerprint.

Only the fields of :data:`URL_FIELDS`, every string of a JSON statement
Pitloom writes (an annotation whose ``schema`` is under
:data:`PITLOOM_SCHEMA_PREFIX`: its field provenance, the artifact metadata
it copies from a model, a conflict's candidates, an enrichment's changes)
and every segment of a ``Metadata provenance:`` comment line are read, each
as a whole value (a string that is not a URL holds no finding); a name, a
description, any other comment line or other prose is not (a README example
must not block a build; finding secrets in prose is a secret scanner's
job).

Split into :mod:`._fields` (what is read), :mod:`._find` (the walk) and
:mod:`._check` (the check); this package re-exports their public names.

See also: :mod:`pitloom.export.spdx3_json` (the exporter),
:func:`pitloom.core.url_masking.find_url_credentials` (the detector),
:class:`pitloom.core.credential_policy.CredentialPolicy` (what a run
accepts) and :mod:`pitloom.messages.url_credentials` (the lines said).
"""

from __future__ import annotations

from pitloom.export._spdx3_credentials._check import check_graph_credentials
from pitloom.export._spdx3_credentials._fields import (
    NOT_READ,
    PITLOOM_SCHEMA_PREFIX,
    PROVENANCE_COMMENT_PREFIX,
    REFERENCE_FIELDS,
    URL_FIELDS,
)
from pitloom.export._spdx3_credentials._find import (
    GraphFinding,
    find_graph_credentials,
)

__all__ = [
    "NOT_READ",
    "PITLOOM_SCHEMA_PREFIX",
    "PROVENANCE_COMMENT_PREFIX",
    "REFERENCE_FIELDS",
    "URL_FIELDS",
    "GraphFinding",
    "check_graph_credentials",
    "find_graph_credentials",
]
