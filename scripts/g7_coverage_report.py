# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Report how much of a minimum-elements standard Pitloom's SBOMs meet.

Builds the conformance scenarios (``tests/conformance/g7ai_shared.py``), runs
the checker for one standard (G7 SBOM for AI by default, CISA 2026 or FSCT
2024) and prints a deterministic JSON report: per scenario and per cluster,
the rules ``present``, ``missing``, ``not-applicable`` and ``out-of-scope``,
requirements apart from recommendations, the coverage
(present / (present + missing)), the model the checker judged the system by
and the number of SPDX properties written.

The figure means "meets the checker's reading", not "compliant"; rules the
checker does not check are listed, never counted as missing.

Usage:
  python scripts/g7_coverage_report.py [--standard g7ai|cisa2026|fsct3] [-o FILE]
      [--scenario NAME ...]
  python scripts/g7_coverage_report.py [--standard ...] --write-expected
      [--allow-regression]
  python scripts/g7_coverage_report.py --compare PREVIOUS.json CURRENT.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from collections import Counter
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# pylint: disable=wrong-import-position
from tests.conformance import g7ai_shared as shared  # noqa: E402

Report = dict[str, Any]


def cluster(rule_id: str) -> str:
    """Return the cluster code of *rule_id* (``MDL`` in ``BOM-G7AI2026-MDL-001``)."""
    return rule_id.split("-")[2]


def summarise(
    actual: dict[str, str], kinds: dict[str, str], properties: int
) -> dict[str, Any]:
    """Count one scenario's outcomes in total, by provision and by cluster."""
    counts: dict[str, Counter[str]] = {"all": Counter(), "requirement": Counter()}
    by_cluster: dict[str, Counter[str]] = {}
    for rule, outcome in actual.items():
        counts["all"][outcome] += 1
        if kinds[rule] == "requirement":
            counts["requirement"][outcome] += 1
        by_cluster.setdefault(cluster(rule), Counter())[outcome] += 1

    def coverage(c: Counter[str]) -> float | None:
        decided = c["present"] + c["missing"]
        return round(100 * c["present"] / decided, 1) if decided else None

    return {
        "outcomes": dict(sorted(counts["all"].items())),
        "requirements": dict(sorted(counts["requirement"].items())),
        "coverage_percent": coverage(counts["all"]),
        "requirement_coverage_percent": coverage(counts["requirement"]),
        "clusters": {
            c: {**dict(sorted(n.items())), "coverage_percent": coverage(n)}
            for c, n in sorted(by_cluster.items())
        },
        "properties_written": properties,
    }


def _points(now: float | None, before: float | None) -> str:
    if now is None or before is None:
        return "n/a"
    return f"{now - before:+.1f} points"


def compare(previous: Report, current: Report) -> list[str]:
    """Describe what changed between two reports, one line each."""
    lines = []
    for key in ("standard", "checker", "mapping_sha256", "rules"):
        # A report made before "standard" was recorded is a G7 report.
        default = "g7ai" if key == "standard" else None
        if previous["header"].get(key, default) != current["header"].get(key, default):
            lines.append(f"SERIES BREAK: {key} changed; compare with care")
    for name in sorted(set(previous["scenarios"]) - set(current["scenarios"])):
        lines.append(f"{name}: scenario removed")
    for name, now in current["scenarios"].items():
        before = previous["scenarios"].get(name)
        if before is None:
            lines.append(f"{name}: new scenario")
            continue
        a, b = now["summary"], before["summary"]
        total = _points(a["coverage_percent"], b["coverage_percent"])
        required = _points(
            a["requirement_coverage_percent"], b["requirement_coverage_percent"]
        )
        lines.append(f"{name}: coverage {total}, requirements {required}")
        for rule in sorted(set(now["outcomes"]) | set(before["outcomes"])):
            old, new = before["outcomes"].get(rule), now["outcomes"].get(rule)
            if old != new:
                lines.append(f"  {rule}: {old} -> {new}")
        gained = a["properties_written"] - b["properties_written"]
        if gained:
            lines.append(f"  properties written: {gained:+d}")
    return lines


def regressions(
    expected: dict[str, dict[str, str]], actual: dict[str, dict[str, str]]
) -> list[str]:
    """List the cells that were ``present`` in *expected* and are not now."""
    return [
        f"{rule} [{scenario}]: present -> {actual[scenario][rule]}"
        for rule, cells in sorted(expected.items())
        for scenario, outcome in cells.items()
        if scenario in actual
        and outcome == "present"
        and actual[scenario][rule] != "present"
    ]


def build_report(names: Sequence[str], standard: str = "g7ai") -> Report:
    """Generate the scenarios *names*, check them and return the report."""
    kinds = shared.provisions(standard)
    scenarios: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name in names:
            text = shared.SCENARIOS[name]()
            path = Path(tmp) / f"{name}.spdx3.json"
            path.write_text(text, encoding="utf-8")
            checker = shared.check(path, standard=standard)
            actual = checker.rule_outcomes()
            stand_in = checker.system_judged_by_model()
            written = {
                (e["type"], k)
                for e in json.loads(text)["@graph"]
                for k in e
                if "_" in k
            }
            scenarios[name] = {
                "outcomes": actual,
                "system_judged_by_model": stand_in[0] if stand_in else None,
                "summary": summarise(actual, kinds, len(written)),
            }
    return {
        "header": {
            "pitloom": version("pitloom"),
            "checker": shared.checker_commit(),
            "standard": standard,
            "mapping_sha256": hashlib.sha256(
                shared.mapping_path(standard).read_bytes()
            ).hexdigest(),
            "rules": len(kinds),
        },
        "scenarios": scenarios,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line; return the exit status."""
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").split("\n\n", maxsplit=1)[0]
    )
    parser.add_argument("-o", "--output", type=Path, help="write the report here")
    parser.add_argument("--scenario", action="append", choices=list(shared.SCENARIOS))
    parser.add_argument(
        "--standard", default="g7ai", choices=["g7ai", "cisa2026", "fsct3"]
    )
    parser.add_argument("--write-expected", action="store_true")
    parser.add_argument(
        "--allow-regression",
        action="store_true",
        help="with --write-expected, accept a rule that is no longer present",
    )
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("PREV", "CURRENT"))
    args = parser.parse_args(argv)
    if args.compare:
        previous, current = (json.loads(p.read_text("utf-8")) for p in args.compare)
        print("\n".join(compare(previous, current)))
        return 0
    if args.write_expected and args.scenario:
        parser.error("--write-expected needs every scenario")
    report = build_report(args.scenario or list(shared.SCENARIOS), args.standard)
    if args.write_expected:
        actual = {n: s["outcomes"] for n, s in report["scenarios"].items()}
        table = shared.expected_path(args.standard)
        previous = shared.read_expected(args.standard) if table.exists() else {}
        lost = regressions(previous, actual)
        if lost and not args.allow_regression:
            for line in lost:
                print(f"ERROR: {line}", file=sys.stderr)
            print("ERROR: refusing to rewrite; see --allow-regression", file=sys.stderr)
            return 1
        shared.expected_path(args.standard).write_text(
            shared.render_expected(actual, args.standard),
            encoding="utf-8",
            newline="\n",
        )
        return 0
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
