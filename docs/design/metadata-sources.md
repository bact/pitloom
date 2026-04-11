---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Metadata sources — design notes

This document records research into how other SBOM and SCA tools handle
Python package metadata extraction, and derives design guidance for
pitloom's planned enhancements.

## How Trivy handles Python metadata

**Repository:** <https://github.com/aquasecurity/trivy>

Trivy's Python coverage focuses on **installed packages** and **lock files**
rather than source trees.  It does not parse `setup.py` or call PEP 517
hooks during normal SBOM generation.

### Priority order (highest to lowest)

1. **`.dist-info/METADATA`** (wheel installs) — RFC 822-style email header
   format; parsed by Trivy's `packaging` parser.
2. **`.egg-info/PKG-INFO`** or **`EGG-INFO/PKG-INFO`** (egg / editable installs).
3. **Lock files** — `poetry.lock`, `Pipfile.lock`, `uv.lock`,
   `requirements.txt` — for declared (not necessarily installed) dependencies.
4. **`pyproject.toml`** — parsed statically for `[project]` (PEP 621) and
   `[tool.poetry]` sections; no execution of the build backend.

### Key design choices

- **No `setup.py` / `setup.cfg` parsing.** Trivy treats installed metadata as
  canonical; source file parsing is considered unreliable for vulnerability
  scanning.
- **No PEP 517 execution.** Running arbitrary build code is a security risk
  and a performance cost. Trivy's threat model centres on container image
  scanning where packages are already installed.
- **Language-agnostic architecture.** The same pipeline handles PyPI, npm,
  Maven, etc. Per-language parsers produce a uniform `Package` struct.

### Implications for pitloom

Trivy's approach is appropriate for *scanning installed environments*.
Pitloom operates at *build time* (source tree + build hook), so it has
access to information Trivy does not — but it should follow Trivy's lead
in treating `.dist-info/METADATA` as the highest-fidelity source when
operating in an installed context (e.g., the CLI run against an editable
install or a virtual environment).

---

## How Syft handles Python metadata

**Repository:** <https://github.com/anchore/syft>

Syft uses a **pluggable cataloger architecture** with different catalogers
selected depending on the scan target (container image vs. directory).

### Catalogers for Python

| Cataloger | Trigger | Sources used |
| :--- | :--- | :--- |
| `python-installed-package-cataloger` | Any scan | `.dist-info/METADATA`, `.egg-info/PKG-INFO` |
| `python-package-cataloger` | Directory scans only | `requirements.txt`, `pyproject.toml`, `poetry.lock`, `Pipfile.lock` |

### Key design choices

- **Installed packages are primary.** The installed cataloger runs for every
  scan type; the source-file cataloger is directory-only.
- **No `setup.py` execution.** Syft's maintainers explicitly ruled out
  executing `setup.py` due to the complexity of tracing dynamic dependencies
  and the security risk of running arbitrary code.
- **Static parsing throughout.** Lock files and `pyproject.toml` are
  parsed without invoking the build backend.
- **Dual-mode operation.** In container image scans Syft works from installed
  metadata; in source directory scans it reads declared dependencies. Pitloom
  follows a similar pattern: build-hook path (installed, post-wheel) vs. CLI
  path (source tree).

### Implications for pitloom

Syft's cataloger split maps cleanly onto pitloom's two paths:

| Pitloom path | Syft analogue | Primary metadata source |
| :--- | :--- | :--- |
| Hatchling / setuptools build hook | installed-package cataloger | `.dist-info/METADATA` (inside wheel) |
| CLI (`loom <project_dir>`) | source-file cataloger | `pyproject.toml` → `setup.cfg` → `setup.py` |

The CLI should additionally consider checking for an existing `.dist-info` or
`.egg-info` directory (from an editable install) as a high-fidelity supplement
before falling back to raw source parsing.

---

## PEP 517 — `prepare_metadata_for_build_wheel`

**Reference:** <https://peps.python.org/pep-0517/>

### What it does

PEP 517 defines a set of hooks that a build frontend (pip, build) calls on
a build backend (setuptools, Hatchling, Flit …) via a subprocess interface:

```text
build_wheel(wheel_directory, config_settings, metadata_directory)
prepare_metadata_for_build_wheel(metadata_directory, config_settings)
build_sdist(sdist_directory, config_settings)
```

`prepare_metadata_for_build_wheel` builds only the `.dist-info` directory
(containing `METADATA`, `WHEEL`, `top_level.txt`, `entry_points.txt`, etc.)
without compiling or packaging the rest of the project. The backend returns
the directory name, e.g. `mypackage-1.0.dist-info`.

### Why it matters for pitloom

It is the only **backend-agnostic, dynamic-metadata-aware** mechanism that:

- Works for setuptools, Hatchling, Flit, PDM, Meson-Python, and any future
  PEP 517-compliant backend without pitloom needing per-backend logic.
- Resolves version strings set via Git tags, `importlib.metadata`, or any
  other runtime technique that static AST parsing cannot handle.
- Produces the same `METADATA` file that `pip install` would generate, making
  pitloom's extracted metadata identical to what end-users and SCA tools see.

### Proposed integration

```text
Priority order (planned — highest to lowest)
────────────────────────────────────────────
1. PEP 517  prepare_metadata_for_build_wheel   ← future, opt-in
2. .dist-info/METADATA or .egg-info/PKG-INFO   ← future (installed env)
3. pyproject.toml [project]                    ← implemented
4. setup.cfg [metadata] / [options]            ← implemented
5. setup.py setup() literal arguments          ← implemented
```

### Implementation sketch

```python
import subprocess
import tempfile
from pathlib import Path

def prepare_metadata_via_pep517(project_dir: Path) -> Path | None:
    """Call prepare_metadata_for_build_wheel and return the .dist-info path."""
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import build.env, sys; "
                "from build._builder import _BuildBackend; "
                "..."
            ],
            cwd=str(project_dir),
            capture_output=True,
        )
        ...
```

In practice pitloom should use the `build` library's
`ProjectBuilder.prepare_metadata_for_build_wheel()` rather than invoking the
backend directly, to get correct environment isolation and wheel directory
handling.

### Tradeoffs

| Concern | Notes |
| :--- | :--- |
| **Accuracy** | Highest possible — identical to what pip installs. |
| **Side effects** | May run arbitrary build-backend code. Backends can have network access, write files, etc. |
| **Performance** | Slower than static parsing; adds a subprocess per project. |
| **Isolation** | Should be run in an isolated environment (`--no-build-isolation` or a fresh venv) to avoid polluting the user's environment. |
| **Availability** | Requires the build backend and its dependencies to be installed. |

### Recommended adoption path

1. **Opt-in flag** — add `[tool.pitloom] pep517-metadata = true` (default
   `false`). When enabled, pitloom calls `prepare_metadata_for_build_wheel`
   and uses its output as a higher-priority source.
2. **Graceful fallback** — if the call fails (backend not installed, hook not
   implemented), log a warning and fall back to static sources.
3. **Cache result** — write the `.dist-info` directory to the project's build
   cache so repeated `loom` invocations do not re-run the backend.

---

## Recommended metadata source priority for pitloom

Drawing from the Trivy, Syft, and PEP 517 research, the recommended long-term
priority order for `_load_project_metadata()` is:

```text
1. PEP 517 prepare_metadata_for_build_wheel   [opt-in; future]
   └─ parses the resulting METADATA file via email.parser

2. Installed .dist-info/METADATA              [future]
   └─ present when running inside an editable install or venv

3. pyproject.toml [project]                   [implemented]
   └─ read_pyproject() → ProjectMetadata

4. setup.cfg [metadata] / [options]           [implemented]
   └─ read_setup_cfg() → ProjectMetadata

5. setup.py setup() literal arguments         [implemented]
   └─ read_setup_py() (AST) → ProjectMetadata
```

Sources 3–5 are combined via `merge_metadata(primary, secondary)` so gaps at
one level are filled by the next without overwriting already-resolved fields.
Sources 1–2 (when implemented) will be treated the same way — as a
higher-priority primary passed to `merge_metadata`.

The `METADATA` file format (RFC 822 / `email.parser`) is straightforward and
already handled by `packaging.metadata.Metadata` in the `packaging` library,
which pitloom's dependency `pyproject-metadata` transitively includes.

---

## See also

- [docs/implementation/setuptools-support.md](../implementation/setuptools-support.md)
  implementation notes for the static `setup.cfg` / `setup.py` extractors
- [docs/design/hatchling-build-hook.md](hatchling-build-hook.md) —
  PEP 770 wheel embedding via the Hatchling hook
- [docs/design/metadata-provenance.md](metadata-provenance.md) —
  provenance tracking per field
