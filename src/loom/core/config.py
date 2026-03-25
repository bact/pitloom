# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Loom tool configuration read from ``[tool.loom]`` in ``pyproject.toml``."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LoomConfig:
    """Settings from the ``[tool.loom]`` section of ``pyproject.toml``.

    All fields have safe defaults so that a project without a ``[tool.loom]``
    section works out of the box.  Adding new ``[tool.loom]`` options in
    future versions only requires adding a new field here with a default value.

    Attributes:
        pretty: When ``True``, the serialised SBOM JSON is indented with
            2 spaces for human readability.  Defaults to ``False`` (compact,
            machine-optimised output).
        fragments: List of paths to pre-generated SPDX 3 JSON-LD fragment
            files, relative to the project directory.  These are merged into
            the final SBOM document at generation time.
    """

    pretty: bool = False
    fragments: list[str] = field(default_factory=list)


__all__ = ["LoomConfig"]
