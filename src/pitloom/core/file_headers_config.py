# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Configuration dataclass for per-file SPDX header metadata extraction."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileHeadersConfig:
    """Configuration settings for ``[tool.pitloom.file-headers]``.

    Attributes:
        enabled: Whether to scan each source file's leading comment header
            for SPDX-File* tags (FileCopyrightText, FileContributor,
            FileType) and a per-file SPDX-License-Identifier. On by
            default -- this is pure regex over bytes already read for the
            SHA-256 hash, the same cost class as work Pitloom already does
            unconditionally elsewhere (e.g. LICENSE/CITATION.cff/
            codemeta.json scanning in ``pitloom.extract._license``); the
            "off until proven" precedent ``[tool.pitloom.enrich]`` has
            doesn't apply here, since it was about immature
            external-content parsing, not raw cost.
        detect_content_type: Whether to also detect each file's real IANA
            media type via ``magika``/``mimetypes`` (see
            ``pitloom.extract._file_headers.guess_content_type``). Off by
            default -- unlike ``enabled``, this has a real measured
            per-file cost (``magika`` inference, ~5ms/file), so it keeps
            the same "opt-in, real cost" treatment ``[tool.pitloom.enrich]``
            has. Independent of ``enabled`` -- never used to derive
            ``software_primaryPurpose`` from ``SPDX-FileType``, or vice
            versa; see ``working-docs/design/file-headers.md``.
    """

    enabled: bool = True
    detect_content_type: bool = False
