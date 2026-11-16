# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The credential policy is threaded through every route to the SBOM, and a
refused SBOM leaves the ID registry as it was.

Every public SBOM-producing entry point takes ``credentials``, and it is
united with the config's ``accept-url-credentials``, never replacing it. The
SBOM is serialised (and so checked) before the registry is saved and before
the output is written.

See also: tests/test_credential_surfaces.py (the surfaces and their streams),
tests/export/test_spdx3_credentials.py (the check itself) and
tests/core/test_credential_policy.py (the policy).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import dataclasses
import inspect
import json
import re
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom import assemble, loom
from pitloom._loom_active_run import _ActiveRun
from pitloom.assemble import (
    embed_wheel_sbom,
    generate,
    generate_env_sbom,
    generate_git_project_sbom,
    generate_git_sbom,
    generate_merged_sbom,
    generate_model_sbom,
    generate_project_sbom,
    generate_pypi_sbom,
    generate_pypi_sbom_with_download,
    generate_wheel_sbom,
    generate_wheel_sbom_with_metadata,
)
from pitloom.assemble._model_generator import enrich_model
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import ConfigOverrides
from pitloom.core.credential_policy import CredentialPolicy
from pitloom.core.project import ProjectMetadata
from pitloom.id_registry import IdRegistry
from pitloom.messages import code_of
from tests._author_routes import hook_sbom, write_wheel
from tests.cli.shared import FRAGMENT_FIXTURE

pytestmark = pytest.mark.platform

_REFUSED = "credentials-unsafe/refused"
_WHEN = "2026-01-01T00:00:00Z"
_NS = "https://ids.example/ns"
HOME = "https://b:T0KEN@e.example/h?api_key=S3CRET"
DEP = "foo @ https://a:S3CRET@h.example/x.whl?token=T0KEN"
#: A fingerprint as a refusal prints it.
_OFFERED = re.compile(r"--accept-url-credential (sha256:[0-9a-f]{16})")

#: Every public entry point that writes an SBOM or a fragment, by name.
ENTRY_POINTS: dict[str, Callable[..., object]] = {
    "generate": generate,
    "generate_project_sbom": generate_project_sbom,
    "generate_wheel_sbom": generate_wheel_sbom,
    "generate_wheel_sbom_with_metadata": generate_wheel_sbom_with_metadata,
    "generate_env_sbom": generate_env_sbom,
    "generate_merged_sbom": generate_merged_sbom,
    "generate_model_sbom": generate_model_sbom,
    "enrich_model": enrich_model,
    "generate_git_sbom": generate_git_sbom,
    "generate_git_project_sbom": generate_git_project_sbom,
    "generate_pypi_sbom_with_download": generate_pypi_sbom_with_download,
    "generate_pypi_sbom": generate_pypi_sbom,
    "loom.Run": loom.Run.__init__,
    "_ActiveRun": _ActiveRun.__init__,
}


@pytest.mark.parametrize("name", sorted(ENTRY_POINTS))
def test_every_entry_point_takes_credentials(name: str) -> None:
    parameter = inspect.signature(ENTRY_POINTS[name]).parameters.get("credentials")
    assert parameter is not None, name
    assert parameter.default is None


def test_every_public_generator_is_listed() -> None:
    """A new ``generate*``/``enrich*`` of ``pitloom.assemble`` joins the
    list above (an embed takes ``ConfigOverrides.credentials`` instead)."""
    found = {
        name
        for name in dir(assemble)
        if name.startswith(("generate", "enrich")) and callable(getattr(assemble, name))
    }
    assert found <= set(ENTRY_POINTS), found - set(ENTRY_POINTS)
    assert "credentials" in {f.name for f in dataclasses.fields(ConfigOverrides)}


def _project(tmp: Path, accept: str = "") -> Path:
    proj = tmp / "proj"
    (proj / "testpkg").mkdir(parents=True, exist_ok=True)
    (proj / "testpkg" / "__init__.py").write_text("", encoding="utf-8")
    (proj / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n'
        "[project]\nname = 'testpkg'\nversion = '0.1.0'\n"
        f"dependencies = ['{DEP}']\n[project.urls]\nHomepage = '{HOME}'\n"
        "[tool.hatch.metadata]\nallow-direct-references = true\n"
        f"[tool.pitloom]\n{accept}",
        encoding="utf-8",
    )
    return proj


def _wheel(tmp: Path) -> Path:
    metadata = (
        "Metadata-Version: 2.4\nName: demo\nVersion: 1.0\n"
        f"Project-URL: Homepage, {HOME}\nRequires-Dist: {DEP}\n"
    )
    return write_wheel(tmp, metadata)


Route = Callable[[Path, Path, CredentialPolicy | None, PitloomConfig | None], str]


def _route_project(
    tmp: Path,
    registry: Path,
    credentials: CredentialPolicy | None,
    config: PitloomConfig | None,
) -> str:
    return generate_project_sbom(
        _project(tmp),
        output_path=tmp / "o.json",
        id_registry=registry,
        offline=True,
        credentials=credentials,
        pitloom_config=config,
        project_metadata=None,
    )


def _route_wheel(
    tmp: Path,
    registry: Path,
    credentials: CredentialPolicy | None,
    config: PitloomConfig | None,
) -> str:
    return generate_wheel_sbom(
        _wheel(tmp),
        output_path=tmp / "o.json",
        id_registry=registry,
        offline=True,
        credentials=credentials,
        pitloom_config=config,
    )


def _route_env(
    tmp: Path,
    registry: Path,
    credentials: CredentialPolicy | None,
    config: PitloomConfig | None,
) -> str:
    return generate_env_sbom(
        output_path=tmp / "o.json",
        id_registry=registry,
        offline=True,
        credentials=credentials,
        pitloom_config=config,
    )


ROUTES: dict[str, Route] = {
    "project": _route_project,
    "wheel": _route_wheel,
    "env": _route_env,
}


@pytest.fixture(autouse=True, name="_stub_env")
def _stub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The installed environment, with a homepage holding a credential: what
    ``pipdeptree`` and the installed packages cannot be made to say."""
    env = ProjectMetadata(name="envproj", version="1", urls={"Homepage": HOME})
    monkeypatch.setattr(
        "pitloom.assemble._generators_env.read_environment", lambda: (env, [])
    )


def _registry(tmp: Path) -> Path:
    path = tmp / "ids.json"
    IdRegistry.new("demo", path, namespace=_NS).save()
    return path


def _offered(text: str) -> list[str]:
    return sorted(set(_OFFERED.findall(text)))


@pytest.mark.parametrize("route", sorted(ROUTES))
def test_a_refused_sbom_leaves_the_registry_and_the_output_alone(
    route: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    registry = _registry(tmp_path)
    before = registry.read_bytes()
    with pytest.raises(ValueError) as caught:
        ROUTES[route](tmp_path, registry, None, None)
    assert code_of(caught.value) == _REFUSED
    assert registry.read_bytes() == before
    assert not (tmp_path / "o.json").exists()
    # Not vacuous: the same run with the credentials allowed does save ids.
    ROUTES[route](tmp_path, registry, CredentialPolicy(allow_all=True), None)
    assert registry.read_bytes() != before
    assert (tmp_path / "o.json").is_file()


def _fingerprints(
    route: str, tmp: Path, registry: Path, caplog: pytest.LogCaptureFixture
) -> list[str]:
    with pytest.raises(ValueError):
        ROUTES[route](tmp, registry, None, None)
    return _offered(caplog.text)


@pytest.mark.parametrize("route", ["project", "wheel"])
def test_the_keyword_is_united_with_the_config_never_replacing_it(
    route: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Two values hold a credential: the config accepts one, the keyword the
    other, so the run needs both lists."""
    monkeypatch.chdir(tmp_path)
    registry = _registry(tmp_path)
    first, second = _fingerprints(route, tmp_path, registry, caplog)
    config = PitloomConfig(accept_url_credentials=(first,))
    only_config = CredentialPolicy()
    only_keyword = CredentialPolicy(accepted=frozenset({second}))
    for given, policy in ((config, only_config), (None, only_keyword)):
        with pytest.raises(ValueError) as caught:
            ROUTES[route](tmp_path, registry, policy, given)
        assert code_of(caught.value) == _REFUSED
    ROUTES[route](tmp_path, registry, only_keyword, config)
    assert (tmp_path / "o.json").is_file()


def test_the_hook_reads_the_pyproject_list_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """``allow-url-credentials`` in ``pyproject.toml`` allows nothing; the
    ``accept-url-credentials`` list does."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError) as caught:
        hook_sbom(_project(tmp_path, "allow-url-credentials = true\n"))
    assert code_of(caught.value) == _REFUSED
    listed = ", ".join(f"'{fp}'" for fp in _offered(caplog.text))
    assert listed.count("sha256:") == 2
    sbom = hook_sbom(_project(tmp_path, f"accept-url-credentials = [{listed}]\n"))
    assert "S3CRET" in sbom


def test_a_loom_run_refuses_a_fragment_and_saves_no_model_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    registry = _registry(tmp_path)
    before = registry.read_bytes()
    model = tmp_path / "m.bin"
    model.write_bytes(b"weights")
    card = tmp_path / "croissant.json"
    card.write_text(
        '{"@context": {"@vocab": "https://schema.org/"}, "@type": "Dataset", '
        f'"name": "d", "url": "{HOME}"}}',
        encoding="utf-8",
    )
    out = tmp_path / "frags" / "a.json"

    def run(credentials: CredentialPolicy | None) -> None:
        with loom.run(out, id_registry=registry, credentials=credentials) as active:
            active.set_model("m", path=model)
            active.add_dataset("d", croissant=card)

    with pytest.raises(ValueError) as caught:
        run(None)
    assert code_of(caught.value) == _REFUSED
    assert registry.read_bytes() == before
    assert not out.parent.exists()
    run(CredentialPolicy(allow_all=True))
    assert out.is_file() and registry.read_bytes() != before


def test_merge_and_embed_take_the_policy_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The library merge takes ``credentials``; an embed takes it in its
    ``ConfigOverrides``, united with the config's list."""
    monkeypatch.chdir(tmp_path)
    fragments = tmp_path / "fragments"
    fragments.mkdir()
    data = json.loads(FRAGMENT_FIXTURE.read_text(encoding="utf-8"))
    for element in data["@graph"]:
        if "software_downloadLocation" in element:
            element["software_downloadLocation"] = HOME
    (fragments / "a.json").write_text(json.dumps(data), encoding="utf-8")
    allow = CredentialPolicy(allow_all=True)
    with pytest.raises(ValueError) as caught:
        generate_merged_sbom(fragments, output_path=tmp_path / "m.json")
    assert code_of(caught.value) == _REFUSED and not (tmp_path / "m.json").exists()
    assert "S3CRET" in generate_merged_sbom(fragments, credentials=allow)

    wheel = _wheel(tmp_path)
    with pytest.raises(ValueError) as caught:
        embed_wheel_sbom(wheel, overrides=ConfigOverrides(offline=True))
    assert code_of(caught.value) == _REFUSED
    with zipfile.ZipFile(wheel) as zf:
        assert not [n for n in zf.namelist() if "/sboms/" in n]
    overrides = ConfigOverrides(offline=True, credentials=allow)
    assert "S3CRET" in embed_wheel_sbom(wheel, overrides=overrides)[2]
