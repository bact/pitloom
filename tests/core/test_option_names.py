# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An option as each surface spells it in an ``option-no-effect`` line,
and the reasons that name one, written when said.

See also: tests/messages/test_surface.py (the surface itself) and
tests/core/test_inert_options.py (which options a target cannot use).
"""

from __future__ import annotations

import contextvars
import re
import string

import pytest

from pitloom.core import build_options, inert_options
from pitloom.core.internal_error import InternalError
from pitloom.core.option_names import (
    PARAM_TO_FLAG,
    REASON_NAMES,
    named_reason,
    option_name,
)
from pitloom.messages import SURFACE_CLI, SURFACE_HOOK, SURFACE_LIBRARY, advice_surface


def _on_the_hook(param: str) -> str:
    """*param* as the hook names it."""
    with advice_surface(SURFACE_HOOK):
        return option_name(param)


@pytest.mark.parametrize(
    ("param", "cli", "library"),
    [
        ("use_lockfile", "--use-lockfile/--no-use-lockfile", "use_lockfile"),
        ("trust_model_files", "--trust-model-files", "trust_model_files"),
        ("allow_build", "--allow-build", "BuildOptions.allow"),
        ("no_build_isolation", "--no-build-isolation", "BuildOptions.no_isolation"),
        ("build_timeout", "--build-timeout", "BuildOptions.timeout"),
        ("sbom", "--sbom", "sbom_path"),
        ("enrich_project_dir", "--project-dir", "project_target"),
        ("project_dir", "--project-dir", "project_dir"),
    ],
    ids=[
        "lockfile",
        "trust",
        "allow",
        "isolation",
        "timeout",
        "sbom",
        "enrich-dir",
        "project-dir",
    ],
)
def test_an_option_is_named_as_the_surface_spells_it(
    param: str, cli: str, library: str
) -> None:
    with advice_surface(SURFACE_CLI):
        assert option_name(param) == cli
    with advice_surface(SURFACE_LIBRARY):
        assert option_name(param) == library
    assert option_name(param) == library  # the default surface
    # The hook settles configured keys only: a parameter there is a
    # programming error the suite refuses (strict); a build says the
    # library's name rather than fail.
    with pytest.raises(InternalError, match="cannot reach"):
        _on_the_hook(param)
    assert contextvars.Context().run(_on_the_hook, param) == library


@pytest.mark.parametrize("surface", [SURFACE_CLI, SURFACE_LIBRARY, SURFACE_HOOK])
def test_a_configured_setting_is_named_by_its_key_on_every_surface(
    surface: str,
) -> None:
    with advice_surface(surface):
        assert (
            option_name("describe_relationship", configured=True)
            == "tool.pitloom.describe-relationship"
        )
        assert (
            option_name("update_id_registry", configured=True)
            == "tool.pitloom.update-id-registry"
        )


def test_an_unknown_option_is_a_programming_error() -> None:
    with pytest.raises(InternalError, match="no option name"):
        option_name("no_such_option")
    with pytest.raises(InternalError):
        named_reason("without {no_such_option}")


@pytest.mark.parametrize(
    ("reason", "cli", "library"),
    [
        (
            build_options.EXTERNAL_SBOM_REASON,
            "for an externally-supplied --sbom (",
            "for an externally-supplied sbom_path (",
        ),
        (
            inert_options.INERT[inert_options.EMBED_PROJECT]["trust_model_files"],
            "with --project-dir (AI models are read from the project, not the wheel)",
            "with project_dir (AI models are read from the project, not the wheel)",
        ),
        (
            inert_options.INERT[inert_options.ENRICH_STANDALONE]["use_lockfile"],
            "without --project-dir ",
            "without project_target ",
        ),
    ],
    ids=["sbom", "embed-project", "enrich-standalone"],
)
def test_a_reason_names_its_option_when_said(
    reason: str, cli: str, library: str
) -> None:
    with advice_surface(SURFACE_CLI):
        assert named_reason(reason).startswith(cli)
    assert named_reason(reason).startswith(library)


def _reasons() -> list[str]:
    """Every reason a no-effect line can end in: the inert table's and the
    build options'."""
    rows = [reason for row in inert_options.INERT.values() for reason in row.values()]
    build = [
        value
        for name, value in vars(build_options).items()
        if name.endswith("_REASON") or name == "_WITHOUT_ALLOW"
    ]
    return sorted({*rows, *build})


def test_every_reason_names_only_known_options() -> None:
    """A brace in a reason is a placeholder of an option, never text: the
    reason is formatted when said."""
    reasons = _reasons()
    assert len(reasons) > 20
    for reason in reasons:
        fields = [f for _, f, _, _ in string.Formatter().parse(reason) if f is not None]
        assert all(f in PARAM_TO_FLAG or f in REASON_NAMES for f in fields), reason
        for surface in (SURFACE_CLI, SURFACE_LIBRARY):
            with advice_surface(surface):
                written = named_reason(reason)
            assert "{" not in written and "}" not in written, reason


def test_no_option_name_is_kept_as_a_flag_in_a_library_reason() -> None:
    """Every reason a library call can be given names no flag."""
    flag = re.compile(r"(?:^|[\s(])--[a-z]")
    for reason in _reasons():
        assert not flag.search(named_reason(reason)), reason
