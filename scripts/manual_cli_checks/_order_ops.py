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
``loom wheel``), ``model``, ``embed`` (a fresh build, then
``embed-wheel --project-dir``), ``train``/``eval`` (``loom.run`` scripts with
``set_model``/``use_model(path=)``, a file and a directory dataset), and
the mutating ``retrain``, ``edit-file`` (the newest added module, else
the profile's file), ``edit-data``, ``rename-file``, ``add-file``. Not
covered: ``enrich`` (needs a model card or the network), ``env`` (reads
the interpreter's environment, not the project), ``merge`` (no
registry), the Hatchling hook with a registry (``embed`` covers the
build-stage reader) and setuptools wheels (a build writes ``*.egg-info``
into the project).

See also: ``_order_fixtures.py``, ``_order_gen.py`` (sequences and the
script around these lines), ``_order_invariants.py``.
"""

from __future__ import annotations

import shlex
from collections.abc import Mapping
from dataclasses import dataclass, field

from _order_fixtures import (
    DATASET_DIR,
    DATASET_FILE,
    NAMESPACE,
    Profile,
    fixture_dir,
    model_bytes,
)

MUTATING = frozenset({"retrain", "edit-file", "edit-data", "rename-file", "add-file"})
#: Steps that run a Pitloom command against the registry.
READERS = frozenset(
    {"gen", "gen-ds", "gen-min", "import", "import0", "project", "wheel"}
    | {"model", "embed", "train", "eval"}
)
OPS = tuple(sorted(MUTATING | READERS))
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
    if op in ("wheel", "embed"):
        return profile.wheel
    if op in ("model", "retrain"):
        return profile.model is not None
    if op in ("train", "eval", "gen-ds", "edit-data"):
        return profile.loom
    return True


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
            target = "pyproject.toml" if op == "gen-min" else "."
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
        build = [f"build {tag}"] if op in ("wheel", "embed") else []
        return [*build, _run(tag, self._surface(op, out))], [(op, out)], None

    def _surface(self, op: str, out: str) -> list[str]:
        """The command of a step that writes an SBOM or fragment to *out*."""
        p = self.profile
        target = f'"$WORK/{out}"'
        common = ["-o", target, "--creation-datetime", '"$DT"']
        loom = ['"$PY"', f"{op}.py", target, '"$REG"', str(p.model), str(p.stem)]
        commands = {
            "project": ["project", ".", *self._reg_flag("--id-registry")],
            "wheel": ["wheel", '"$WHEEL"', "--id-registry", '"$REG"'],
            "embed": ["embed-wheel", '"$WHEEL"', "--project-dir", "."]
            + ["--id-registry", '"$REG"'],
            # A local model file: --offline would only warn it has no effect.
            "model": ["model", str(p.model), "--id-registry", '"$REG"'],
        }
        if op == "train":
            return [*loom, DATASET_FILE, DATASET_DIR]
        if op == "eval":
            return [*loom, DATASET_FILE]
        offline = [] if op == "model" else ["--offline"]
        return ["loom", *commands[op], *common, *offline]

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
        if op == "add-file":
            path = f"{p.package_dir}/new_{tag}.py"
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
