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
import tempfile
import uuid
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
    from pdm.backend.hooks.base import Context
    from pdm.backend.hooks.version import DynamicVersionBuildHook
    from pdm.backend.wheel import WheelBuilder

    try:
        # WheelBuilder, not the plain Builder base: Builder never sets
        # its own `target` class attribute (no default at all), and
        # resolve_version_from_scm()'s write path (see options-stripping
        # below) reads context.target -- accessing it on a plain Builder
        # raises AttributeError, silently losing the resolved version
        # for any project using `source = "scm"` together with
        # `write_to` (a common, documented PDM idiom for auto-embedding
        # a _version.py). WheelBuilder sets target = "wheel", same as
        # the sibling _models_wheel_pdm.py discovery module already
        # uses, so this attribute is always defined.
        builder = WheelBuilder(project_dir)
        # A plain Context, never through Builder.build_context() -- that
        # helper mkdir()s dist_dir as a build-time side effect. Neither
        # resolve_version_from_file nor resolve_version_from_scm reads
        # dist_dir, so pointing it at project_dir (already on disk, never
        # written to) keeps this a pure declarative read.
        #
        # build_dir, unlike dist_dir, is never read here either (only
        # written to by resolve_version_from_scm's write_to option,
        # which is stripped below) -- pointed at a path guaranteed never
        # to exist on disk, not project_dir / ".pdm-build" itself, so a
        # future pdm-backend change that starts *reading* build_dir
        # (e.g. caching) can't pick up stale content from a real build
        # the same way the sibling _models_wheel_pdm.py discovery
        # module's build_dir is already guarded against.
        context = Context(
            build_dir=Path(tempfile.gettempdir())
            / f"pitloom-unused-{uuid.uuid4().hex}",
            dist_dir=project_dir,
            kwargs={},
            builder=builder,
        )
        options = {k: v for k, v in version_config.items() if k != "source"}
        if source == "scm":
            # resolve_version_from_scm() unconditionally writes the
            # resolved version to context.build_dir when write_to is
            # set -- a real disk write this pure metadata read must
            # never trigger (the same side effect
            # _models_wheel_pdm.py's discover() avoids by skipping
            # initialize() entirely). Stripping write_to/write_template
            # here still resolves the version correctly; it only
            # suppresses the file write pdm-backend does as a side
            # effect of resolving it.
            options.pop("write_to", None)
            options.pop("write_template", None)
        method = getattr(DynamicVersionBuildHook(), f"resolve_version_from_{source}")
        version = str(method(context, **options))
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        log.warning(
            "PDM dynamic version resolution failed for %s: %s", project_dir, exc
        )
        return None, None

    return version, f"Source: pyproject.toml | Method: pdm_dynamic_version({source})"
