# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A secret planted in a project URL, a dependency URL, a dataset URL, an
ID registry namespace or a key reaches no SBOM, stdout, stderr, log record
or registry file, on every surface: ``loom generate`` (to a file and with
``-o -``), the library, the Hatchling hook, ``embed-wheel``, ``merge``, the
Croissant dataset route and the ID registry's command, library and file.

See also: tests/core/url_masking/test_url_masking_credentials.py (each sink),
tests/export/test_spdx3_strip.py (the SBOM strip) and
tests/id_registry/test_credentials_registry.py (the registry rule).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.__main__ import main
from pitloom.assemble import generate_project_sbom
from pitloom.assemble.spdx3.document import build_model
from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.dataset_metadata import DatasetReference
from pitloom.extract.dataset.croissant import read_croissant
from pitloom.id_registry import IdRegistry
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import code_of
from tests._author_routes import CREATED, hook_sbom, write_wheel
from tests.cli.shared import FRAGMENT_FIXTURE

pytestmark = pytest.mark.platform

SECRETS = ("S3CRET", "T0KEN")
_DEP = "foo @ https://a:S3CRET@h.example/x.whl?token=T0KEN"
_HOME = "https://b:T0KEN@e.example/h?api_key=S3CRET"
_NS = "https://u:S3CRET@ids.example/ns"
_WHEN = "2026-01-01T00:00:00Z"


def _leaks(*texts: str) -> list[str]:
    return [s for s in SECRETS for t in texts if s in t]


def _project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    (proj / "testpkg").mkdir(parents=True)
    (proj / "testpkg" / "__init__.py").write_text("", encoding="utf-8")
    (proj / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n'
        "[project]\nname = 'testpkg'\nversion = '0.1.0'\n"
        f"dependencies = ['{_DEP}']\n[project.urls]\nHomepage = '{_HOME}'\n"
        "[tool.hatch.metadata]\nallow-direct-references = true\n",
        encoding="utf-8",
    )
    return proj


def _cli(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    return main()


def _generate(tmp: Path, mp: pytest.MonkeyPatch) -> str:
    out = tmp / "o.json"
    argv = ["generate", str(_project(tmp)), "-o", str(out), "--offline"]
    assert _cli(argv + ["--creation-datetime", _WHEN], mp) == 0
    return out.read_text(encoding="utf-8")


def _stdout(tmp: Path, mp: pytest.MonkeyPatch) -> str:
    argv = ["generate", str(_project(tmp)), "-o", "-", "--offline"]
    assert _cli(argv + ["--creation-datetime", _WHEN], mp) == 0
    return ""  # the SBOM is on stdout, checked with it


def _library(tmp: Path, _mp: pytest.MonkeyPatch) -> str:
    out = tmp / "o.json"
    generate_project_sbom(_project(tmp), output_path=out, offline=True)
    return out.read_text(encoding="utf-8")


def _hook(tmp: Path, _mp: pytest.MonkeyPatch) -> str:
    return hook_sbom(_project(tmp))


def _embed_wheel(tmp: Path, mp: pytest.MonkeyPatch) -> str:
    metadata = (
        "Metadata-Version: 2.4\nName: demo\nVersion: 1.0\n"
        f"Project-URL: Homepage, {_HOME}\nRequires-Dist: {_DEP}\n"
    )
    wheel = write_wheel(tmp, metadata)
    argv = ["embed-wheel", str(wheel), "--offline", "--creation-datetime", _WHEN]
    assert _cli(argv, mp) == 0
    with zipfile.ZipFile(wheel) as zf:
        return "".join(
            zf.read(n).decode("utf-8") for n in zf.namelist() if "/sboms/" in n
        )


def _merge(tmp: Path, mp: pytest.MonkeyPatch) -> str:
    fragments = tmp / "fragments"
    fragments.mkdir()
    data = json.loads(FRAGMENT_FIXTURE.read_text(encoding="utf-8"))
    for element in data["@graph"]:
        if "software_downloadLocation" in element:
            element["software_downloadLocation"] = _HOME
    (fragments / "a.json").write_text(json.dumps(data), encoding="utf-8")
    shutil.copy(FRAGMENT_FIXTURE, fragments / "b.json")
    assert _cli(["merge", str(fragments), "-o", str(tmp / "o.json")], mp) == 0
    return (tmp / "o.json").read_text(encoding="utf-8")


def _croissant(tmp: Path, _mp: pytest.MonkeyPatch) -> str:
    card = tmp / "croissant.json"
    card.write_text(
        json.dumps(
            {
                "@context": {"@vocab": "https://schema.org/"},
                "@type": "Dataset",
                "name": "d",
                "url": "https://alice:S3CRET@data.example/d.csv?token=T0KEN",
            }
        ),
        encoding="utf-8",
    )
    dataset = DatasetReference(role="trainedOn", metadata=read_croissant(card))
    sbom = build_model(AiModelMetadata(name="m", datasets=[dataset]), CREATED)
    text = sbom.to_json()
    assert "download_url=https://data.example/d.csv" in text
    return text


_SURFACES: dict[str, Callable[[Path, pytest.MonkeyPatch], str]] = {
    "cli-generate": _generate,
    "cli-stdout": _stdout,
    "library": _library,
    "hook": _hook,
    "embed-wheel": _embed_wheel,
    "merge": _merge,
    "croissant": _croissant,
}


@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_no_planted_secret_reaches_the_sbom_or_a_stream(
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.chdir(tmp_path)
    with caplog.at_level(logging.INFO, logger="pitloom"):
        sbom = _SURFACES[surface](tmp_path, monkeypatch)
    out, err = capsys.readouterr()
    sbom = sbom or out
    assert "@graph" in sbom and ("e.example/h" in sbom or "data.example" in sbom)
    assert not _leaks(sbom, out, err, caplog.text)
    said = err + "".join(f"[{getattr(r, CODE_ATTR, '')}]" for r in caplog.records)
    assert "credentials-unsafe]" in said


def _registry_surfaces(tmp: Path, mp: pytest.MonkeyPatch) -> dict[str, object]:
    """Each registry surface given a credentialed namespace or key: its code
    (an exception's, else the exit status)."""
    found: dict[str, object] = {}
    calls: dict[str, Callable[[], object]] = {
        "library-new": lambda: IdRegistry.new("demo", namespace=_NS),
        "constructor": lambda: IdRegistry(namespace=_NS),
        "register": lambda: IdRegistry(namespace="https://h/ns").register(
            "ai_AIPackage", _HOME
        ),
    }
    for name, call in calls.items():
        with pytest.raises(ValueError) as caught:
            call()
        found[name] = code_of(caught.value)
    (tmp / "src").mkdir()
    (tmp / "src" / "a.py").write_text("x\n", encoding="utf-8")
    base = ["id", "generate", "--project-dir", str(tmp), "-o", str(tmp / "r.json")]
    with pytest.raises(SystemExit) as stopped:
        _cli(base + ["--namespace", _NS, str(tmp / "src")], mp)
    found["cli-namespace"] = stopped.value.code
    found["cli-key"] = _cli(base + ["-e", f"{_HOME}:ai_AIPackage", "src"], mp)
    (tmp / "bad.json").write_text(
        json.dumps({"version": 4, "namespace": _NS, "project_root": "."}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as caught:
        IdRegistry.load(tmp / "bad.json")
    found["file"] = code_of(caught.value)
    return found


def test_a_credentialed_namespace_or_key_is_refused_on_every_registry_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One refusal per surface, the library's coded as the command line's
    ``-e``; argparse (exit 2) and a malformed file keep their own code."""
    monkeypatch.chdir(tmp_path)
    found = _registry_surfaces(tmp_path, monkeypatch)
    _, err = capsys.readouterr()
    registry = "credentials-unsafe/registry"
    assert found == {
        "library-new": registry,
        "constructor": registry,
        "register": registry,
        "cli-namespace": 2,
        "cli-key": 1,
        "file": "registry-malformed",
    }
    assert f"[{registry}]" in err and "holds user information" in err
    assert not _leaks(err) and not (tmp_path / "r.json").exists()


def _run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(  # nosec B603
        [sys.executable, "-m", "pitloom", *args],
        capture_output=True,
        check=False,
        timeout=120,
        cwd=tmp_path,
    )


@pytest.mark.parametrize("verbose", [False, True], ids=["default", "verbose"])
def test_a_project_with_planted_secrets_writes_none_anywhere(
    tmp_path: Path, verbose: bool
) -> None:
    """The SBOM, stdout and stderr (also under ``-v``) hold no secret, and
    the removal is said once per URL, coded."""
    proj = _project(tmp_path)
    args = ["generate", str(proj), "-o", str(tmp_path / "out.json")]
    done = _run(tmp_path, *args, *(["-v"] if verbose else []))
    assert done.returncode == 0, done.stderr
    err = done.stderr.decode()
    assert not _leaks(done.stdout.decode(), err)
    sbom = (tmp_path / "out.json").read_text(encoding="utf-8")
    assert not _leaks(sbom) and "h.example/x.whl" in sbom
    assert err.count("[credentials-unsafe]") == 2
    json.loads(sbom)


def test_the_import_route_and_the_generate_route_store_no_credential_key(
    tmp_path: Path,
) -> None:
    """``-e`` is refused before anything is said about the entity; an
    imported SBOM element with the same key is skipped; neither stores it."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x\n", encoding="utf-8")
    key = f"https://u:{SECRETS[0]}@h/m"
    done = _run(
        tmp_path, "id", "generate", "-o", "reg.json", "-e", key + ":ai_AIPackage", "src"
    )
    err = done.stderr.decode()
    assert done.returncode == 1 and "[credentials-unsafe/registry]" in err
    assert "stored by name" not in err and not _leaks(err)
    assert not (tmp_path / "reg.json").exists()
    graph = [
        {
            "type": "CreationInfo",
            "@id": "_:c",
            "specVersion": "3.0.1",
            "createdBy": ["https://x/a"],
            "created": _WHEN,
        },
        {
            "type": "SoftwareAgent",
            "spdxId": "https://x/a",
            "creationInfo": "_:c",
            "name": "t",
        },
        {
            "type": "ai_AIPackage",
            "spdxId": "https://ids.example/ns#M-1",
            "creationInfo": "_:c",
            "name": key,
            "software_packageVersion": "1",
        },
    ]
    context = "https://spdx.org/rdf/3.0.1/spdx-context.jsonld"
    (tmp_path / "s.json").write_text(
        json.dumps({"@context": context, "@graph": graph}), encoding="utf-8"
    )
    done = _run(tmp_path, "id", "import", "s.json", "-o", "reg2.json")
    assert done.returncode == 0 and not _leaks(done.stderr.decode())
    assert not _leaks((tmp_path / "reg2.json").read_text(encoding="utf-8"))


# A colon is no character of a Windows file name.
_COLON_NAMES = sys.platform != "win32"


@pytest.mark.parametrize(
    "name",
    [
        pytest.param(
            "meet 10:30@ab:c.txt",
            marks=pytest.mark.skipif(not _COLON_NAMES, reason="no colon on Windows"),
        ),
        "meet@ab.txt",
        "a@b c.txt",
    ],
    ids=["colons", "at-sign", "at-sign-space"],
)
def test_a_file_name_that_looks_like_an_address_is_kept_on_every_route(
    tmp_path: Path, name: str
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / name).write_text("x\n", encoding="utf-8")
    done = _run(
        tmp_path, "id", "generate", "-o", "r.json", "-e", f"{name}:software_File", "src"
    )
    assert done.returncode == 0, done.stderr
    assert name in (tmp_path / "r.json").read_text(encoding="utf-8")
