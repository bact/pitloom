# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The declared CLI matrix: every subcommand, how to give it a target,
and what each of its options is exercised by (a group, one-factor
variants, or a reasoned exclusion).

``M/completeness`` compares this plan with the real parser, so a new
subcommand or option that is not classified here fails the run instead
of going unchecked. See also: ``_matrix.py`` (runs the plan).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from _fixtures import Fixtures

from pitloom.core.inert_options import (
    EMBED_PROJECT,
    ENRICH,
    ENV,
    INERT,
    MODEL_FILE,
    PARAM_TO_FLAG,
    PROJECT,
    WHEEL,
)

Args = Callable[[Fixtures, Path], list[str]]


def _fixed(*args: str) -> Args:
    return lambda _fx, _cell: list(args)


@dataclass(frozen=True)
class Command:
    """A (sub)command and how a matrix cell runs it.

    *artefact* is what a cell compares between variants: ``output`` (the
    ``-o`` file), ``wheel-sbom`` (the SBOM embedded in the target wheel),
    ``registry`` (``reg.json``) or ``stdout``.
    """

    name: str
    target: Args
    artefact: str
    network: bool = False
    # Without -o: False means the command must refuse (exit 1, ERROR:).
    default_output: bool = True


COMMANDS: list[Command] = [
    # generate's target-detection dispatch has no default file name.
    Command(
        "generate",
        lambda fx, c: [str(fx.stage("project", c))],
        "output",
        default_output=False,
    ),
    Command("project", lambda fx, c: [str(fx.stage("project", c))], "output"),
    # The wheel holds a GGUF, which a wheel scan lists without metadata unless
    # --trust-wheel-model.
    Command("wheel", lambda fx, c: [str(fx.stage("gated-wheel", c))], "output"),
    Command(
        "embed-wheel",
        lambda fx, c: [
            str(fx.stage("wheel", c)),
            "--project-dir",
            str(fx.stage("project", c)),
        ],
        "wheel-sbom",
    ),
    Command(
        "verify-wheel", lambda fx, c: [str(fx.stage("embedded-wheel", c))], "stdout"
    ),
    Command(
        "validate-wheel",
        lambda fx, c: [str(fx.stage("embedded-wheel", c))],
        "stdout",
        network=True,
    ),
    Command("model", lambda fx, c: [str(fx.stage("model", c))], "output"),
    Command(
        "enrich",
        lambda fx, c: [
            str(fx.stage("model", c)),
            "--project-dir",
            str(fx.stage("project", c)),
        ],
        "output",
    ),
    Command("env", _fixed(), "output"),
    Command("merge", lambda fx, c: [str(fx.stage("fragments", c))], "output"),
    # Fetches the SPDX context from spdx.org.
    Command(
        "fragment validate",
        lambda fx, c: [str(fx.stage("sbom", c))],
        "stdout",
        network=True,
    ),
    Command(
        "fragment list",
        lambda fx, c: ["--project-dir", str(fx.stage("project", c))],
        "stdout",
    ),
    Command(
        "id generate",
        lambda fx, c: [
            str(fx.stage("project", c)),
            "--project-dir",
            str(c / "demo-project"),
            "-o",
            str(c / "reg.json"),
        ],
        "registry",
    ),
    Command(
        "id import",
        lambda fx, c: [str(fx.stage("sbom", c)), "-o", str(c / "reg.json")],
        "registry",
    ),
]

# Expectations for a one-factor variant, compared with the command's
# plain run: "changes" (artefact differs), "same" (identical), "exit:N",
# "any" (only the universal invariants; the report shows the effect),
# "contains:TEXT" (TEXT appears in the artefact), "writes:FILE" (FILE is
# written in the cell directory) or "warns:FLAG" (the target cannot use
# the option: exactly one `WARNING: Options:` line names FLAG and the
# artefact is identical). Every non-"warns" variant must also leave stderr
# free of `WARNING: Options:` lines.


@dataclass(frozen=True)
class Variant:
    """One way to give an option, and what it must do."""

    label: str
    args: Args
    expect: str


def _v(label: str, expect: str, *args: str) -> Variant:
    return Variant(label, _fixed(*args), expect)


_BUILD_FLAGS = (
    "covered by tests/test_build_flag_warnings.py (every flag combination, "
    "every surface, real argv) and checks B1-B7 (real process)"
)
_TARGET = "part of the command's target, given in every cell"
_CONFIG_COMMENT = "matrix config comment"


def _write_config(cell: Path) -> str:
    """Write a ``--config`` file into *cell*; return its path."""
    path = cell / "matrix-config.toml"
    path.write_text(
        f'[tool.pitloom]\ncreation-comment = "{_CONFIG_COMMENT}"\n', encoding="utf-8"
    )
    return str(path)


# Option -> handled by a group ("group:NAME"), excluded ("exclude:REASON"),
# or a list of one-factor variants. Keyed by the option's first spelling
# as the parser lists it; a (command, option) key overrides for one command.
PLAN: dict[str | tuple[str, str], str | list[Variant]] = {
    "--debug": "group:debug",
    "-V": [_v("--version", "exit:0", "--version")],
    "-o": "group:output",
    "--pretty": "group:output",
    "--creation-datetime": "group:date",
    "--offline": "group:offline",
    "--allow-build": f"exclude:{_BUILD_FLAGS}",
    "--no-build-isolation": f"exclude:{_BUILD_FLAGS}",
    "--build-timeout": f"exclude:{_BUILD_FLAGS}",
    "--update-id-registry": "exclude:side effect on the registry file: sequence S4",
    "--embed": "exclude:side effect on the wheel: sequences S2 and S3",
    "--project-dir": f"exclude:{_TARGET}",
    ("fragment list", "--project-dir"): f"exclude:{_TARGET}",
    ("id generate", "-o"): f"exclude:{_TARGET} (-o is --id-registry here)",
    # embed-wheel's artefact is the embedded SBOM; -o writes a copy.
    ("embed-wheel", "-o"): [_v("-o file", "writes:copy.json", "-o", "copy.json")],
    ("embed-wheel", "--pretty"): [
        _v("--pretty", "writes:copy.json", "-o", "copy.json", "--pretty"),
        _v("--no-pretty", "writes:copy.json", "-o", "copy.json", "--no-pretty"),
    ],
    ("id import", "-o"): f"exclude:{_TARGET} (-o is --id-registry here)",
    # --content-type-method is live on a wheel/env (it steers the authors
    # fetch) while --content-type is not, so give it alone there.
    **{
        (command, "--content-type-method"): [
            _v("extension", "any", "--content-type-method", "extension"),
            _v("invalid", "exit:2", "--content-type-method", "bogus"),
        ]
        for command in ("wheel", "env")
    },
    # Live on a model file, but a model-only SBOM has no Relationship
    # element for it to describe.
    ("model", "--describe-relationship"): [
        _v("--describe-relationship", "same", "--describe-relationship"),
        _v("--no-describe-relationship", "same", "--no-describe-relationship"),
    ],
    # embed-wheel prints no verbose details, and says so.
    ("embed-wheel", "-v"): [_v("-v", "warns:-v", "-v")],
    "<target>": f"exclude:{_TARGET}",
    "<project_dir>": f"exclude:{_TARGET}",
    "<wheel_files>": f"exclude:{_TARGET}",
    "<fragments_dir>": f"exclude:{_TARGET}",
    "<paths>": f"exclude:{_TARGET}",
    "<sbom>": f"exclude:{_TARGET}",
    "--describe-relationship": [
        _v("--describe-relationship", "changes", "--describe-relationship"),
        _v("--no-describe-relationship", "same", "--no-describe-relationship"),
    ],
    "--enrich": [
        _v("--enrich", "any", "--enrich"),
        _v("--no-enrich", "same", "--no-enrich"),
    ],
    "--extract-file-header": [
        _v("--extract-file-header", "same", "--extract-file-header"),
        _v("--no-extract-file-header", "changes", "--no-extract-file-header"),
    ],
    "--content-type": [
        _v("--content-type", "changes", "--content-type"),
        _v("--no-content-type", "same", "--no-content-type"),
    ],
    "--scan-model-usage": [
        _v("--scan-model-usage", "changes", "--scan-model-usage"),
        _v("--no-scan-model-usage", "same", "--no-scan-model-usage"),
    ],
    # Live on `wheel`, whose fixture wheel holds a GGUF; inert on every other
    # cell (models read from a project directory, or no wheel at all).
    "--trust-wheel-model": [
        _v("--trust-wheel-model", "changes", "--trust-wheel-model")
    ],
    "--content-type-method": [
        _v(
            "extension",
            "changes",
            "--content-type",
            "--content-type-method",
            "extension",
        ),
        _v("invalid", "exit:2", "--content-type-method", "bogus"),
    ],
    "--max-source-metadata-bytes": [
        _v("1", "any", "--max-source-metadata-bytes", "1"),
        _v("-1", "exit:2", "--max-source-metadata-bytes", "-1"),
    ],
    "-v": [_v("-v", "same", "-v")],
    "--id-registry": [
        # r.json is never created for this cell -- a declared but missing
        # registry file is a hard ERROR on every surface (see
        # working-docs/implementation/manual-cli-checks.md check 14).
        Variant(
            "missing registry",
            lambda _fx, c: ["--id-registry", str(c / "r.json")],
            "exit:1",
        ),
    ],
    "--creator-name": [
        _v("name", "contains:Jane Matrix", "--creator-name", "Jane Matrix")
    ],
    "--creator-type": [
        _v(
            "organization",
            "contains:Organization",
            "--creator-name",
            "Org Matrix",
            "--creator-type",
            "organization",
        ),
        _v("invalid", "exit:2", "--creator-type", "bogus"),
    ],
    "--creator-email": [
        _v(
            "email",
            "contains:jane@example.org",
            "--creator-name",
            "Jane Matrix",
            "--creator-email",
            "jane@example.org",
        )
    ],
    "--creation-tool": [
        _v("name", "contains:MatrixTool", "--creation-tool", "MatrixTool")
    ],
    "--no-creation-tool": [_v("--no-creation-tool", "changes", "--no-creation-tool")],
    "--creation-comment": [
        _v("text", "contains:matrix comment", "--creation-comment", "matrix comment")
    ],
    "--use-lockfile": [
        _v("--use-lockfile", "same", "--use-lockfile"),
        _v("--no-use-lockfile", "same", "--no-use-lockfile"),
    ],
    "--sbom": [
        Variant(
            "external SBOM",
            lambda fx, c: ["--sbom", str(fx.stage("sbom", c))],
            "changes",
        ),
    ],
    "--sbom-basename": [_v("custom", "any", "--sbom-basename", "custom")],
    "--allow-mismatch": [_v("--allow-mismatch", "same", "--allow-mismatch")],
    "--verify": [_v("--verify", "same", "--verify")],
    "--validate": [Variant("--validate", _fixed("--validate"), "same")],
    "--sbom-filename": [_v("missing", "exit:1", "--sbom-filename", "absent.json")],
    "--fail-on-mismatch": [_v("--fail-on-mismatch", "same", "--fail-on-mismatch")],
    "--no-merge": [_v("--no-merge", "same", "--no-merge")],
    "-e": [_v("entity", "changes", "-e", "matrix-entity")],
    "--config": [
        Variant(
            "file",
            lambda _fx, c: ["--config", _write_config(c)],
            f"contains:{_CONFIG_COMMENT}",
        ),
        _v("missing", "exit:1", "--config", "absent.toml"),
    ],
}

# The target kind each command's matrix cell runs (see COMMANDS' targets).
# generate/project cells run a project directory.
_CELL_KINDS = {
    "generate": PROJECT,
    "project": PROJECT,
    "wheel": WHEEL,
    "env": ENV,
    "model": MODEL_FILE,
    "enrich": ENRICH,
    "embed-wheel": EMBED_PROJECT,
}


def _inert_overrides() -> dict[tuple[str, str], list[Variant]]:
    """Per-command variants for every option the cell's target cannot use,
    derived from :data:`pitloom.core.inert_options.INERT` so the matrix and
    the library cannot disagree on which options warn. Each keeps the
    option's own variants but expects ``warns:`` instead of an effect; an
    ``exit:N`` variant (an argparse refusal) is unchanged. An option planned
    as a group or an exclusion keeps that plan."""
    overrides: dict[tuple[str, str], list[Variant]] = {}
    for command, kind in _CELL_KINDS.items():
        for param in INERT[kind]:
            flag = PARAM_TO_FLAG[param].split("/")[0]
            base = PLAN.get((command, flag), PLAN.get(flag))
            if not isinstance(base, list):
                continue
            overrides[(command, flag)] = [
                variant
                if variant.expect.startswith("exit:")
                else Variant(variant.label, variant.args, f"warns:{flag}")
                for variant in base
            ]
    return overrides


PLAN.update(_inert_overrides())

# Variants that need the network (run only with --network).
NETWORK_VARIANTS = {("embed-wheel", "--validate")}


def plan_for(command: str, option: str) -> str | list[Variant] | None:
    """The plan entry for *option* on *command*, or ``None`` if unplanned."""
    if (command, option) in PLAN:
        return PLAN[(command, option)]
    return PLAN.get(option)
