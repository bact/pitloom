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

    Uses flit-core's own ``read_flit_config()`` + ``Module`` +
    ``get_docstring_and_version_via_ast()`` -- an AST-only scan for a
    ``__version__`` assignment and the module's docstring, matching
    flit-core's exact resolution rules for the literal-value case.

    Deliberately does **not** call flit-core's own ``make_metadata()``/
    ``get_info_from_module()``: those fall back to *importing* --
    executing -- the target module whenever the AST scan can't find a
    literal ``__version__``/docstring (e.g. a version computed by a
    function call). That fallback is out of scope here for the same
    reason :mod:`pitloom.extract._setuptools` never executes
    ``setup.py`` -- matching the same no-execution guarantee
    :mod:`pitloom.core._models_wheel_flit`'s ``discover()`` already
    implements for the identical data. A dynamic field that isn't
    AST-resolvable is left unresolved (falls through to the caller's
    generic heuristic) rather than resolved by running project code.

    Returns a ``{field: value}`` mapping for whichever of ``"version"``/
    ``"description"`` were both requested (in *dynamic_fields*) and
    successfully resolved via the AST scan -- an empty dict on any
    failure (not a Flit project, malformed config, module not found, or
    an AST-unresolvable dynamic field), logged as a ``WARNING:`` rather
    than raised, since the caller falls back to its own generic
    dynamic-version heuristic either way.
    """
    wanted = [f for f in ("version", "description") if f in dynamic_fields]
    if not wanted:
        return {}

    # pylint: disable=import-outside-toplevel
    from flit_core.common import Module, get_docstring_and_version_via_ast
    from flit_core.config import read_flit_config
    from flit_core.versionno import normalise_version

    try:
        loaded_cfg = read_flit_config(pyproject_path)
        module = Module(loaded_cfg.module, pyproject_path.parent)
        docstring, version = get_docstring_and_version_via_ast(module)
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        log.warning(
            "Flit dynamic metadata resolution failed for %s: %s", pyproject_path, exc
        )
        return {}

    result: dict[str, str] = {}
    if "version" in wanted and version:
        result["version"] = normalise_version(version)
    if "description" in wanted and docstring and docstring.strip():
        result["description"] = docstring.lstrip().splitlines()[0]
    return result
