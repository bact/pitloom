# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Validation of the ``[tool.hatch.build.hooks.pitloom]`` table.

See also: :mod:`pitloom.plugins.hatch` (the build hook that calls it).
"""

from __future__ import annotations

from typing import Any

from pitloom.messages.config import (
    ConfigPlace,
    config_invalid,
    config_moved,
    hook_unknown_keys,
)

_HOOK = ConfigPlace("tool.hatch.build.hooks.pitloom")

#: Keys that moved to [tool.pitloom] / [tool.pitloom.creation], mapped to a
#: destination of :data:`~pitloom.messages.config.DESTINATIONS`. A second
#: table beside the CLI's (:mod:`pitloom.core._config_legacy`); a drift test
#: holds both to that list.
_MOVED_KEYS = {
    "sbom-basename": "[tool.pitloom] sbom-basename",
    "fragments": "[tool.pitloom.fragment] files",
    "creator-name": "[[tool.pitloom.creator]] name",
    "creator-email": "[[tool.pitloom.creator]] email",
    "creator-type": "[[tool.pitloom.creator]] type",
    "creation-tool": "[[tool.pitloom.creation-tool]] name",
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
    live in ``[tool.pitloom]`` / ``[tool.pitloom.creation]``. The table may
    come from ``hatch.toml``, so no error names a file.

    Raises:
        pitloom.messages.config.ConfigError: ``config-invalid`` if
            ``enabled`` has an unexpected type, ``config-moved`` if a moved
            key is still present here, ``config-unknown-key`` if an unknown
            key is present.
    """
    enabled = config.get("enabled", True)
    if not isinstance(enabled, bool):
        raise config_invalid(_HOOK.at("enabled"), "boolean", got=enabled)

    for key, new_location in _MOVED_KEYS.items():
        if key in config:
            raise config_moved(_HOOK.at(key), new_location)

    unknown = set(config) - {"enabled", *_MOVED_KEYS, *_HATCHLING_KEYS}
    if unknown:
        raise hook_unknown_keys(_HOOK, sorted(unknown))
