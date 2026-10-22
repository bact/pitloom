# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Validation of the ``[tool.hatch.build.hooks.pitloom]`` table.

See also: :mod:`pitloom.plugins.hatch` (the build hook that calls it).
"""

from __future__ import annotations

from typing import Any

#: Keys that moved to [tool.pitloom] / [tool.pitloom.creation] -- one source
#: of truth shared with the CLI -- mapped to their new location.
_MOVED_KEYS = {
    "sbom-basename": "[tool.pitloom] sbom-basename",
    "fragments": "[tool.pitloom.fragment] files",
    "creator-name": "[[tool.pitloom.creator]] (key: name)",
    "creator-email": "[[tool.pitloom.creator]] (key: email)",
    "creator-type": "[[tool.pitloom.creator]] (key: type)",
    "creation-tool": "[[tool.pitloom.creation-tool]] (key: name)",
}


#: The keys Hatchling itself reads from every build hook's table
#: (``hatchling.builders.config``), so the hook leaves them alone.
_HATCHLING_KEYS = frozenset(
    {
        "dependencies",
        "enable-by-default",
        "require-runtime-dependencies",
        "require-runtime-features",
    }
)


def validate_config(config: dict[str, Any]) -> None:
    """Validate ``[tool.hatch.build.hooks.pitloom]`` configuration values.

    This section controls only whether the hook runs (``enabled``) and holds
    Hatchling's own hook keys (:data:`_HATCHLING_KEYS`); all other settings
    live in ``[tool.pitloom]`` / ``[tool.pitloom.creation]``.

    Raises:
        ValueError: If ``enabled`` has an unexpected type, a moved key is
            still present here, or an unknown key is present.
    """
    section = "[tool.hatch.build.hooks.pitloom]"

    enabled = config.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError(
            f"{section} 'enabled' must be a boolean (true/false), "
            f"got {type(enabled).__name__!r}."
        )

    for key, new_location in _MOVED_KEYS.items():
        if key in config:
            raise ValueError(
                f"{section} {key!r} is no longer supported here; "
                f"set it under {new_location} instead."
            )

    unknown = set(config) - {"enabled", *_MOVED_KEYS, *_HATCHLING_KEYS}
    if unknown:
        raise ValueError(
            f"{section} unknown key(s): {sorted(unknown)!r}. "
            "Only 'enabled' and Hatchling's own hook keys "
            f"({', '.join(sorted(_HATCHLING_KEYS))}) are supported; all "
            "other SBOM settings live in [tool.pitloom] / "
            "[tool.pitloom.creation]."
        )
