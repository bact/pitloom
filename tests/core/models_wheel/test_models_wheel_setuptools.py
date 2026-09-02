# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for setuptools-backed wheel file discovery
(:mod:`pitloom.core._models_wheel_setuptools`).

See also: tests/core/models_wheel/test_models_wheel_dispatch.py for
the facade-level backend-dispatch/fallback-warning tests.
"""

import logging
import sys
from pathlib import Path
from types import ModuleType

import pytest

from pitloom.core._models_wheel_setuptools import (
    _dedupe_by_distribution_path,
    _distribution_path,
    _isolated_sys_modules,
    _load_distribution,
    _setup_py_packaging_kwargs,
    discover,
)
from pitloom.core._models_wheel_types import IncludedFile

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "projects"
PACKAGES_FIND_FIXTURE = FIXTURES / "sampleproject-setuptools"
PACKAGE_DATA_FIXTURE = FIXTURES / "sampleproject-setuptools-data"
ZEROCONFIG_FIXTURE = FIXTURES / "sampleproject-setuptools-zeroconfig"
MERGED_FIXTURE = FIXTURES / "sampleproject-setuptools-merged"


def test_discover_packages_find_where_regression() -> None:
    """Regression for the documented bug: a ``[options.packages.find]
    where = src`` layout must resolve distribution paths without the
    ``src/``/``where=`` prefix leaking in -- previously (via the
    always-Hatchling-heuristic code path) this was reported as
    ``src/sampleproject_setuptools/__init__.py`` instead of the correct
    ``sampleproject_setuptools/__init__.py``."""
    result = discover(PACKAGES_FIND_FIXTURE)

    assert result is not None
    distribution_paths = {f.distribution_path for f in result}
    assert distribution_paths == {"sampleproject_setuptools/__init__.py"}
    assert not any(p.startswith(("src/", "where")) for p in distribution_paths)


def test_discover_resolves_absolute_physical_paths() -> None:
    """``IncludedFile.path`` must be absolute, matching Hatchling's own
    ``IncludedFile.path`` contract -- the caller reads it after
    discovery's temporary chdir has already been undone."""
    result = discover(PACKAGES_FIND_FIXTURE)

    assert result is not None
    for included_file in result:
        assert Path(included_file.path).is_absolute()
        assert Path(included_file.path).is_file()


def test_discover_package_data_and_manifest_in() -> None:
    """``package_data`` (explicit glob) and ``include_package_data`` +
    ``MANIFEST.in`` (manifest-analysis path) are both resolved -- the
    ``.py`` module, the ``package_data``-globbed ``.json``, and the
    MANIFEST.in-only ``.txt`` (not matched by the ``*.json`` glob)."""
    result = discover(PACKAGE_DATA_FIXTURE)

    assert result is not None
    distribution_paths = {f.distribution_path for f in result}
    assert distribution_paths == {
        "sampleproject_setuptools_data/__init__.py",
        "sampleproject_setuptools_data/data.json",
        "sampleproject_setuptools_data/notes.txt",
    }


def test_discover_package_data_leaves_no_egg_info_behind() -> None:
    """The manifest-analysis path (``include_package_data``) must not
    mutate the fixture directory -- ``egg_base`` redirection to a temp
    directory is what makes this a safe, read-only discovery pass."""
    before = set(PACKAGE_DATA_FIXTURE.rglob("*"))

    result = discover(PACKAGE_DATA_FIXTURE)

    assert result is not None
    after = set(PACKAGE_DATA_FIXTURE.rglob("*"))
    assert after == before, "discovery must not leave any new file/dir behind"


def test_discover_zero_config_pep621_auto_discovery() -> None:
    """Regression: a bare PEP 621 project (``[project]`` only, no
    ``[tool.setuptools]`` at all) must resolve via setuptools' own
    zero-config auto-discovery (``Distribution.set_defaults()``), not
    resolve to an empty file list. ``apply_configuration()`` alone
    does not trigger auto-discovery -- ``Distribution.run_command()``
    normally does, but discovery never runs a real command, so this
    must be triggered explicitly."""
    result = discover(ZEROCONFIG_FIXTURE)

    assert result is not None
    distribution_paths = {f.distribution_path for f in result}
    assert distribution_paths == {"sampleproject_setuptools_zeroconfig/__init__.py"}


def test_discover_succeeds_on_legacy_table_form_license(tmp_path: Path) -> None:
    """Regression: a project using PEP 621's original ``project.license``
    TOML-table form (``{text = "..."}``), a ``tool.setuptools.license-files``
    key, and a legacy ``License ::`` trove classifier -- all superseded by
    PEP 639 but still common in real, unmigrated projects (e.g. requests
    2.34.2, see ``tests/fixtures/real-world-projects/setuptools/``) --
    must still resolve successfully.

    setuptools>=77 warns (never raises outside pytest's own
    ``filterwarnings = ["error"]``) on each of these forms during
    ``apply_configuration()``; without the scoped
    ``SetuptoolsDeprecationWarning`` ignore entry in this project's own
    pytest config, this test fails even though real (non-pytest) usage
    of ``discover()`` never did."""
    (tmp_path / "pyproject.toml").write_text(
        "[build-system]\n"
        'requires = ["setuptools"]\n'
        'build-backend = "setuptools.build_meta"\n\n'
        "[project]\n"
        'name = "pkg"\n'
        'version = "0.1.0"\n'
        'license = {text = "Apache-2.0"}\n'
        'classifiers = ["License :: OSI Approved :: Apache Software License"]\n\n'
        "[tool.setuptools]\n"
        'license-files = ["LICENSE"]\n',
        encoding="utf-8",
    )
    (tmp_path / "LICENSE").write_text("Apache-2.0\n", encoding="utf-8")
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")

    result = discover(tmp_path)

    assert result is not None
    assert {f.distribution_path for f in result} == {"pkg/__init__.py"}


def test_discover_merges_setup_cfg_and_pyproject_toml() -> None:
    """Regression: ``packages``/``package_dir`` from ``setup.cfg`` and
    ``package-data`` from ``pyproject.toml``'s ``[tool.setuptools]`` are
    both applied to the same ``Distribution`` -- neither file alone
    would resolve this fixture's full file list."""
    result = discover(MERGED_FIXTURE)

    assert result is not None
    distribution_paths = {f.distribution_path for f in result}
    assert distribution_paths == {
        "sampleproject_setuptools_merged/__init__.py",
        "sampleproject_setuptools_merged/notes.txt",
    }


def test_distribution_path_top_level_module_has_no_leading_slash() -> None:
    """Regression: a top-level ``py_modules``/``package_data`` entry
    (empty ``package``) must not produce a leading-slash distribution
    path -- ``f"{''}/{filename}"`` would naively yield ``"/filename"``."""
    assert _distribution_path("", "foo.py") == "foo.py"


def test_distribution_path_normalizes_backslashes() -> None:
    """Regression: a backslash reaching *package* (a malformed
    ``packages``/``package_dir`` entry, not necessarily only a Windows
    artifact) is normalized to a forward slash, not left as-is."""
    assert _distribution_path("foo\\bar", "x.py") == "foo/bar/x.py"


def test_dedupe_by_distribution_path_drops_later_duplicate(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression: a ``package_data`` glob overlapping a ``.py`` module
    already found by module discovery must not produce two
    ``IncludedFile`` entries for the same ``distribution_path`` -- that
    would corrupt the Merkle root (each leaf hash counted twice). Both
    scans resolve physical paths from the same ``src_dir`` (see
    ``_discover_module_files``/``_discover_data_files``), so a benign
    overlap like this always shares the same source ``path`` too -- no
    warning, since nothing is actually ambiguous here."""
    module_entry = IncludedFile(path="/src/pkg/x.py", distribution_path="pkg/x.py")
    data_entry = IncludedFile(path="/src/pkg/x.py", distribution_path="pkg/x.py")

    with caplog.at_level(logging.WARNING):
        result = _dedupe_by_distribution_path([module_entry, data_entry], Path("/proj"))

    assert result == [module_entry]
    assert caplog.records == []


def test_dedupe_by_distribution_path_warns_on_genuine_collision(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Two *different* source files resolving to the same
    ``distribution_path`` (e.g. overlapping ``package_dir`` entries) is a
    real misconfiguration silently shrinking the wheel's file set --
    unlike the benign glob-overlap case, this must be logged."""
    first = IncludedFile(path="/src/pkg_a/x.py", distribution_path="pkg/x.py")
    second = IncludedFile(path="/src/pkg_b/x.py", distribution_path="pkg/x.py")

    with caplog.at_level(logging.WARNING):
        result = _dedupe_by_distribution_path([first, second], Path("/proj"))

    assert result == [first]
    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "/src/pkg_a/x.py" in message
    assert "/src/pkg_b/x.py" in message
    assert "pkg/x.py" in message


def test_setup_py_packaging_kwargs_detects_only_relevant_names(
    tmp_path: Path,
) -> None:
    """Regression, found real-world validating against boto3 and cffi:
    setup.py passing ``package_data``/``packages`` imperatively (even as
    a non-literal ``find_packages()`` call, which the metadata
    extractor's own AST helper can't resolve to a value) must still be
    detected by name -- while an unrelated kwarg like ``install_requires``
    is not."""
    setup_py = tmp_path / "setup.py"
    setup_py.write_text(
        "from setuptools import find_packages, setup\n"
        "setup(\n"
        '    name="pkg",\n'
        "    packages=find_packages(),\n"
        '    package_data={"pkg": ["*.json"]},\n'
        '    install_requires=["other"],\n'
        ")\n",
        encoding="utf-8",
    )
    assert _setup_py_packaging_kwargs(setup_py) == ["package_data", "packages"]


def test_setup_py_packaging_kwargs_no_setup_call_returns_empty(
    tmp_path: Path,
) -> None:
    """No ``setup()``/``setuptools.setup()`` call in the file (or no
    file, or a syntax error) is not this function's problem -- an empty
    list, not an exception."""
    setup_py = tmp_path / "setup.py"
    setup_py.write_text("print('not a real setup.py')\n", encoding="utf-8")
    assert _setup_py_packaging_kwargs(setup_py) == []
    assert _setup_py_packaging_kwargs(tmp_path / "missing.py") == []


def test_setup_py_packaging_kwargs_no_false_positive_on_metadata_only(
    tmp_path: Path,
) -> None:
    """Regression: a ``setup()`` call passing only ordinary metadata
    kwargs (``name=``/``version=``, present in nearly every real-world
    ``setup.py``) must not be flagged -- proves the detector isn't
    matching on kwarg presence in general, only on the specific
    packaging-relevant names."""
    setup_py = tmp_path / "setup.py"
    setup_py.write_text(
        "from setuptools import setup\n"
        'setup(name="pkg", version="1.0.0", description="just metadata")\n',
        encoding="utf-8",
    )
    assert _setup_py_packaging_kwargs(setup_py) == []


def test_setup_py_packaging_kwargs_inspects_call_past_an_unrelated_match(
    tmp_path: Path,
) -> None:
    """Regression: an unrelated ``.setup()``-named call earlier in the
    file (e.g. a logger/app configured before the real ``setup()`` call)
    must not stop the scan -- every matching call is inspected, not just
    the first one found by ``ast.walk``."""
    setup_py = tmp_path / "setup.py"
    setup_py.write_text(
        "import logging\n"
        "from setuptools import setup\n"
        "logger = logging.getLogger(__name__)\n"
        "logger.setup()\n"
        'setup(name="pkg", packages=["pkg"])\n',
        encoding="utf-8",
    )
    assert _setup_py_packaging_kwargs(setup_py) == ["packages"]


def test_setup_py_packaging_kwargs_flags_kwargs_unpacking(
    tmp_path: Path,
) -> None:
    """Regression: ``setup(**config)`` can hide a packaging-relevant
    argument the static scan has no way to inspect -- the unpack itself
    must be reported (as ``"**kwargs"``) rather than silently treated as
    "no packaging kwargs present"."""
    setup_py = tmp_path / "setup.py"
    setup_py.write_text(
        "from setuptools import setup\nconfig = {'name': 'pkg'}\nsetup(**config)\n",
        encoding="utf-8",
    )
    assert _setup_py_packaging_kwargs(setup_py) == ["**kwargs"]


def test_discover_warns_when_setup_py_overrides_packaging_imperatively(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: a project with resolvable static config (here,
    zero-config auto-discovery) *and* a setup.py that also passes
    ``package_data`` imperatively must still return the statically
    resolved file list (it's the best available, and often still
    correct for the ``.py`` modules) -- but with a ``WARNING:`` that it
    may be incomplete, since setup.py is never executed to check."""
    tmp_path_name = "pkgwarn"
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "setuptools.build_meta"\n\n'
        f'[project]\nname = "{tmp_path_name}"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    pkg_dir = tmp_path / tmp_path_name
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "setup.py").write_text(
        "from setuptools import setup\nsetup(package_data={'pkgwarn': ['*.json']})\n",
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        result = discover(tmp_path)

    assert result is not None
    assert {f.distribution_path for f in result} == {"pkgwarn/__init__.py"}
    assert "package_data" in caplog.text
    assert "imperatively" in caplog.text


def test_discover_returns_none_without_static_config(tmp_path: Path) -> None:
    """A setuptools project with neither ``[tool.setuptools]`` in
    ``pyproject.toml`` nor a ``setup.cfg`` (packages only resolvable by
    executing an imperative ``setup.py``) is out of scope -- ``None``
    signals the caller to fall back, not "found zero files"."""
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "setuptools.build_meta"\n',
        encoding="utf-8",
    )
    (tmp_path / "setup.py").write_text(
        'from setuptools import setup\nsetup(name="pkg", version="1.0.0")\n',
        encoding="utf-8",
    )

    assert discover(tmp_path) is None


def test_discover_returns_none_and_logs_on_introspection_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Any setuptools-introspection failure is treated the same as "no
    static config" -- ``None``, plus a logged warning with the failure
    detail (the facade logs its own generic fallback warning on top)."""
    (tmp_path / "setup.cfg").write_text(
        "[metadata]\nname = pkg\nversion = 1.0.0\n\n[options]\npackages = find:\n",
        encoding="utf-8",
    )

    def _broken_finalize(self: object) -> None:
        del self
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "setuptools.command.build_py.build_py.finalize_options", _broken_finalize
    )

    with caplog.at_level(logging.WARNING):
        result = discover(tmp_path)

    assert result is None
    assert "boom" in caplog.text


def test_discover_returns_none_and_logs_on_ambiguous_flat_layout(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: a zero-config PEP 621 project with two top-level
    package-looking directories and no explicit ``packages``/
    ``py_modules`` is ambiguous to setuptools' own auto-discovery, which
    raises ``PackageDiscoveryError`` from ``set_defaults()`` -- this
    must be caught and turned into ``None`` plus an actionable warning
    (not left to the generic "introspection failure" branch, and not
    left uncaught)."""
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "setuptools.build_meta"\n\n'
        '[project]\nname = "ambig"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    for pkg in ("pkg_a", "pkg_b"):
        pkg_dir = tmp_path / pkg
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        result = discover(tmp_path)

    assert result is None
    assert "could not auto-discover packages unambiguously" in caplog.text


def _make_dynamic_version_project(root: Path, version_value: str) -> None:
    """A project whose version is only resolvable via a real import (not
    setuptools' static AST literal-eval) -- the assigned value is a
    function call, not a literal."""
    root.mkdir()
    (root / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "setuptools.build_meta"\n\n'
        '[project]\nname = "pkgx"\ndynamic = ["version"]\n\n'
        '[tool.setuptools.dynamic]\nversion = {attr = "_probe_mod.__version__"}\n',
        encoding="utf-8",
    )
    (root / "_probe_mod.py").write_text(
        f'def _compute() -> str:\n    return "{version_value}"\n\n'
        "__version__ = _compute()\n",
        encoding="utf-8",
    )


def test_load_distribution_does_not_leak_dynamic_import_across_projects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two projects processed in the same process, both resolving a
    dynamic ``attr:`` version via a real import (forced by a non-literal
    value) and both declaring a same-named module, must each resolve
    their OWN version -- not one cached in ``sys.modules`` from the
    other project's earlier call."""
    project_a = tmp_path / "a"
    project_b = tmp_path / "b"
    _make_dynamic_version_project(project_a, "1.0.0")
    _make_dynamic_version_project(project_b, "2.0.0")

    monkeypatch.chdir(project_a)
    with _isolated_sys_modules(project_a):
        dist_a = _load_distribution(project_a, None)
    assert "_probe_mod" not in sys.modules

    monkeypatch.chdir(project_b)
    with _isolated_sys_modules(project_b):
        dist_b = _load_distribution(project_b, None)
    assert "_probe_mod" not in sys.modules

    assert dist_a is not None
    assert dist_b is not None
    assert dist_a.metadata.version == "1.0.0"
    assert dist_b.metadata.version == "2.0.0"


def test_isolated_sys_modules_removes_only_newly_imported_modules(
    tmp_path: Path,
) -> None:
    """The context manager removes module names added to ``sys.modules``
    while it's active *and* loaded from beneath the given project
    directory, but leaves a name that was already present before it
    started alone -- using fake module entries (not a real import) to
    keep this deterministic regardless of what else the process has
    already imported."""
    pre_existing = "_pitloom_test_pre_existing_module"
    newly_added = "_pitloom_test_newly_added_module"
    sys.modules[pre_existing] = ModuleType(pre_existing)
    try:
        with _isolated_sys_modules(tmp_path):
            added_module = ModuleType(newly_added)
            added_module.__file__ = str(tmp_path / "pkg" / "mod.py")
            sys.modules[newly_added] = added_module
            assert newly_added in sys.modules

        assert newly_added not in sys.modules
        assert pre_existing in sys.modules
    finally:
        sys.modules.pop(pre_existing, None)
        sys.modules.pop(newly_added, None)


def test_isolated_sys_modules_leaves_modules_outside_project_dir_alone(
    tmp_path: Path,
) -> None:
    """Regression: a module newly imported during discovery but loaded
    from *outside* the target project directory (e.g. a third-party
    dependency pulled in transitively by ``attr:`` resolution) must not
    be evicted from ``sys.modules`` -- only the target project's own
    modules are safe to assume are re-importable/re-cacheable per
    project."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    outside_module = "_pitloom_test_outside_project_module"
    file_less_module = "_pitloom_test_no_file_module"
    try:
        with _isolated_sys_modules(project_dir):
            added_outside = ModuleType(outside_module)
            added_outside.__file__ = str(tmp_path / "elsewhere" / "mod.py")
            sys.modules[outside_module] = added_outside
            sys.modules[file_less_module] = ModuleType(file_less_module)

        assert outside_module in sys.modules
        assert file_less_module in sys.modules
    finally:
        sys.modules.pop(outside_module, None)
        sys.modules.pop(file_less_module, None)


def test_isolated_sys_modules_treats_unresolvable_module_file_as_outside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: if a newly-imported module's ``__file__`` can't be
    resolved (a broken symlink loop, or another ``OSError``/
    ``RuntimeError``/``ValueError`` from ``Path.resolve()``), the module
    is treated as outside *project_dir* (left alone) rather than
    crashing discovery."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    unresolvable_module = "_pitloom_test_unresolvable_module"
    bad_path = str(tmp_path / "broken" / "mod.py")
    real_resolve = Path.resolve

    def _flaky_resolve(self: Path, *args: object, **kwargs: object) -> Path:
        if str(self) == bad_path:
            raise OSError("simulated broken symlink")
        return real_resolve(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "resolve", _flaky_resolve)

    try:
        with _isolated_sys_modules(project_dir):
            added = ModuleType(unresolvable_module)
            added.__file__ = bad_path
            sys.modules[unresolvable_module] = added

        assert unresolvable_module in sys.modules
    finally:
        sys.modules.pop(unresolvable_module, None)
