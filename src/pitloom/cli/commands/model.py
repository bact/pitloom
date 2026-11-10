# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``model`` subcommand: an AI model SBOM from a local file or folder, a
Git URL or a Hugging Face repository."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from pitloom.assemble import (
    generate_model_sbom,
)
from pitloom.cli.commands._remote import run_remote
from pitloom.cli.commands.utils import (
    _print_sbom_output_path,
    cli_error_handler,
    existing_model_path,
)
from pitloom.cli.kv_output import log_verbose
from pitloom.cli.options import (
    _resolve_hf_output_path,
    _resolve_model_output_path,
    add_offline_argument,
)
from pitloom.cli.options_config import explicit_config_and_options
from pitloom.core.build_options import BuildOptions
from pitloom.core.inert_options import GIT_MODEL, HF, MODEL_FILE, forward_options
from pitloom.core.quote_source import quote_source
from pitloom.core.url_masking import sanitize_url
from pitloom.extract.model_target import MODEL, model_path_of
from pitloom.extract.remote import (
    is_git_url,
    is_huggingface_source,
    is_unfetchable_remote,
    log_hf_url_rewrite,
    parse_hf_model_id,
)
from pitloom.extract.remote.pypi_url import is_pypi_url
from pitloom.logging_config import print_error
from pitloom.messages import (
    INPUT_NOT_FOUND,
    MODEL_FILE_NOT_FOUND_LINE,
    MODEL_URL_LINE,
    PYPI_URL_UNUSABLE,
)


def _write_model_sbom(
    args: argparse.Namespace,
    source: Path | str,
    output_path: Path,
    *,
    kind: str,
    subject: str,
    shown: str | None = None,
) -> None:
    """Write the SBOM of the model *source* to *output_path*, with
    ``--config`` and every option resolved against it; the options *kind*
    cannot use are said once against *subject*."""
    pitloom_config, options = explicit_config_and_options(args)
    if kind == GIT_MODEL:
        # The fetch consumed it: a file of the clone is read with no network.
        options.pop("offline", None)
        # Consumed by the fetch too (run_remote): it lifts the clone's gate,
        # and the cap bounds the checkout.
        options.pop("trust_model_files", None)
        options.pop("max_download_bytes", None)
    generate_model_sbom(
        source,
        output_path=output_path,
        pitloom_config=pitloom_config,
        shown=shown,
        **forward_options(kind, subject, generate_model_sbom, options),
    )


def generate_model_from_args(
    args: argparse.Namespace,
    model_path: Path,
    *,
    kind: str,
    subject: str,
    shown: str | None = None,
) -> Path:
    """Generate the SBOM of the local model file *model_path* from parsed
    arguments; return the output path it was written to: ``-o``, else the
    file's name plus ``.spdx3.json`` in the current directory (never next to
    the file, which may be in a temporary clone).

    Shared by ``loom model`` on a file, a folder and a Git URL (*kind*
    :data:`~pitloom.core.inert_options.GIT_MODEL`, whose ``--offline`` the
    fetch consumed) and ``loom generate`` on a Git URL. The options *kind*
    cannot use are said once against *subject*; messages name the file
    *shown* (default: *model_path*).
    """
    output_path = _resolve_model_output_path(args.output, model_path.resolve())
    if args.verbose:
        named = model_path.resolve() if shown is None else shown
        log_verbose(MODEL_FILE=named, OUTPUT_PATH=output_path)
    _write_model_sbom(
        args, model_path, output_path, kind=kind, subject=subject, shown=shown
    )
    return output_path


def _run_hf_model(args: argparse.Namespace, target: str) -> int:
    """``loom model`` on a Hugging Face URL or model id."""
    model_id = parse_hf_model_id(target)
    if model_id is None:
        print_error(
            "not a valid Hugging Face URL or model ID: "
            f"{quote_source(sanitize_url(target))}"
        )
        return 1
    log_hf_url_rewrite(target, model_id)
    output_path = _resolve_hf_output_path(args.output, model_id)
    if args.verbose:
        log_verbose(HF_MODEL=model_id, OUTPUT_PATH=output_path)
    # Same subject generate_model_sbom() settles its own options under.
    _write_model_sbom(args, model_id, output_path, kind=HF, subject=model_id)
    _print_sbom_output_path(output_path)
    return 0


@cli_error_handler("model command failed")
def _run_model_command(args: argparse.Namespace) -> int:
    """Generate an AI Model SBOM from a local file or folder, a Git URL or a
    Hugging Face repository."""
    target: str = args.target
    if is_pypi_url(target):
        print_error(
            MODEL_URL_LINE.render({"url": sanitize_url(target.strip())}),
            code=PYPI_URL_UNUSABLE.code,
        )
        return 1
    if is_git_url(target) and not Path(target).exists():
        # loom model has no --allow-build: no build flag to settle.
        return run_remote(args, target.strip(), MODEL, BuildOptions())
    if is_huggingface_source(target):
        return _run_hf_model(args, target)
    if is_unfetchable_remote(target):
        return run_remote(args, target.strip(), MODEL, BuildOptions())
    # The path as given goes to the generator, so its log lines name the
    # file as the user wrote it.
    opened_path = existing_model_path(Path(target))
    if opened_path is None:
        # A URL that is no source we read (user information in a Hugging
        # Face one) is named as given, cleaned, not as a path under the cwd.
        shown = sanitize_url(target) if "://" in target else Path(target).resolve()
        print_error(
            MODEL_FILE_NOT_FOUND_LINE.render({"path": shown}),
            code=INPUT_NOT_FOUND.code,
        )
        return 1
    # A folder: its one model file, which names the output.
    model_path = model_path_of(opened_path, subject=target)
    _print_sbom_output_path(
        generate_model_from_args(
            args, model_path, kind=MODEL_FILE, subject=str(model_path)
        )
    )
    return 0


def add_parser(subparsers: Any, parent_parser: argparse.ArgumentParser) -> None:
    """Add the ``model`` subcommand."""
    # AI model asset: loom model <SOURCE> [--offline]
    model_parser = subparsers.add_parser(
        "model",
        parents=[parent_parser],
        help="Generate an AI Model SBOM (AIBOM) from a local file or folder, a "
        "Git URL or a HF repo.",
    )
    model_parser.add_argument(
        "target",
        type=str,
        help="A local AI model file (recognised by its content), a folder "
        "holding one model file, the http(s) URL of a model file or folder "
        "in a Git repository (fetched shallowly; fastText, GGUF, HDF5, ONNX "
        "and PyTorch files, whose reader a hostile file could crash or hang, "
        "are listed without metadata), or a Hugging Face URL / model ID.",
    )
    add_offline_argument(
        model_parser,
        "; effect depends on the resolved target -- "
        "HF URL/ID or Git URL: error, no fetch attempted (no local fallback "
        "exists). "
        "local model file or folder: no-op (no network path exists).",
    )
    model_parser.set_defaults(func=_run_model_command)
