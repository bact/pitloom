# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Package URLs (PURL) for AI models and datasets.

``pkg:huggingface`` names a Hugging Face model repository at a revision;
``pkg:generic`` names anything else by a name plus a ``checksum`` or a
``download_url`` qualifier. The PyPI form is
:func:`pitloom.core.models.build_pypi_purl`.

See also: https://github.com/package-url/purl-spec (type definitions).
"""

from __future__ import annotations

import re
from urllib.parse import quote

__all__ = ["build_generic_purl", "build_huggingface_purl"]

_GIT_SHA = re.compile(r"[0-9a-fA-F]{40}")


def _encode(text: str, safe: str = "") -> str:
    return quote(text, safe=safe)


def build_huggingface_purl(model_id: str, revision: str | None) -> str | None:
    """Return ``pkg:huggingface/<owner>/<name>[@<revision>]``, or ``None``.

    The type needs an owner, so a legacy id without one (``gpt2``) gets no
    PURL. *revision* is kept, lowercased, only when it is a Git commit hash.
    """
    parts = model_id.split("/")
    if len(parts) != 2 or not all(parts):
        return None
    base = f"pkg:huggingface/{_encode(parts[0])}/{_encode(parts[1])}"
    if revision and _GIT_SHA.fullmatch(revision):
        return f"{base}@{revision.lower()}"
    return base


def build_generic_purl(
    name: str,
    *,
    version: str | None = None,
    checksum: str | None = None,
    download_url: str | None = None,
) -> str:
    """Return ``pkg:generic/<name>[@<version>][?checksum=..&download_url=..]``.

    *checksum* is ``<algorithm>:<hex>``. Qualifiers are in key order, as the
    PURL specification canonicalises them.
    """
    purl = f"pkg:generic/{_encode(name)}"
    if version:
        purl += f"@{_encode(version)}"
    qualifiers = [
        f"{key}={_encode(value, safe=safe)}"
        for key, value, safe in (
            ("checksum", checksum, ":"),
            ("download_url", download_url, "/:"),
        )
        if value
    ]
    return purl + ("?" + "&".join(qualifiers) if qualifiers else "")
