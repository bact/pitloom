# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Fixture projects for the order-matrix checks (``O*``): one profile per
project shape, built once per run under the shared fixtures root and copied
by each sequence's script (never modified in place).

See also: ``_order_ops.py`` (the steps), ``_checks_order.py`` (the checks),
``_fixtures.py`` (``write_project``, the flat demo project).
"""

from __future__ import annotations

import shutil
import struct
import textwrap
import threading
from dataclasses import dataclass
from pathlib import Path

import _fixtures
from _harness import REPO_ROOT

# A fixed registry namespace (design D8 `--namespace`), so two permutations
# starting from the same state can be compared byte for byte.
NAMESPACE = "https://example.org/ord"
_HEADER = b'{"t":{"dtype":"F32","shape":[1],"data_offsets":[0,4]}}'


def model_bytes(weight: int) -> bytes:
    """A one-tensor safetensors file holding *weight* as F32; weight 0 is
    the fixture's pristine model, ``retrain N`` writes weight N."""
    return struct.pack("<Q", len(_HEADER)) + _HEADER + struct.pack("<f", weight)


# The shell side of `retrain`: the same bytes as model_bytes() (a test pins it).
RETRAIN_PY = (
    "import struct, sys; h = " + repr(_HEADER) + "; "
    "open(sys.argv[1], 'wb').write("
    "struct.pack('<Q', len(h)) + h + struct.pack('<f', int(sys.argv[2])))"
)

TRAIN_PY = textwrap.dedent(
    """\
    import sys
    from pitloom import loom

    out, registry, model, stem, data, corpus = sys.argv[1:7]
    with loom.run(out, id_registry=registry):
        loom.set_model(stem, path=model)
        loom.add_dataset(data)
        loom.add_input_dataset(corpus)
    """
)
EVAL_PY = textwrap.dedent(
    """\
    import sys
    from pitloom import loom

    out, registry, model, stem, data = sys.argv[1:6]
    with loom.run(out, id_registry=registry):
        loom.use_model(stem, path=model)
        loom.add_validation_dataset(data)
    """
)
DATASET_FILE = "data/t.txt"
DATASET_DIR = "corpus"


@dataclass(frozen=True)
class Profile:
    """One fixture project and the facts the steps need about it."""

    name: str
    #: Project-relative model file and the stem `id generate` keys it by.
    model: str | None
    stem: str | None
    #: The file `edit-file` appends to, and the pair `rename-file` toggles.
    edit: str
    rename: tuple[str, str]
    #: Where `add-file` writes a new module.
    package_dir: str
    #: Whether a wheel can be built offline here (`wheel`, `embed`).
    wheel: bool
    #: Project-relative registry declared in `[tool.pitloom]`, or None for
    #: a registry beside the project passed with `--id-registry`/`-o`.
    in_tree: str | None = None
    #: Two model files sharing one stem: each keeps its own id.
    shared_stem: bool = False
    #: Every model file of the project (``model`` alone when empty).
    models: tuple[str, ...] = ()
    #: The project directory below the registry root (a monorepo) and the
    #: directory the `loom.run` scripts run from ("" = the registry root).
    subdir: str = ""
    loom_dir: str = ""
    #: (op, why) of the steps that do not apply to this layout.
    unsupported: tuple[tuple[str, str], ...] = ()

    @property
    def loom(self) -> bool:
        """Whether the `loom.run` scripts apply (they need a model)."""
        return self.model is not None

    @property
    def model_paths(self) -> tuple[str, ...]:
        """Every project-relative model file."""
        return self.models or ((self.model,) if self.model else ())

    @property
    def pyproject(self) -> str:
        """The project's ``pyproject.toml``, relative to the registry root."""
        return f"{self.subdir}/pyproject.toml" if self.subdir else "pyproject.toml"


def _add_loom_files(root: Path, scripts: str = "") -> None:
    (root / "data").mkdir(exist_ok=True)
    (root / DATASET_FILE).write_bytes(b"one line\n")
    (root / DATASET_DIR / "b").mkdir(parents=True)
    (root / DATASET_DIR / "a.txt").write_bytes(b"a\n")
    (root / DATASET_DIR / "b" / "c.txt").write_bytes(b"c\n")
    (root / scripts).mkdir(exist_ok=True)
    (root / scripts / "train.py").write_text(TRAIN_PY, encoding="utf-8")
    (root / scripts / "eval.py").write_text(EVAL_PY, encoding="utf-8")


def _flat(root: Path) -> None:
    _fixtures.write_project(root)
    (root / "demo" / "tiny.safetensors").write_bytes(model_bytes(0))
    _add_loom_files(root)


def _src(root: Path) -> None:
    source = REPO_ROOT / "tests" / "fixtures" / "projects" / "sampleproject-hatchling"
    shutil.copytree(source, root)
    package = root / "src" / "sampleproject_hatchling"
    (package / "tiny.safetensors").write_bytes(model_bytes(0))
    (package / "data.csv").write_bytes(b"a,b\n1,2\n")
    _add_loom_files(root)


def _setuptools(root: Path) -> None:
    source = REPO_ROOT / "tests" / "fixtures" / "projects" / "sampleproject-setuptools"
    shutil.copytree(source, root)
    (root / "src" / "sampleproject_setuptools" / "data.csv").write_bytes(b"a,b\n")


def _stems(root: Path) -> None:
    _fixtures.write_project(root)
    (root / "demo" / "tiny.safetensors").unlink()
    (root / "demo" / "load.py").write_text('MODEL = "m.safetensors"\n', "utf-8")
    for sub in ("a", "b"):
        (root / "demo" / sub).mkdir()
        (root / "demo" / sub / "m.safetensors").write_bytes(model_bytes(0))
    # Different bytes, so the two files are not one hash-merged element.
    (root / "demo" / "b" / "m.safetensors").write_bytes(model_bytes(-1))
    _add_loom_files(root)


def _in_tree(root: Path) -> None:
    _flat(root)
    with (root / "pyproject.toml").open("a", encoding="utf-8") as fh:
        fh.write('\n[tool.pitloom]\nid-registry = "demo/reg.json"\n')


def _monorepo(root: Path) -> None:
    _fixtures.write_project(root / "pkgs" / "demo")
    (root / "pkgs" / "demo" / "demo" / "tiny.safetensors").write_bytes(model_bytes(0))
    _add_loom_files(root)


def _subdir(root: Path) -> None:
    """Models, data and the loom scripts in sibling directories."""
    _fixtures.write_project(root)
    (root / "demo" / "tiny.safetensors").unlink()
    (root / "demo" / "load.py").write_text('MODEL = "m.safetensors"\n', "utf-8")
    (root / "models").mkdir()
    (root / "models" / "m.safetensors").write_bytes(model_bytes(0))
    _add_loom_files(root, "scripts")


_FLAT_RENAME = ("demo/data.csv", "demo/data_r.csv")
PROFILES: dict[str, Profile] = {
    "flat": Profile(
        "flat",
        "demo/tiny.safetensors",
        "tiny",
        "demo/__init__.py",
        _FLAT_RENAME,
        "demo",
        wheel=True,
    ),
    "src": Profile(
        "src",
        "src/sampleproject_hatchling/tiny.safetensors",
        "tiny",
        "src/sampleproject_hatchling/__init__.py",
        (
            "src/sampleproject_hatchling/data.csv",
            "src/sampleproject_hatchling/data_r.csv",
        ),
        "src/sampleproject_hatchling",
        wheel=True,
    ),
    "setuptools": Profile(
        "setuptools",
        None,
        None,
        "src/sampleproject_setuptools/__init__.py",
        (
            "src/sampleproject_setuptools/data.csv",
            "src/sampleproject_setuptools/data_r.csv",
        ),
        "src/sampleproject_setuptools",
        # A setuptools build writes *.egg-info into the project: not a
        # read-only step, so no wheel steps here.
        wheel=False,
    ),
    "stems": Profile(
        "stems",
        "demo/a/m.safetensors",
        "m",
        "demo/__init__.py",
        _FLAT_RENAME,
        "demo",
        wheel=True,
        shared_stem=True,
        models=("demo/a/m.safetensors", "demo/b/m.safetensors"),
    ),
    "intree": Profile(
        "intree",
        "demo/tiny.safetensors",
        "tiny",
        "demo/__init__.py",
        _FLAT_RENAME,
        "demo",
        wheel=True,
        in_tree="demo/reg.json",
    ),
    # The registry root is above the project (`id generate .` at the root).
    "monorepo": Profile(
        "monorepo",
        "pkgs/demo/demo/tiny.safetensors",
        "tiny",
        "pkgs/demo/demo/__init__.py",
        ("pkgs/demo/demo/data.csv", "pkgs/demo/demo/data_r.csv"),
        "pkgs/demo/demo",
        wheel=True,
        subdir="pkgs/demo",
        # A wheel or sdist read alone has no project directory to prefix
        # its paths with: nothing to look up under the root above it.
        # `embed` names the project, so its members are prefixed.
        unsupported=tuple(
            (op, "no project directory to prefix its paths (registry above it)")
            for op in ("sdist", "wheel")
        ),
    ),
    # The model, data and scripts live in sibling directories: the loom
    # scripts run from scripts/ and name them `../models/m.safetensors`.
    "subdir": Profile(
        "subdir",
        "models/m.safetensors",
        "m",
        "demo/__init__.py",
        _FLAT_RENAME,
        "demo",
        wheel=True,
        loom_dir="scripts",
    ),
}
_BUILDERS = {
    "flat": _flat,
    "src": _src,
    "setuptools": _setuptools,
    "stems": _stems,
    "intree": _in_tree,
    "monorepo": _monorepo,
    "subdir": _subdir,
}
_LOCK = threading.Lock()


def fixture_dir(name: str) -> Path:
    """The pristine project of profile *name*, built on first use under
    the run's shared fixtures root. Never modify it."""
    root = _fixtures.get().root / "order" / name
    with _LOCK:
        if not root.exists():
            staging = root.with_name(f"{name}.partial")
            shutil.rmtree(staging, ignore_errors=True)
            _BUILDERS[name](staging)
            staging.rename(root)
    return root
