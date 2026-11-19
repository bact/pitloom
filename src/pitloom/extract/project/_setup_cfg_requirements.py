# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The requirement lists of a ``setup.cfg``: ``install_requires`` and
``[options.extras_require]``, as setuptools reads them.

See also: :mod:`pitloom.extract.project.setuptools_cfg` (the reader) and
:mod:`pitloom.extract.project._requirements_files` (``file:`` requirements).
"""

from __future__ import annotations

import configparser
from pathlib import Path

from pitloom.core.provenance import provenance_segment, provenance_source
from pitloom.extract.project._requirements_files import (
    ListedFiles,
    setup_cfg_file_names,
    setup_cfg_requirement_lines,
)
from pitloom.extract.project._setuptools_options import SetupOption


def cfg_requirements(value: str, project_dir: Path) -> list[str] | ListedFiles:
    """A requirements value (``install_requires``, an extra) as setuptools
    reads it (:func:`~pitloom.extract.project._requirements_files.\
setup_cfg_requirement_lines`), or the files its ``file:`` directive lists
    in *project_dir*, read when the options are merged."""
    names = setup_cfg_file_names(value)
    if names is None:
        return setup_cfg_requirement_lines(value)
    return ListedFiles(project_dir, names)


def cfg_source(field: str) -> str:
    return provenance_segment(provenance_source("setup.cfg"), "Field", field)


EXTRAS_SECTION = "options.extras_require"


def extras_option(
    cfg: configparser.ConfigParser, text: str, project_dir: Path
) -> SetupOption | None:
    """``[options.extras_require]`` of the ``setup.cfg`` *text*, read as *cfg*
    read it: extra (or ``extra:marker``) -> requirements. The keys are
    spelt as written, since ``configparser`` lowercases them and a marker's
    value is case-sensitive; the values are *cfg*'s, so a ``%(key)s`` finds
    its key whatever its case, as it does for setuptools. ``None`` without
    the section."""
    cased = configparser.ConfigParser(interpolation=None)  # spelling only
    cased.optionxform = str  # type: ignore[assignment,method-assign]
    cased.read_string(text, source="setup.cfg")
    if not cased.has_section(EXTRAS_SECTION):
        return None
    extras = {
        key: cfg_requirements(_extra_value(cfg, key), project_dir)
        for key in cased.options(EXTRAS_SECTION)  # a [DEFAULT] key is one too
    }
    return SetupOption(extras, cfg_source(EXTRAS_SECTION))


def _extra_value(cfg: configparser.ConfigParser, key: str) -> str:
    """The interpolated value of the extra *key* (as written). A bad ``%`` in
    it is reported under that spelling, not under *cfg*'s lowercased key."""
    try:
        return cfg.get(EXTRAS_SECTION, key)
    except configparser.InterpolationError as exc:
        exc.option = key
        raise
