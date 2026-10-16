# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The steps of the order-matrix checks (``O*``): each Pitloom operation
rendered as shell lines, plus a simulation of what the mutating steps do
to the project's files, so the invariants know the bytes on disk after
every step without re-reading them.

Operations (``OPS``): ``gen``, ``gen-ds`` (``id generate``, plain and
with both datasets pinned by ``-e NAME:dataset_DatasetPackage``),
``gen-min`` (``pyproject.toml`` alone: a registry that holds almost
nothing),
``import`` (``id import`` of the SBOM or fragment most recently
produced), ``import0`` (of the SBOM the setup produced: the same input
in every order), ``project``, ``wheel`` (a fresh offline build, then
``loom wheel``), ``sdist`` (a fresh sdist, then ``loom project SDIST``),
``model``, ``embed`` (a fresh build, then
``embed-wheel --project-dir``), ``train``/``eval`` (``loom.run`` scripts with
``set_model``/``use_model(path=)``, a file and a directory dataset; run from
the profile's ``loom_dir``), and
the mutating ``retrain``, ``edit-file`` (the newest added module, else
the profile's file), ``edit-data``, ``rename-file``, ``add-file``. Spelling
steps, run only by the ``O6`` checks (a file system may not support them):
``add-nfd`` (a module whose name is in NFD), ``model-upper`` and
``train-upper`` (``model`` / ``train`` with the model path in upper case).
Not covered: ``enrich`` (needs a model card or the network), ``env`` (reads
the interpreter's environment, not the project), ``merge`` (no
registry), the Hatchling hook with a registry (``embed`` covers the
build-stage reader) and setuptools wheels (a build writes ``*.egg-info``
into the project).

See also: ``_order_fixtures.py``, ``_order_gen.py`` (sequences and the
script around these lines), ``_order_invariants.py``.
"""

from __future__ import annotations

import posixpath
import shlex
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from _order_fixtures import (
    DATASET_DIR,
    DATASET_FILE,
    NAMESPACE,
    Profile,
    fixture_dir,
    model_bytes,
)

MUTATING = frozenset(
    {"retrain", "edit-file", "edit-data", "rename-file", "add-file", "add-nfd"}
)
#: Steps that run a Pitloom command against the registry.
READERS = frozenset(
    {"gen", "gen-ds", "gen-min", "import", "import0", "project", "wheel"}
    | {"model", "embed", "train", "eval", "sdist", "model-upper", "train-upper"}
)
OPS = tuple(sorted(MUTATING | READERS))
#: Steps only the ``O6`` spelling checks run: they need a file system that
#: keeps an NFD name or folds case, so no walk or permutation may pick them.
SPELLING = frozenset({"add-nfd", "model-upper", "train-upper"})
#: The surface (the key of an output's graph) of a step that is not its own.
SURFACE = {"model-upper": "model", "train-upper": "train"}
#: A file name in NFD: "cafe" and a combining acute accent.
NFD_STEM = "cafe\u0301"
#: The `id import` steps: the only ones that may drop a recorded sha256.
IMPORTS = frozenset({"import", "import0"})
#: A v2 registry file (design D10: one ERROR, no migration).
V2_REGISTRY = (
    '{"entities": {}, "files": {}, "namespace": "' + NAMESPACE + '", "version": 2}\n'
)
BAD_JSON = "{\n"
INJECTIONS = ("v2", "badjson", "readonly")


def applies(op: str, profile: Profile) -> bool:
    """Whether *op* can run on *profile*'s project."""
    if op in ("wheel", "embed", "sdist"):
        return profile.wheel
    if op in ("model", "retrain", "model-upper"):
        return profile.model is not None
    if op in ("train", "eval", "train-upper", "gen-ds", "edit-data"):
        return profile.loom
    return True


def upper(path: str) -> str:
    """*path* with its directories and stem in upper case (the extension
    stays: a format is recognised by it)."""
    pure = PurePosixPath(path)
    return str(pure.parent.as_posix().upper() + "/" + pure.stem.upper() + pure.suffix)


@dataclass(frozen=True)
class Step:
    """One numbered step of a sequence and what it leaves behind."""

    n: int
    op: str
    #: ``setup``, ``step``, or an injected failure (``INJECTIONS``).
    kind: str
    lines: tuple[str, ...]
    #: (surface, path relative to the work dir) of each SBOM written.
    outputs: tuple[tuple[str, str], ...] = ()
    #: The SBOM `id import` read (relative to the work dir).
    imported: str | None = None
    #: Project files changed by mutating steps so far (None: removed).
    overlay: Mapping[str, bytes | None] = field(default_factory=dict)

    @property
    def tag(self) -> str:
        """The step's log file stem."""
        return f"{self.n:02d}"


class Planner:
    """Turns op names into :class:`Step` s for one profile, tracking the
    simulated file changes and the last SBOM written."""

    def __init__(self, profile: Profile) -> None:
        self.profile = profile
        self.steps: list[Step] = []
        self._overlay: dict[str, bytes | None] = {}
        self._last_sbom: str | None = None
        self._setup_sbom: str | None = None
        self._renamed = False
        self._added: list[str] = []

    def _reg_flag(self, flag: str) -> list[str]:
        """``flag "$REG"``, or nothing when the project declares it."""
        return [] if self.profile.in_tree else [flag, '"$REG"']

    def add(self, op: str, kind: str = "step") -> Step:
        """Plan *op* as the next step."""
        n = len(self.steps) + 1
        tag = f"{n:02d}"
        lines, outputs, imported = self._render(op, tag, n)
        if kind in INJECTIONS:
            lines = _inject(kind, lines)
        for surface, path in outputs:
            if kind in ("setup", "step", "readonly"):
                self._last_sbom = path
            if kind == "setup" and surface == "project":
                self._setup_sbom = path
        step = Step(
            n, op, kind, tuple(lines), tuple(outputs), imported, dict(self._overlay)
        )
        self.steps.append(step)
        return step

    def _render(
        self, op: str, tag: str, n: int
    ) -> tuple[list[str], list[tuple[str, str]], str | None]:
        """(shell lines, outputs, imported SBOM) of *op* as step *n*."""
        if op in MUTATING:
            return [self._mutate(op, tag, n)], [], None
        if op in ("gen", "gen-ds", "gen-min"):
            target = self.profile.pyproject if op == "gen-min" else "."
            cmd = ["loom", "id", "generate", target, "--project-dir", "."]
            cmd += [*self._reg_flag("-o"), "--namespace", '"$NS"']
            if op == "gen-ds":
                cmd += ["-e", f"{DATASET_FILE}:dataset_DatasetPackage"]
                cmd += ["-e", f"{DATASET_DIR}:dataset_DatasetPackage"]
            return [_run(tag, cmd)], [], None
        if op in ("import", "import0"):
            source = self._setup_sbom if op == "import0" else self._last_sbom
            if source is None:
                return [_run(tag, ["true"]) + "  # no SBOM yet"], [], None
            cmd = ["loom", "id", "import", f'"$WORK/{source}"', *self._reg_flag("-o")]
            return [_run(tag, cmd)], [], source
        out = f"out/{tag}-{op}.json"
        build = {"wheel": "build", "embed": "build", "sdist": "build_sdist"}.get(op)
        pre = [f"{build} {tag} {self.profile.subdir or '.'}"] if build else []
        return (
            [*pre, _run(tag, self._surface(op, out))],
            [(SURFACE.get(op, op), out)],
            None,
        )

    def _surface(self, op: str, out: str) -> list[str]:
        """The command of a step that writes an SBOM or fragment to *out*."""
        p = self.profile
        target = f'"$WORK/{out}"'
        common = ["-o", target, "--creation-datetime", '"$DT"']
        model = upper(str(p.model)) if op.endswith("-upper") else str(p.model)
        # A monorepo's archive names its project, as `embed` always does.
        project_dir = ["--project-dir", p.subdir] if p.subdir else []
        commands = {
            "project": ["project", p.subdir or ".", *self._reg_flag("--id-registry")],
            "sdist": ["project", '"$SDIST"', "--id-registry", '"$REG"', *project_dir],
            "wheel": ["wheel", '"$WHEEL"', "--id-registry", '"$REG"', *project_dir],
            "embed": ["embed-wheel", '"$WHEEL"', "--project-dir", p.subdir or "."]
            + ["--id-registry", '"$REG"'],
            # A local model file: --offline would only warn it has no effect.
            "model": ["model", model, "--id-registry", '"$REG"'],
        }
        commands["model-upper"] = commands["model"]
        if op in ("train", "eval", "train-upper"):
            return self._loom_script(op.removesuffix("-upper"), target, model)
        offline = [] if op.startswith("model") else ["--offline"]
        return ["loom", *commands[op], *common, *offline]

    def _loom_script(self, op: str, target: str, model: str) -> list[str]:
        """A `loom.run` script run from the profile's ``loom_dir``, naming
        the model and datasets relative to it."""
        here = self.profile.loom_dir or "."

        def rel(path: str) -> str:
            return posixpath.relpath(path, here)

        cmd = [
            '"$PY"',
            f"{op}.py",
            target,
            '"$REG"',
            rel(model),
            str(self.profile.stem),
        ]
        cmd += [rel(DATASET_FILE)]
        if op == "train":
            cmd += [rel(DATASET_DIR)]
        return ["in_dir", here, *cmd]

    def _mutate(self, op: str, tag: str, n: int) -> str:
        p = self.profile
        if op == "retrain":
            self._overlay[str(p.model)] = model_bytes(n)
            return _run(tag, ["retrain", str(p.model), str(n)])
        if op in ("edit-file", "edit-data"):
            # The newest file this sequence added, else the profile's one.
            path = (self._added or [p.edit])[-1] if op == "edit-file" else DATASET_FILE
            self._overlay[path] = self.current(path) + f"# edit {n}\n".encode()
            return _run(tag, ["append", path, str(n)])
        if op in ("add-file", "add-nfd"):
            stem = NFD_STEM if op == "add-nfd" else "new"
            path = f"{p.package_dir}/{stem}_{tag}.py"
            self._added.append(path)
            self._overlay[path] = f"N = {n}\n".encode()
            return _run(tag, ["add", path, str(n)])
        if op == "rename-file":
            old, new = p.rename[::-1] if self._renamed else p.rename
            self._overlay[new] = self.current(old)
            self._overlay[old] = None
            self._renamed = not self._renamed
            return _run(tag, ["mv", old, new])
        raise ValueError(f"unknown op {op!r}")

    def current(self, path: str) -> bytes:
        """*path*'s simulated bytes; only for files a step changed."""
        if path not in self._overlay:
            return (fixture_dir(self.profile.name) / path).read_bytes()
        data = self._overlay[path]
        if data is None:
            raise ValueError(f"{path} was removed by an earlier step")
        return data


def _run(tag: str, cmd: list[str]) -> str:
    return " ".join(["run", tag, *cmd])


def _inject(kind: str, lines: list[str]) -> list[str]:
    """Wrap a step's lines so it runs against a broken registry (design
    D10, section 6) or a read-only one (build notes),
    then put the registry back."""
    if kind == "readonly":
        return ['chmod 444 "$REG"', *lines, 'chmod 644 "$REG"']
    content = V2_REGISTRY if kind == "v2" else BAD_JSON
    return [
        'cp "$REG" "$WORK/reg.bak"',
        f'printf %s {shlex.quote(content)} >"$REG"',
        *lines,
        'cp "$WORK/reg.bak" "$REG"',
    ]
