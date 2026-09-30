# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Which options a target cannot act on, and the one place that says so.

Every SBOM surface accepts more options than every target can use: the CLI
parent parser offers the same flags to each subcommand, and
:func:`pitloom.assemble.generate` accepts the union of its delegates'
parameters. An option given for a target that cannot use it gets one
``WARNING: Options: <subject>: <flag> has no effect <reason>``, never a
silent drop (AGENTS.md "no silent deviations").

:data:`INERT` is keyed by *target kind*, not by command, so ``loom wheel``,
``loom generate x.whl`` and ``generate("x.whl")`` share one row and one
wording. :func:`forward_options` enforces "exactly once" structurally: the
layer that drops a parameter warns about it, and a parameter its callee
accepts is left for the callee to settle.

No leading underscore: imported by :mod:`pitloom.assemble`,
:mod:`pitloom.embed` and :mod:`pitloom.cli`.

See also: :mod:`pitloom.core.no_effect` (the message shape) and
:mod:`pitloom.core.build_options` (the same idea for the build flags).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from typing import Any

from pitloom.core.build_options import EXTERNAL_SBOM_REASON, NO_PROJECT_DIR_REASON
from pitloom.core.no_effect import INERT_LOG_PREFIX, warn_no_effect

# Target kinds. One kind per distinct set of options a target can act on.
PROJECT = "project"
SDIST = "sdist"
WHEEL = "wheel"
ENV = "env"
MODEL_FILE = "model_file"
HF = "hf"
ENRICH = "enrich"
ENRICH_STANDALONE = "enrich_standalone"
EMBED_PROJECT = "embed_project"
EMBED_STANDALONE = "embed_standalone"
EMBED_SBOM = "embed_sbom"

#: Library parameter name -> the CLI spelling a warning names. A
#: ``BooleanOptionalAction`` flag names both spellings, since either one
#: may be the one given.
PARAM_TO_FLAG: dict[str, str] = {
    "pretty": "--pretty/--no-pretty",
    "describe_relationship": "--describe-relationship/--no-describe-relationship",
    "enrich": "--enrich/--no-enrich",
    "extract_file_header": "--extract-file-header/--no-extract-file-header",
    "content_type": "--content-type/--no-content-type",
    "scan_model_usage": "--scan-model-usage/--no-scan-model-usage",
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

_NO_FILE_SCAN = (
    "for this target (file headers and content types are read from a "
    "project directory only)"
)
_SDIST_FILE_SCAN = (
    "for an sdist archive target (files come from the archive's own listing)"
)
_SDIST_NO_MODELS = (
    "for an sdist archive target (AI models are scanned in a project directory only)"
)
_WHEEL_NO_MODEL_SCAN = (
    "for a wheel target (AI models inside a wheel are not scanned yet)"
)
_ENV_NO_MODEL_SCAN = (
    "for an installed environment (AI model files are not scanned here yet)"
)
_MODEL_NO_USAGE = "for a model target (there are no Python files here to reference it)"
_FRAGMENT_NO_USAGE = (
    "for an enrichment fragment (scan usage when generating the base SBOM instead)"
)
_NO_MODELS = "for this target (it has no AI models to enrich)"
_NO_LOCKFILE = (
    "for this target (no lock-file concept applies to env/wheel/"
    "model-file/Hugging-Face targets)"
)
_SDIST_NO_LOCKFILE = (
    "for an sdist archive target (no lock/pin cascade support for archives yet)"
)
_FRAGMENT_NO_LOCKFILE = "without --project-dir (no base document identity is computed)"
_NO_HARVEST = "for this target (it never writes ids back to a registry)"
_MODEL_NO_DEPENDENCIES = (
    "for a model file (no files or dependencies here for a content-type "
    "method to steer)"
)
_MODEL_NO_NETWORK = "for a local model file (nothing here uses the network)"
_HF_NO_REGISTRY = "for a Hugging Face model (its ids are not looked up in a registry)"
_HF_NO_LOCAL_ENRICH = (
    "for a Hugging Face model (its model card is already parsed natively)"
)
_FRAGMENT_NO_DESCRIBE = (
    "for an enrichment fragment (describe relationships when generating "
    "the base SBOM instead)"
)
_FRAGMENT_NO_SOURCE_METADATA = (
    "for an enrichment fragment (it carries no source-metadata annotation)"
)
_EMBED_CANONICAL = (
    "for a wheel-embedded SBOM (always written as RFC 8785 canonical JSON)"
)
_EMBED_NO_DESCRIBE = (
    "for a wheel-embedded SBOM (relationship descriptions are not embedded)"
)

_FILE_SCAN = ("extract_file_header", "content_type")
#: Options no wheel-embedded SBOM can use, however it is embedded
#: (``embed-wheel`` or ``wheel --embed``).
_EMBED_COMMON: dict[str, str] = {
    "pretty": _EMBED_CANONICAL,
    "describe_relationship": _EMBED_NO_DESCRIBE,
    "update_id_registry": _NO_HARVEST,
}
_MODEL_FILE_ROW: dict[str, str] = {
    **dict.fromkeys(_FILE_SCAN, _NO_FILE_SCAN),
    "content_type_method": _MODEL_NO_DEPENDENCIES,
    "scan_model_usage": _MODEL_NO_USAGE,
    "update_id_registry": _NO_HARVEST,
}

_ENRICH_ROW: dict[str, str] = {
    **dict.fromkeys(_FILE_SCAN, _NO_FILE_SCAN),
    "describe_relationship": _FRAGMENT_NO_DESCRIBE,
    "content_type_method": _MODEL_NO_DEPENDENCIES,
    "max_source_metadata_bytes": _FRAGMENT_NO_SOURCE_METADATA,
    "scan_model_usage": _FRAGMENT_NO_USAGE,
    "update_id_registry": _NO_HARVEST,
}

#: Target kind -> {parameter: reason it has no effect there}.
INERT: dict[str, dict[str, str]] = {
    PROJECT: {},
    SDIST: {
        **dict.fromkeys(_FILE_SCAN, _SDIST_FILE_SCAN),
        "enrich": _SDIST_NO_MODELS,
        "scan_model_usage": _SDIST_NO_MODELS,
        "use_lockfile": _SDIST_NO_LOCKFILE,
    },
    WHEEL: {
        **dict.fromkeys(_FILE_SCAN, _NO_FILE_SCAN),
        "enrich": _NO_MODELS,
        "scan_model_usage": _WHEEL_NO_MODEL_SCAN,
        "use_lockfile": _NO_LOCKFILE,
    },
    ENV: {
        **dict.fromkeys(_FILE_SCAN, _NO_FILE_SCAN),
        "enrich": _NO_MODELS,
        "scan_model_usage": _ENV_NO_MODEL_SCAN,
        "use_lockfile": _NO_LOCKFILE,
    },
    MODEL_FILE: {
        **_MODEL_FILE_ROW,
        "offline": _MODEL_NO_NETWORK,
        "use_lockfile": _NO_LOCKFILE,
    },
    HF: {
        **_MODEL_FILE_ROW,
        "enrich": _HF_NO_LOCAL_ENRICH,
        "id_registry": _HF_NO_REGISTRY,
        "use_lockfile": _NO_LOCKFILE,
    },
    ENRICH: _ENRICH_ROW,
    ENRICH_STANDALONE: {**_ENRICH_ROW, "use_lockfile": _FRAGMENT_NO_LOCKFILE},
    EMBED_PROJECT: dict(_EMBED_COMMON),
    EMBED_STANDALONE: {
        **_EMBED_COMMON,
        **dict.fromkeys(
            (*_FILE_SCAN, "enrich", "scan_model_usage"), NO_PROJECT_DIR_REASON
        ),
    },
    EMBED_SBOM: {
        **dict.fromkeys(
            (
                *_FILE_SCAN,
                "enrich",
                "scan_model_usage",
                "content_type_method",
                "max_source_metadata_bytes",
                "offline",
                "id_registry",
                "creation_metadata",
                "pitloom_config",
                "project_dir",
            ),
            EXTERNAL_SBOM_REASON,
        ),
        # The given file is embedded as is: nothing -- not even formatting
        # -- is regenerated, so the embed-only reasons would be wrong.
        **dict.fromkeys(_EMBED_COMMON, EXTERNAL_SBOM_REASON),
    },
}


#: The parameters of :data:`_EMBED_COMMON`, for a caller that embeds by
#: another route than :func:`pitloom.embed.embed_wheel_sbom`.
EMBEDDED_SBOM_PARAMS = tuple(_EMBED_COMMON)


def settle_inert(
    kind: str, subject: object, given: Mapping[str, object]
) -> frozenset[str]:
    """Warn once per parameter in *given* that *kind* cannot act on, and
    return their names so the caller drops them.

    A value of ``None`` means "not given" and is skipped; ``False`` and
    ``0`` are explicit choices and count (AGENTS.md's ``None`` vs empty
    rule). Within one call, warnings follow :data:`PARAM_TO_FLAG` order, so
    the output does not depend on the caller's mapping order; options
    settled by different layers (see :func:`forward_options`) warn in
    layer order.

    Raises:
        KeyError: *kind* is not a key of :data:`INERT`.
    """
    row = INERT[kind]
    inert = [
        param
        for param in PARAM_TO_FLAG
        if param in row and given.get(param) is not None
    ]
    for param in inert:
        warn_no_effect(INERT_LOG_PREFIX, subject, (PARAM_TO_FLAG[param],), row[param])
    return frozenset(inert)


def forward_options(
    kind: str,
    subject: object,
    callee: Callable[..., Any],
    options: Mapping[str, Any],
) -> dict[str, Any]:
    """Split *options* into what *callee* accepts, returned for forwarding,
    and what it does not, settled here with :func:`settle_inert`.

    Which parameters *callee* accepts is read from its signature, so the
    layer that drops an option is always the one that warns about it, and
    one the callee accepts is left for the callee's own settling: every
    ignored option is reported exactly once however many layers it
    crosses.

    Raises:
        ValueError: *callee* does not accept a given option that
            :data:`INERT` does not declare inert for *kind* -- it would be
            dropped without a word, so this is a wiring bug, not user
            error. An option left ``None`` was not given and is dropped
            silently.
    """
    parameters = inspect.signature(callee).parameters
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
        return dict(options)
    forwarded = {name: value for name, value in options.items() if name in parameters}
    dropped = {name: value for name, value in options.items() if name not in parameters}
    undeclared = sorted(
        name
        for name, value in dropped.items()
        if value is not None and name not in INERT[kind]
    )
    if undeclared:
        raise ValueError(
            f"{getattr(callee, '__name__', callee)}() does not accept "
            f"{', '.join(undeclared)}, which INERT[{kind!r}] does not declare"
        )
    settle_inert(kind, subject, dropped)
    return forwarded


__all__ = [
    "EMBED_PROJECT",
    "EMBED_SBOM",
    "EMBED_STANDALONE",
    "EMBEDDED_SBOM_PARAMS",
    "ENRICH",
    "ENRICH_STANDALONE",
    "ENV",
    "HF",
    "INERT",
    "MODEL_FILE",
    "PARAM_TO_FLAG",
    "PROJECT",
    "SDIST",
    "WHEEL",
    "forward_options",
    "settle_inert",
]
