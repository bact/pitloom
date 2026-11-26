# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An option as the surface that runs spells it, for the
``option-no-effect`` lines: a command-line flag (``--use-lockfile``), a
library parameter (``use_lockfile``), or a ``[tool.pitloom]`` setting
read from configuration by its TOML key on any surface
(``tool.pitloom.describe-relationship``).

The surface is :func:`pitloom.messages.current_surface`; a reason that
names an option holds a ``{name}`` placeholder of :data:`REASON_NAMES`,
written when the warning is said (:func:`named_reason`), never at import.

No leading underscore: imported by :mod:`pitloom.core.inert_options`,
:mod:`pitloom.core.build_options`, :mod:`pitloom.core.no_effect` and
:mod:`pitloom.assemble`.

See also: :mod:`pitloom.core.no_effect` (the line) and
:mod:`pitloom.core.inert_options` (which options a target cannot use).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from pitloom.core.internal_error import InternalError
from pitloom.messages import SURFACE_CLI, SURFACE_LIBRARY, current_surface
from pitloom.messages.build import (
    ALLOW_BUILD_NAMES,
    BUILD_TIMEOUT_NAMES,
    NO_BUILD_ISOLATION_NAMES,
)

#: Library parameter name -> the CLI spelling a warning names. A
#: ``BooleanOptionalAction`` flag names both spellings, since either one
#: may be the one given.
PARAM_TO_FLAG: Final[Mapping[str, str]] = MappingProxyType(
    {
        "pretty": "--pretty/--no-pretty",
        "describe_relationship": "--describe-relationship/--no-describe-relationship",
        "enrich": "--enrich/--no-enrich",
        "extract_file_header": "--extract-file-header/--no-extract-file-header",
        "content_type": "--content-type/--no-content-type",
        "scan_model_usage": "--scan-model-usage/--no-scan-model-usage",
        "trust_model_files": "--trust-model-files",
        "max_model_extract_bytes": "--max-model-extract-bytes",
        "max_download_bytes": "--max-download-bytes",
        "content_type_method": "--content-type-method",
        "max_source_metadata_bytes": "--max-source-metadata-bytes",
        "offline": "--offline/--no-offline",
        "use_lockfile": "--use-lockfile/--no-use-lockfile",
        "id_registry": "--id-registry",
        "update_id_registry": "--update-id-registry/--no-update-id-registry",
        "creation_metadata": "--creator-*/--creation-*",
        "pitloom_config": "--config",
        "project_dir": "--project-dir",
    }
)

#: An option a reason or a build line names that is no parameter of
#: :data:`PARAM_TO_FLAG`: its placeholder -> (its flag, its library name).
REASON_NAMES: Final[Mapping[str, tuple[str, str]]] = MappingProxyType(
    {
        **{
            name: (names[SURFACE_CLI], names[SURFACE_LIBRARY])
            for name, names in (
                ("allow_build", ALLOW_BUILD_NAMES),
                ("no_build_isolation", NO_BUILD_ISOLATION_NAMES),
                ("build_timeout", BUILD_TIMEOUT_NAMES),
            )
        },
        "sbom": ("--sbom", "sbom_path"),
        # enrich_model() names the project it enriches project_target.
        "enrich_project_dir": ("--project-dir", "project_target"),
    }
)


def option_name(param: str, *, configured: bool = False) -> str:
    """*param* (a key of :data:`PARAM_TO_FLAG` or :data:`REASON_NAMES`) as
    the surface that runs spells it: its flag on the command line, else its
    library name. *configured*: a setting read from ``[tool.pitloom]``,
    named by its dotted TOML key on every surface
    (``tool.pitloom.describe-relationship``), one token as the line's
    ``option`` field takes it.

    Raises:
        pitloom.core.internal_error.InternalError: *param* is in neither
            table.
    """
    if param in REASON_NAMES:
        flag, library = REASON_NAMES[param]
    elif param in PARAM_TO_FLAG:
        flag, library = PARAM_TO_FLAG[param], param
    else:
        raise InternalError(f"no option name for {param!r}")
    if configured:
        return f"tool.pitloom.{param.replace('_', '-')}"
    return flag if current_surface() == SURFACE_CLI else library


class _Names(dict[str, str]):
    """The option names a reason's placeholders stand for, looked up as
    they are written."""

    def __missing__(self, key: str) -> str:
        return option_name(key)


def named_reason(reason: str) -> str:
    """*reason* with each ``{name}`` placeholder written as the surface that
    runs spells that option (:func:`option_name`). A reason has no other
    brace.

    Raises:
        pitloom.core.internal_error.InternalError: A placeholder names no
            option.
    """
    return reason.format_map(_Names())


__all__ = ["PARAM_TO_FLAG", "REASON_NAMES", "named_reason", "option_name"]
