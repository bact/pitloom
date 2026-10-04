# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Read the CLI's ``KEY=VALUE`` stdout and ``INFO: KEY=VALUE`` stderr lines.

:func:`kv_stdout` is the one assertion that captured stdout is data only:
every non-empty line is space-separated ``KEY=VALUE`` pairs, nothing else.

See also: :mod:`pitloom.cli.kv_output` (the writer),
:mod:`tests.cli.test_cli_kv_stdout` (the every-subcommand guard).
"""

from __future__ import annotations

import re

_KEY = r"[A-Z][A-Z0-9_]*"
#: A whole stdout line: ``KEY=VALUE`` pairs, space-separated; as the writer
#: puts a value that may hold a space last, only the last value may hold one.
_KV_LINE = re.compile(rf"(?:{_KEY}=\S* )*{_KEY}=.*")
#: A key starting a pair, for :func:`parse_kv`.
_PAIR_KEY = re.compile(rf"(?:^| )({_KEY})=")
_INFO = "INFO: "


def parse_kv(line: str) -> dict[str, str]:
    """The pairs of one ``KEY=VALUE ...`` line. A value runs to the next
    `` KEY=``, so the last value may hold a space."""
    keys = list(_PAIR_KEY.finditer(line))
    return {
        match.group(1): line[
            match.end() : keys[i + 1].start() if i + 1 < len(keys) else len(line)
        ]
        for i, match in enumerate(keys)
    }


def kv_stdout(out: str) -> list[dict[str, str]]:
    """Assert every non-empty line of *out* is ``KEY=VALUE`` pairs only;
    return one dict per line."""
    lines = [line for line in out.splitlines() if line]
    stray = [line for line in lines if not _KV_LINE.fullmatch(line)]
    assert not stray, f"stdout is not KEY=VALUE only: {stray}"
    return [parse_kv(line) for line in lines]


def records(out: str, key: str) -> list[dict[str, str]]:
    """The stdout records of *out* (see :func:`kv_stdout`) holding *key*."""
    return [record for record in kv_stdout(out) if key in record]


def statuses(out: str) -> list[str]:
    """The ``STATUS=`` value of every stdout record of *out*, in order."""
    return [record["STATUS"] for record in records(out, "STATUS")]


def sbom_output_path(out: str) -> str:
    """The one ``PITLOOM_SBOM_OUTPUT_PATH=`` value of *out*."""
    (record,) = records(out, "PITLOOM_SBOM_OUTPUT_PATH")
    return record["PITLOOM_SBOM_OUTPUT_PATH"]


def info_lines(err: str) -> list[str]:
    """Every ``INFO:`` line of captured stderr, without the tag."""
    return [line[len(_INFO) :] for line in err.splitlines() if line.startswith(_INFO)]


def info_kv(err: str) -> dict[str, str]:
    """Every ``INFO: KEY=VALUE`` pair of captured stderr, merged, for the
    ``-v`` lines that give one fact each."""
    merged: dict[str, str] = {}
    for line in info_lines(err):
        if _PAIR_KEY.match(line):
            merged.update(parse_kv(line))
    return merged


def info_options(err: str) -> dict[str, dict[str, str]]:
    """The ``-v`` ``INFO: OPTION=<name> SOURCE=<source> VALUE=<value>``
    lines of captured stderr, keyed by option name."""
    rows = (parse_kv(line) for line in info_lines(err) if line.startswith("OPTION="))
    return {row["OPTION"]: row for row in rows}
