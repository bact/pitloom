# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Flit-core-backed dynamic-metadata resolution.

Flit-core is PEP 621-native -- ``read_pyproject()``'s generic
``StandardMetadata.from_pyproject`` path already handles a Flit project's
``[project]`` table on its own. The one gap this module closes is PEP 621
``dynamic = ["version", "description"]``: Flit resolves those from the
target module itself (a ``__version__ = "..."`` assignment and the
module's docstring), which only flit-core's own resolution logic knows
how to find -- the same reason :mod:`pitloom.extract._poetry` exists
alongside the generic path, just for a narrower field set.

See also: :mod:`pitloom.core._models_wheel_flit` (the sibling wheel
file-discovery module, sharing the same ``flit_core.config.read_flit_config``
+ ``flit_core.common.Module`` lookup); :mod:`pitloom.extract._pyproject_dynamic`
(the caller, ``prepare_dynamic_version``).
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


def resolve_flit_dynamic_metadata(
    pyproject_path: Path, dynamic_fields: list[str]
) -> dict[str, str]:
    """Resolve Flit's dynamic ``version``/``description`` fields.

    Delegates entirely to flit-core's own ``read_flit_config()`` +
    ``Module`` + ``make_metadata()`` -- the same functions flit-core's
    real build uses to resolve these fields (AST-parses the target
    module for a ``__version__`` assignment and its docstring, falling
    back to importing the module only if the AST scan comes up empty,
    exactly like a real Flit build would). Never hand-rolled here, to
    avoid drifting from flit-core's actual resolution rules.

    Returns a ``{field: value}`` mapping for whichever of ``"version"``/
    ``"description"`` were both requested (in *dynamic_fields*) and
    successfully resolved -- an empty dict on any failure (not a Flit
    project, malformed config, module not found), logged as a
    ``WARNING:`` rather than raised, since the caller falls back to its
    own generic dynamic-version heuristic either way.
    """
    wanted = [f for f in ("version", "description") if f in dynamic_fields]
    if not wanted:
        return {}

    # pylint: disable=import-outside-toplevel
    from flit_core.common import Module, make_metadata
    from flit_core.config import read_flit_config

    try:
        loaded_cfg = read_flit_config(pyproject_path)
        module = Module(loaded_cfg.module, pyproject_path.parent)
        metadata = make_metadata(module, loaded_cfg)
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        log.warning(
            "Flit dynamic metadata resolution failed for %s: %s", pyproject_path, exc
        )
        return {}

    result: dict[str, str] = {}
    if "version" in wanted and metadata.version:
        result["version"] = str(metadata.version)
    if "description" in wanted and metadata.summary:
        result["description"] = str(metadata.summary)
    return result
