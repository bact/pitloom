# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.extract.copyright_notices: what a copyright notice
line is, and the notices of several licence files.

See also: tests/test_copyright_surfaces.py (the main package's
``copyrightText`` on every route).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.core.project import ProjectMetadata
from pitloom.extract._license_detect import pick_license_names
from pitloom.extract.copyright_notices import (
    COPYRIGHT_NOTICE_LINE_RE,
    apply_in_package_copyright,
    copyright_from_members,
    find_copyright_notices,
    join_copyright_notices,
)
from tests._bounded import run_bounded_in_child

_C = "\u00a9"


@pytest.mark.parametrize(
    ("text", "notices"),
    [
        ("Copyright (c) 2019, Name", ["Copyright (c) 2019, Name"]),
        (f"Copyright {_C} 2019-2024 Name", [f"Copyright {_C} 2019-2024 Name"]),
        ("(C) 2019 Name", ["(C) 2019 Name"]),
        (f"{_C} 2019 Name", [f"{_C} 2019 Name"]),
        ("Copyright 2019 Name", ["Copyright 2019 Name"]),
        ("COPYRIGHT (C) 2019 Name", ["COPYRIGHT (C) 2019 Name"]),
        ("Copyright: (c) 2019 Name", ["Copyright: (c) 2019 Name"]),
        (
            "Copyright (c) Microsoft Corporation.",
            ["Copyright (c) Microsoft Corporation."],
        ),
        # the rest of the line kept as written; indentation and a BOM not
        (
            "\ufeff  Copyright (c) 2019 Name. All rights reserved.  ",
            ["Copyright (c) 2019 Name. All rights reserved."],
        ),
        # an address in angle brackets is no placeholder
        (
            "Copyright (c) 2015 A <a@example.org>",
            ["Copyright (c) 2015 A <a@example.org>"],
        ),
        (
            "Copyright (c) 2020 Jo <jo@author.dev>",
            ["Copyright (c) 2020 Jo <jo@author.dev>"],
        ),
        # a holder list: only lines that are notices themselves
        (
            "Copyright (c) 2019 A\nCopyright (c) 2020 B\n  and C\nAll rights reserved.",
            ["Copyright (c) 2019 A", "Copyright (c) 2020 B"],
        ),
        # CRLF, other lines between, an exact repeat left out
        (
            "MIT\r\n\r\nCopyright (c) 2019 A\r\nPermission ...\r\n"
            "Copyright (c) 2019 A\r\n",
            ["Copyright (c) 2019 A"],
        ),
        # licence templates
        ("Copyright (c) <year> <copyright holders>", []),
        ("   Copyright [yyyy] [name of copyright owner]", []),
        ("    Copyright (C) <year>  <name of author>", []),
        ("Copyright (C) year name of author", []),
        ("Copyright (c) {{ year }} {{ author }}", []),
        ("Copyright (c) 2019 <Your Name>", []),
        # prose about copyright
        ("the copyright holder may not", []),
        ("copyright notice and this permission notice shall be", []),
        ('COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"', []),
        ("Copyright holders may not", []),
        ("(c) You must retain, in the Source form", []),
        ("", []),
    ],
    ids=[
        "c-comma",
        "sign-range",
        "c-only",
        "sign-only",
        "word-year",
        "upper",
        "colon",
        "no-year",
        "bom-tail",
        "address",
        "address-word",
        "holder-list",
        "crlf-repeat",
        "mit-template",
        "apache-template",
        "gpl3-template",
        "gpl2-template",
        "cookiecutter",
        "your-name",
        "holder-prose",
        "notice-prose",
        "disclaimer",
        "holders-prose",
        "apache-clause",
        "empty",
    ],
)
def test_find_copyright_notices(text: str, notices: list[str]) -> None:
    assert find_copyright_notices(text) == notices


@pytest.mark.parametrize(
    ("line", "shaped"),
    [
        ("Copyright (c) <year> <copyright holders>", True),
        ("Copyright holders may not", False),
    ],
    ids=["template", "prose"],
)
def test_a_template_is_notice_shaped(line: str, shaped: bool) -> None:
    """The licence matcher strips every notice-shaped line, a template
    too (the SPDX matching guidelines omit a notice); only the copyright
    text leaves a template out."""
    assert bool(COPYRIGHT_NOTICE_LINE_RE.fullmatch(line)) is shaped


def test_join_copyright_notices_names_only_files_with_a_new_notice() -> None:
    texts = [
        ("A", "Copyright (c) 2019 A\n"),
        ("B", "no notice\n"),
        ("C", "Copyright (c) 2019 A\n"),
        ("D", "Copyright (c) 2019 A\n(c) 2020 D\n"),
    ]
    assert join_copyright_notices(texts) == (
        "Copyright (c) 2019 A\n(c) 2020 D",
        ["A", "D"],
    )
    assert join_copyright_notices([("B", "no notice")]) is None


@pytest.mark.parametrize(
    ("members", "archive", "expected"),
    [
        (
            # licence files in their priority order, other members ignored
            {
                "COPYING": b"Copyright 2020 B\n",
                "README": b"Copyright 2021 R\n",
                "LICENSE": b"Copyright (c) 2019 A\n",
                "CITATION.cff": b"license: MIT\n",
            },
            "demo-1.0.tar.gz",
            (
                "Copyright (c) 2019 A\nCopyright 2020 B",
                "Source: LICENSE, COPYING | File: demo-1.0.tar.gz"
                " | Method: copyright_notice_lines",
            ),
        ),
        # not UTF-8: read with replacement, as for licence detection
        (
            {"LICENSE": b"Copyright (c) 2019 S\xe9b\n"},
            None,
            (
                "Copyright (c) 2019 S\ufffdb",
                "Source: LICENSE | Method: copyright_notice_lines",
            ),
        ),
        ({"LICENSE": b"MIT License\n"}, None, None),
    ],
    ids=["ordered", "latin-1", "none"],
)
def test_copyright_from_members(
    members: dict[str, bytes], archive: str | None, expected: tuple[str, str] | None
) -> None:
    assert copyright_from_members(members, archive) == expected
    metadata = ProjectMetadata(name="demo")
    apply_in_package_copyright(metadata, members, archive)
    assert (
        (metadata.copyright_text, metadata.provenance["copyright_text"])
        if "copyright_text" in metadata.provenance
        else None
    ) == expected
    assert (metadata.copyright_text is None) is (expected is None)


_LICENSE_TEXTS = Path(__file__).parents[1] / "fixtures" / "license-texts"
_DULWICH = (
    Path(__file__).parents[1]
    / "fixtures/real-world-extras/setuptools/dulwich-1.2.17/COPYING"
)
_GPL2 = (_LICENSE_TEXTS / "pylint-4.1.1-LICENSE").read_text(encoding="utf-8")
_FSF3 = "Copyright (C) 2007 Free Software Foundation, Inc. <https://fsf.org/>"
_EVERYONE = " Everyone is permitted to copy and distribute verbatim copies\n"


_GFDL = (
    "        GNU Free Documentation License\n         Version 1.3, 3 November 2008"
    "\n\n\n Copyright (C) 2000, 2001, 2002, 2007, 2008 Free Software Foundation,"
    f" Inc.\n     <https://fsf.org/>\n{_EVERYONE}"
)


def _gnu(title: str, version: str, notice: str = _FSF3) -> str:
    return f"  {title}\n   Version {version}\n\n {notice}\n{_EVERYONE} of this...\n"


@pytest.mark.parametrize(
    ("text", "notices"),
    [
        (_GPL2, []),
        ((_LICENSE_TEXTS / "astroid-4.3.2-LICENSE").read_text(encoding="utf-8"), []),
        # Apache-2.0 OR GPL-2.0-or-later, both texts and no project notice
        (_DULWICH.read_text(encoding="utf-8"), []),
        (_gnu("GNU GENERAL PUBLIC LICENSE", "3, 29 June 2007"), []),
        (_gnu("GNU AFFERO GENERAL PUBLIC LICENSE", "3, 19 November 2007"), []),
        (_gnu("GNU LIBRARY GENERAL PUBLIC LICENSE", "2, June 1991"), []),
        (_gnu("GNU Library General Public License", "2, June 1991"), []),
        (_GFDL, []),
        (_gnu("## GNU GENERAL PUBLIC LICENSE", "3, x").replace("Ver", "_Ver"), []),
        (_gnu("GNU General Public License\n==========================", "3, x"), []),
        # the project's own notice, before or after the licence text
        (f"Copyright (c) 2020 Proj\n\n{_GPL2}", ["Copyright (c) 2020 Proj"]),
        (f"{_GPL2}\nCopyright (c) 2020 Proj\n", ["Copyright (c) 2020 Proj"]),
        # not a licence document's own: kept
        (_FSF3, [_FSF3]),
        (f"GNU GENERAL PUBLIC LICENSE\n\n {_FSF3}\n{_EVERYONE}", [_FSF3]),
        (_gnu("Read the GNU GENERAL PUBLIC LICENSE", "3, x"), [_FSF3]),
        (f"Copyright (c) 2020 Proj\n{_GFDL}", ["Copyright (c) 2020 Proj"]),
        (f"{_gnu('GNU GENERAL PUBLIC LICENSE', '3, x')}{_FSF3}\n", [_FSF3]),
        (
            _gnu("GNU GENERAL PUBLIC LICENSE", "3, x", "Copyright (c) 2020 Proj"),
            ["Copyright (c) 2020 Proj"],
        ),
        (_gnu("GNU GENERAL PUBLIC LICENSE", "3, x").replace("Everyone", "No"), [_FSF3]),
    ],
    ids=[
        "gpl-2.0",
        "lgpl-2.1",
        "dulwich",
        "gpl-3.0",
        "agpl-3.0",
        "lgpl-2.0",
        "lgpl-2.0-mixed-case",
        "gfdl-1.3",
        "markdown-heading",
        "rst-underline",
        "project-before",
        "project-after",
        "fsf-alone",
        "no-version-line",
        "title-in-prose",
        "project-before-gfdl",
        "after-the-block",
        "project-in-the-block",
        "no-permission-line",
    ],
)
def test_a_gnu_licence_document_s_own_notice_is_not_reported(
    text: str, notices: list[str]
) -> None:
    """The FSF's notice heading a GNU licence document is the document's,
    not the project's: left out, only between the document's title and
    ``Version`` lines and its ``Everyone is permitted`` line."""
    assert find_copyright_notices(text) == notices


@pytest.mark.parametrize("files", [1, 16], ids=["one-line", "sixteen-files"])
def test_a_crafted_notice_line_is_read_in_linear_time(files: int) -> None:
    """The placeholder pattern does not backtrack on a long line (250 KB); every
    licence-file name at the size cap reads at once."""
    line = ("Copyright 2020 [" + "name " * 50000).encode()
    names = pick_license_names(
        f"{stem}{suffix}"
        for stem in ("LICENSE", "LICENCE", "COPYING", "COPYRIGHT")
        for suffix in ("", ".txt", ".rst", ".md")
    )[:files]
    members = dict.fromkeys(names, line)
    found = run_bounded_in_child(
        "pitloom.extract.copyright_notices:copyright_from_members", members
    )
    assert found is not None
    assert found[0] == line.decode().strip()
