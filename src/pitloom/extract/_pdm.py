# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""PDM-backend-backed dynamic-version resolution.

PDM-backend is PEP 621-native -- ``read_pyproject()``'s generic
``StandardMetadata.from_pyproject`` path already handles a PDM project's
``[project]`` table on its own. The one gap this module closes is PEP 621
``dynamic = ["version"]`` resolved via ``[tool.pdm.version]``, which only
pdm-backend's own resolution logic knows how to interpret (``source =
"file"``: read a version string out of a named file; ``source = "scm"``:
derive it from a Git tag).

Delegates to ``pdm.backend.hooks.version.DynamicVersionBuildHook``'s
``resolve_version_from_file``/``resolve_version_from_scm`` methods
directly -- the exact functions a real PDM build calls -- rather than
re-implementing their file/regex or SCM-tag logic by hand.

``source = "call"`` (an arbitrary ``module:attr`` callable) is
deliberately **not** resolved: unlike ``"file"``/``"scm"``, invoking it
would execute project code merely to read a version number, which
:mod:`pitloom.extract._setuptools` treats as out of scope for the same
reason (its ``setup.py`` AST-scan never executes the file either). Left
unresolved with a ``WARNING:`` instead.

**Caveat inherent to delegating to pdm-backend itself** (not specific to
this module): simply constructing ``pdm.backend.base.Builder(project_dir)``
already executes any project-declared ``[tool.pdm.build] custom-hook``
file's top-level code, the same way Pitloom's Hatchling build-hook
integration already trusts a project's own ``hatch_build.py`` -- a
project opting into a custom PDM build hook is explicitly asking for
code execution as part of its declared build-backend contract, unlike
setuptools' *implicit* ``setup.py`` fallback. Accepted as consistent with
the existing Poetry/Hatchling delegation precedent, not a new exception.

See also: :mod:`pitloom.core._models_wheel_pdm` (the sibling wheel
file-discovery module, sharing this same ``Builder``/``Context``
construction pattern); :mod:`pitloom.extract._pyproject_dynamic` (the caller).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_RESOLVABLE_SOURCES = frozenset({"file", "scm"})


def resolve_pdm_dynamic_version(
    project_dir: Path, data: dict[str, Any], dynamic_fields: list[str]
) -> tuple[str | None, str | None]:
    """Resolve PDM's dynamic ``version`` field from ``[tool.pdm.version]``.

    Returns ``(version, provenance_source)``, or ``(None, None)`` when
    ``"version"`` isn't dynamic, no ``[tool.pdm.version]`` table is
    present, the declared ``source`` is ``"call"`` or unrecognized, or
    resolution otherwise fails (logged as a ``WARNING:``, never raised --
    the caller falls back to its own generic dynamic-version heuristic).
    """
    if "version" not in dynamic_fields:
        return None, None

    version_config = data.get("tool", {}).get("pdm", {}).get("version", {})
    if not version_config:
        return None, None

    source: str | None = version_config.get("source")
    if not source:
        path = version_config.get("path", "")
        source = "file" if path and (project_dir / path).exists() else None

    if source is None:
        return None, None
    if source not in _RESOLVABLE_SOURCES:
        log.warning(
            "PDM dynamic version source %r for %s is not resolvable without "
            "executing project code -- version left unresolved",
            source,
            project_dir,
        )
        return None, None

    # pylint: disable=import-outside-toplevel
    from pdm.backend.base import Builder
    from pdm.backend.hooks.base import Context
    from pdm.backend.hooks.version import DynamicVersionBuildHook

    try:
        builder = Builder(project_dir)
        # A plain Context, never through Builder.build_context() -- that
        # helper mkdir()s dist_dir as a build-time side effect. Neither
        # resolve_version_from_file nor resolve_version_from_scm reads
        # dist_dir, so pointing it at project_dir (already on disk, never
        # written to) keeps this a pure declarative read.
        context = Context(
            build_dir=project_dir / ".pdm-build",
            dist_dir=project_dir,
            kwargs={},
            builder=builder,
        )
        options = {k: v for k, v in version_config.items() if k != "source"}
        method = getattr(DynamicVersionBuildHook(), f"resolve_version_from_{source}")
        version = str(method(context, **options))
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        log.warning(
            "PDM dynamic version resolution failed for %s: %s", project_dir, exc
        )
        return None, None

    return version, f"Source: pyproject.toml | Method: pdm_dynamic_version({source})"
