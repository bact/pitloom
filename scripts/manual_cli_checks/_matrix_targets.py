# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The matrix cells of the remote targets (``M/<command>/target/<label>``):
a command on a Git or PyPI URL, which no fixture stands for and no
one-factor variant can give (a variant adds options to the cell's local
target). Each refusal made before any request runs in every run, behind
the network guard, and must make no attempt; a real fetch per route and
the download cap run only with ``--network``.

See also: ``_matrix.py`` (registers these with the other cells),
``_matrix_plan.py`` (the one-factor plan).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass

from _harness import DATETIME, NETGUARD, Check, CheckFunc, Context, expect, run_loom
from _matrix_run import universal

#: What a cell may expect: ``refuses:TEXT`` (exit 1, TEXT on stderr, no
#: SBOM) or ``writes`` (exit 0, an SBOM in ``out.json``).
EXPECTATIONS = ("refuses", "writes")


@dataclass(frozen=True)
class TargetCell:
    """A command on a remote target, run as given plus ``-o out.json`` and
    a pinned ``--creation-datetime``, and what it must do (one of
    :data:`EXPECTATIONS`). A *network* cell runs only with ``--network``."""

    command: str
    label: str
    args: tuple[str, ...]
    expect: str
    network: bool = False


#: A small public repository with a ``pyproject.toml`` (PyPA's
#: ``pyproject-hooks``, a few hundred kilobytes, also read by the live Git
#: tests), at a release tag, so every run checks out the same tree.
_GIT_URL = "https://github.com/pypa/pyproject-hooks/tree/v1.2.0"
#: A small, old, pure-Python release with one wheel and one sdist.
_PYPI_URL = "https://pypi.org/project/six/1.16.0/"
#: That release's wheel, as a direct file link.
_FILE_LINK = (
    "https://files.pythonhosted.org/packages/d9/5a/"
    "e7c31adbe875f2abbb91bd84cf2dc52d792b5a01506781dbcf25c91daf11/"
    "six-1.16.0-py2.py3-none-any.whl"
)
_OFFLINE = "refuses:network access is forbidden"
_INVALID = "refuses:[pypi-url-invalid]"

TARGET_CELLS: list[TargetCell] = [
    TargetCell("project", "git-url-offline", (_GIT_URL, "--offline"), _OFFLINE),
    TargetCell("wheel", "pypi-url-offline", (_PYPI_URL, "--offline"), _OFFLINE),
    TargetCell("project", "pypi-url-offline", (_PYPI_URL, "--offline"), _OFFLINE),
    TargetCell(
        "wheel", "other-index", ("https://test.pypi.org/project/six/",), _INVALID
    ),
    TargetCell("wheel", "file-link", (_FILE_LINK,), _INVALID),
    TargetCell("project", "file-link", (_FILE_LINK,), _INVALID),
    TargetCell("project", "git-url", (_GIT_URL,), "writes", network=True),
    TargetCell("wheel", "pypi-url", (_PYPI_URL,), "writes", network=True),
    TargetCell("project", "pypi-url", (_PYPI_URL,), "writes", network=True),
    TargetCell(
        "wheel",
        "pypi-url-over-cap",
        (_PYPI_URL, "--max-download-bytes", "1"),
        "refuses:[over-cap]",
        network=True,
    ),
    TargetCell(
        "project",
        "git-url-over-cap",
        (_GIT_URL, "--max-download-bytes", "1"),
        "refuses:[over-cap]",
        network=True,
    ),
]


def cell_target(target: TargetCell) -> CheckFunc:
    """The check of *target*."""
    kind, _, value = target.expect.partition(":")

    def run(ctx: Context) -> None:
        expect(kind in EXPECTATIONS, f"unknown expectation {target.expect!r}")
        result = run_loom(
            *target.command.split(),
            *target.args,
            "-o",
            "out.json",
            "--creation-datetime",
            DATETIME,
            cwd=ctx.work,
            bootstrap="" if target.network else NETGUARD,
        )
        universal(result, debug=False, network_ok=target.network)
        out = ctx.work / "out.json"
        if kind == "refuses":
            expect(
                result.returncode == 1 and value in result.stderr,
                f"want exit 1 and {value!r} on stderr\n{result.describe()}",
            )
            expect(not out.exists(), "a refused run wrote an SBOM")
            return
        expect(result.returncode == 0, result.describe())
        expect(out.is_file(), f"no out.json\n{result.describe()}")
        graph = json.loads(out.read_text(encoding="utf-8")).get("@graph")
        expect(bool(graph), "out.json holds no @graph")

    return run


def target_checks(cells: list[TargetCell] | None = None) -> Iterator[Check]:
    """One check per cell of *cells* (default :data:`TARGET_CELLS`)."""
    for target in TARGET_CELLS if cells is None else cells:
        yield Check(
            f"M/{target.command.replace(' ', '-')}/target/{target.label}",
            f"{target.command}: {target.label}",
            cell_target(target),
            target.network,
        )
