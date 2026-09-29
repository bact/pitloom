# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The CLI matrix: every subcommand x its options (``_matrix_plan.py``)
x the environment variables that change its behaviour, one check per
cell (``M/<command>/<group>/<variant>``).

Every cell runs a real ``loom`` behind the network guard, in its own
directory with private fixture copies, with ``--offline`` and a pinned
``--creation-datetime`` wherever the command takes them (except in the
group varying that option), and checks the universal invariants: no
traceback, every stderr line tagged, no network attempt. Groups:

- ``debug``: ``--debug``/``--no-debug``/none x ``PITLOOM_DEBUG``
  unset/1/0 -- the logger level Pitloom configured (the flag wins over
  the variable), same exit code and artefact as the plain run, no
  ``DEBUG:`` line with debug off;
- ``output``: ``-o FILE``/``-o -``/none x ``--pretty``/``--no-pretty``/
  none -- where the SBOM lands, its formatting, the same content;
- ``date``: ``--creation-datetime`` x ``SOURCE_DATE_EPOCH`` -- the
  ``created`` value (flag first) and byte-identical repeat runs;
- ``offline``: ``--offline``/``--no-offline``/none -- zero attempts
  with ``--offline``, graceful degradation when the network is blocked;
- ``opt``: every other option's one-factor variants;
- ``parity``: ``generate`` against the dedicated subcommand.

See also: ``_matrix_run.py`` (running a cell), ``_sequences.py``
(commands run in order, with side effects).
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Iterator

import _fixtures
from _harness import (
    DATETIME,
    NETGUARD,
    Check,
    CheckFunc,
    Context,
    child_env,
    expect,
    require,
    run_loom,
)
from _matrix_plan import COMMANDS, NETWORK_VARIANTS, Command, Variant, plan_for
from _matrix_run import DATETIME_2, Matrix, cli_surface, created, normalise, universal

from pitloom.core.no_effect import INERT_LOG_PREFIX

_INERT_WARNING = f"WARNING: {INERT_LOG_PREFIX}"


def _names_flag(line: str, flag: str) -> bool:
    """Whether an ``Options:`` warning names *flag*, alone or as either
    half of a ``--x/--no-x`` pair."""
    return any(
        f"{head}{flag}{tail}" in line
        for head in (": ", "/")
        for tail in (" has no effect", "/")
    )


def _cell_debug(
    mx: Matrix, command: Command, flag: str | None, env_value: str | None
) -> CheckFunc:
    def run(ctx: Context) -> None:
        rc, base = mx.baseline(command)
        env = child_env() if env_value is None else child_env(PITLOOM_DEBUG=env_value)
        result, artefact = mx.run(
            command, ctx.work, pre=(flag,) if flag else (), env=env
        )
        on = flag == "--debug" or (flag is None and env_value == "1")
        universal(result, debug=on, network_ok=command.network)
        # The decision itself, not just its visible output (a clean run
        # may log nothing at DEBUG either way).
        expect(
            result.log_level == (10 if on else 20),
            f"pitloom logger level {result.log_level}, want "
            f"{'DEBUG (10)' if on else 'INFO (20)'}",
        )
        expect(result.returncode == rc, f"exit {result.returncode}, plain run {rc}")
        expect(artefact == base, "artefact differs from the plain run")
        if not on:
            expect(
                not any(line.startswith("DEBUG: ") for line in result.stderr_lines),
                "DEBUG: line with debug off",
            )

    return run


def _cell_output(
    mx: Matrix, command: Command, where: str | None, pretty: str | None
) -> CheckFunc:
    def run(ctx: Context) -> None:
        _, base = mx.baseline(command)
        extra = [pretty] if pretty else []
        if where is not None:
            extra = ["-o", "out.json" if where == "file" else "-", *extra]
        result, _ = mx.run(command, ctx.work, extra=tuple(extra), output=False)
        universal(result, debug=False)
        if where is None and not command.default_output:
            expect(
                result.returncode == 1 and "ERROR: " in result.stderr,
                f"expected a refusal without -o\n{result.describe()}",
            )
            return
        expect(result.returncode == 0, result.describe())
        if where == "file":
            text = (ctx.work / "out.json").read_text(encoding="utf-8")
        elif where == "-":
            text = result.stdout
        else:
            lines = result.stdout.splitlines()
            paths = [
                ln.split("=", 1)[1]
                for ln in lines
                if ln.startswith("PITLOOM_SBOM_OUTPUT_PATH=")
            ]
            expect(len(paths) == 1, f"stdout: {lines}")
            text = (ctx.work / paths[0]).read_text(encoding="utf-8")
            ctx.note(f"default output: {paths[0]}")
        doc = json.loads(text)
        if pretty == "--pretty":
            expect("\n  " in text, "--pretty output is not indented")
        if pretty == "--no-pretty":
            expect("\n" not in text.strip(), "--no-pretty output spans lines")
        base_doc = json.loads(require(base, "plain run wrote no SBOM"))
        expect(
            normalise(json.dumps(doc, sort_keys=True), ctx.work)
            == json.dumps(base_doc, sort_keys=True),
            "content differs from the plain run",
        )

    return run


def _cell_date(mx: Matrix, command: Command, flag: bool, sde: bool) -> CheckFunc:
    def run(ctx: Context) -> None:
        env = (
            child_env(SOURCE_DATE_EPOCH=_fixtures.SOURCE_DATE_EPOCH)
            if sde
            else child_env()
        )
        extra = ("--creation-datetime", DATETIME_2) if flag else ()
        texts = []
        for attempt in ("a", "b"):
            result, artefact = mx.run(
                command, ctx.work / attempt, extra=extra, env=env, dated=False
            )
            universal(result, debug=False)
            expect(result.returncode == 0, result.describe())
            texts.append(artefact)
        expected = DATETIME_2 if flag else DATETIME if sde else None
        stamps = created(texts[0])
        if expected is None:
            ctx.note(f"created (unpinned): {stamps}")
            return
        expect(all(c == expected for c in stamps), f"created {stamps}, want {expected}")
        expect(texts[0] == texts[1], "two pinned runs differ")

    return run


def _cell_offline(mx: Matrix, command: Command, flag: str | None) -> CheckFunc:
    def run(ctx: Context) -> None:
        result, artefact = mx.run(
            command, ctx.work, offline=False, extra=(flag,) if flag else ()
        )
        universal(result, debug=False, network_ok=flag != "--offline")
        expect(result.returncode == 0, result.describe())
        expect(artefact is not None, "no artefact")
        ctx.note(f"{result.network_attempts} network attempts (blocked)")

    return run


def _cell_variant(
    mx: Matrix, command: Command, variant: Variant, network: bool
) -> CheckFunc:
    def run(ctx: Context) -> None:
        rc, base = mx.baseline(command)
        args = tuple(variant.args(_fixtures.get(), ctx.work))
        result, artefact = mx.run(command, ctx.work, extra=args, network=network)
        kind, _, value = variant.expect.partition(":")
        if kind == "exit":
            expect(
                result.returncode == int(value),
                f"exit {result.returncode}, want {value}\n{result.describe()}",
            )
            expect(
                "Traceback (most recent call last)" not in result.stderr,
                f"traceback:\n{result.describe()}",
            )
            return
        universal(result, debug=False, network_ok=network or command.network)
        expect(
            result.returncode == rc,
            f"exit {result.returncode}, plain run {rc}\n" + result.describe(),
        )
        effect = "same" if artefact == base else "changes"
        ctx.note(f"effect: {effect}")
        inert = [ln for ln in result.stderr_lines if ln.startswith(_INERT_WARNING)]
        if kind == "warns":
            # An option the target cannot use: one warning naming it, and
            # the artefact exactly as if it had not been given.
            named = [ln for ln in inert if _names_flag(ln, value)]
            expect(len(named) == 1, f"want one {value} warning, got {inert}")
            expect(effect == "same", "an inert option changed the artefact")
            return
        # Every other expectation is a live option: it must not also warn
        # that it has no effect. Only warnings naming this variant's own
        # flags count -- a cell's fixed flags (e.g. --offline) may be inert
        # for its target, and warn rightly.
        flags = [arg for arg in args if arg.startswith("--")]
        own = [ln for ln in inert if any(_names_flag(ln, f) for f in flags)]
        expect(not own, f"a live option warned: {own}")
        if kind in ("same", "changes"):
            expect(effect == kind, f"expected {kind}, got {effect}")
        elif kind == "contains":
            expect(
                artefact is not None and value in artefact, f"{value!r} not in output"
            )
        elif kind == "writes":
            expect((ctx.work / value).is_file(), f"{value} not written")

    return run


def _cell_parity(mx: Matrix, generate: Command, dedicated: Command) -> CheckFunc:
    # generate, given the dedicated command's own target ("env" for env).
    as_generate = Command(
        "generate",
        lambda fx, cell: dedicated.target(fx, cell) or ["env"],
        generate.artefact,
    )

    def run(ctx: Context) -> None:
        _, want = mx.run(dedicated, ctx.work / "dedicated")
        result, got = mx.run(as_generate, ctx.work / "generate")
        universal(result, debug=False)
        expect(
            got is not None and got == want, f"generate differs from {dedicated.name}"
        )

    return run


def _groups_run(mx: Matrix) -> dict[str, set[str]]:
    """Command -> the cell groups (``debug``, ``output``, ...) it runs."""
    return {
        c.name: {
            cell_id.split("/", 1)[0]
            for cell_id, _, _ in itertools.chain(_group_cells(mx, c), _env_cells(mx, c))
        }
        for c in COMMANDS
    }


def _cell_completeness(mx: Matrix) -> CheckFunc:
    def run(ctx: Context) -> None:
        groups = _groups_run(mx)

        def planned(cmd: str, opt: str) -> bool:
            entry = plan_for(cmd, opt)
            if isinstance(entry, str) and entry.startswith("group:"):
                name = entry[len("group:") :]
                if cmd not in groups:
                    # A parent parser (loom, ids, fragment) runs no cells
                    # of its own: covered only while some subcommand still
                    # runs that group -- `--debug` lives only here.
                    return any(name in cells for cells in groups.values())
                return name in groups[cmd]
            return entry is not None

        missing = [
            f"{cmd}: {'/'.join(opt)}"
            for cmd, opts in mx.surface.items()
            for opt in opts
            if not planned(cmd, opt[0])
        ]
        known = {c.name for c in COMMANDS} | {"loom", "fragment", "id"}
        unknown = sorted(set(mx.surface) - known)
        expect(not missing, f"options with no plan entry: {missing}")
        expect(not unknown, f"subcommands with no Command entry: {unknown}")
        ctx.note(f"{sum(len(o) for o in mx.surface.values())} options classified")

    return run


Cell = tuple[str, CheckFunc, bool]  # (id suffix, check, needs network)


def _group_cells(mx: Matrix, command: Command) -> Iterator[Cell]:
    """The debug and output cells of *command*."""
    for flag, env_value in itertools.product(
        (None, "--debug", "--no-debug"), (None, "1", "0")
    ):
        label = f"{flag or 'no-flag'}+PITLOOM_DEBUG={env_value or 'unset'}"
        yield (
            f"debug/{label}",
            _cell_debug(mx, command, flag, env_value),
            command.network,
        )
    if command.artefact == "output" and mx.takes(command, "-o"):
        for where, pretty in itertools.product(
            ("file", "-", None), (None, "--pretty", "--no-pretty")
        ):
            label = f"{'-o=' + where if where else 'no-o'}+{pretty or 'default'}"
            yield f"output/{label}", _cell_output(mx, command, where, pretty), False


def _env_cells(mx: Matrix, command: Command) -> Iterator[Cell]:
    """The date and offline cells of *command*."""
    if mx.takes(command, "--creation-datetime"):
        for flag_on, sde in itertools.product((False, True), (False, True)):
            label = (
                f"{'--creation-datetime' if flag_on else 'no-flag'}"
                f"+SOURCE_DATE_EPOCH={'set' if sde else 'unset'}"
            )
            yield f"date/{label}", _cell_date(mx, command, flag_on, sde), False
    if mx.takes(command, "--offline"):
        for flag in (None, "--offline", "--no-offline"):
            yield (
                f"offline/{flag or 'no-flag'}",
                _cell_offline(mx, command, flag),
                False,
            )


def _option_cells(mx: Matrix, command: Command) -> Iterator[Cell]:
    """The one-factor cells of *command*'s planned options."""
    for opt in mx.surface.get(command.name, []):
        entry = plan_for(command.name, opt[0])
        if not isinstance(entry, list):
            continue
        network = command.network or (command.name, opt[0]) in NETWORK_VARIANTS
        for variant in entry:
            label = f"{opt[0]}={variant.label.replace(' ', '_')}"
            yield f"opt/{label}", _cell_variant(mx, command, variant, network), network


def register(checks: list[Check]) -> None:
    """Add every matrix cell to *checks*. Ids have no spaces."""
    mx = Matrix(cli_surface())
    checks.append(
        Check(
            "M/completeness",
            "every subcommand and option is planned",
            _cell_completeness(mx),
        )
    )
    for command in COMMANDS:
        slug = command.name.replace(" ", "-")
        for suffix, func, network in itertools.chain(
            _group_cells(mx, command),
            _env_cells(mx, command),
            _option_cells(mx, command),
        ):
            group, _, label = suffix.partition("/")
            if group == "opt":
                label = label.replace("=", " ", 1)
            title = f"{command.name}: {label}"
            checks.append(Check(f"M/{slug}/{suffix}", title, func, network))
    by_name = {c.name: c for c in COMMANDS}
    for name in ("project", "wheel", "model", "env"):
        checks.append(
            Check(
                f"M/generate/parity/{name}",
                f"generate = {name}",
                _cell_parity(mx, by_name["generate"], by_name[name]),
            )
        )
    for variant in plan_for("loom", "-V") or []:
        if isinstance(variant, Variant):
            checks.append(
                Check(
                    f"M/loom/opt/-V={variant.label}",
                    f"loom {variant.label}",
                    _top_level(variant),
                )
            )


def _top_level(variant: Variant) -> CheckFunc:
    def run(ctx: Context) -> None:
        result = run_loom(
            *variant.args(_fixtures.get(), ctx.work), cwd=ctx.work, bootstrap=NETGUARD
        )
        expect(
            result.returncode == 0 and result.stdout.strip() != "", result.describe()
        )
        expect(result.network_attempts == 0, result.describe())

    return run
