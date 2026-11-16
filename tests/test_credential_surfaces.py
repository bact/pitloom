# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An SBOM whose project URL, dependency URL, dataset URL or element id
holds a credential is refused on every surface, with no secret in stdout,
stderr or a log record, and nothing written: ``loom generate`` (to a file
and with ``-o -``), the library, the Hatchling hook, ``embed-wheel`` (with
and without ``--sbom``), ``merge`` and the Croissant dataset route; an ID
registry namespace or key is refused by the registry's command, library and
file.

See also: tests/test_credential_surfaces_accept.py (the same surfaces with
the value accepted), tests/export/test_spdx3_credentials.py (the check) and
tests/id_registry/test_credentials_registry.py (the registry rule).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from pitloom.__main__ import main
from pitloom.assemble import generate_project_sbom
from pitloom.assemble.spdx3.document import build_model
from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.config import PitloomConfig
from pitloom.core.dataset_metadata import DatasetReference
from pitloom.extract.dataset.croissant import read_croissant
from pitloom.id_registry import IdRegistry
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import code_of
from tests._author_routes import CREATED, hook_sbom, write_wheel
from tests.cli.shared import FRAGMENT_FIXTURE

pytestmark = pytest.mark.platform

SECRETS = ("S3CRET", "T0KEN")
DEP = "foo @ https://a:S3CRET@h.example/x.whl?token=T0KEN"
HOME = "https://b:T0KEN@e.example/h?api_key=S3CRET"
_NS = "https://u:S3CRET@ids.example/ns"
_WHEN = "2026-01-01T00:00:00Z"
REFUSED = "credentials-unsafe/refused"
#: A fingerprint as a refusal prints it, for the user to pass back.
_OFFERED = re.compile(r"--accept-url-credential (sha256:[0-9a-f]{16})")


class Refused(Exception):
    """A command-line surface exited non-zero."""


def leaks(*texts: str) -> list[str]:
    return [s for s in SECRETS for t in texts if s in t]


def offered(text: str) -> list[str]:
    """The fingerprints a refusal printed in *text*, sorted, each once."""
    return sorted(set(_OFFERED.findall(text)))


def _toml_list(items: Sequence[str]) -> str:
    return "[" + ", ".join(f"'{item}'" for item in items) + "]"


def _project(tmp: Path, home: str, accept: Sequence[str] = ()) -> Path:
    proj = tmp / "proj"
    (proj / "testpkg").mkdir(parents=True)
    (proj / "testpkg" / "__init__.py").write_text("", encoding="utf-8")
    (proj / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n'
        "[project]\nname = 'testpkg'\nversion = '0.1.0'\n"
        f"dependencies = ['{DEP}']\n[project.urls]\nHomepage = '{home}'\n"
        "[tool.hatch.metadata]\nallow-direct-references = true\n"
        f"[tool.pitloom]\naccept-url-credentials = {_toml_list(accept)}\n",
        encoding="utf-8",
    )
    return proj


def _cli(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    return main()


def _flags(accept: Sequence[str]) -> list[str]:
    return [arg for fp in accept for arg in ("--accept-url-credential", fp)]


def _ok(argv: list[str], mp: pytest.MonkeyPatch, accept: Sequence[str]) -> None:
    if _cli(argv + _flags(accept), mp) != 0:
        raise Refused(argv[0])


def _generate(tmp: Path, mp: pytest.MonkeyPatch, home: str, accept: list[str]) -> str:
    out = tmp / "o.json"
    argv = ["generate", str(_project(tmp, home)), "-o", str(out), "--offline"]
    _ok(argv + ["--creation-datetime", _WHEN], mp, accept)
    return out.read_text(encoding="utf-8")


def _stdout(tmp: Path, mp: pytest.MonkeyPatch, home: str, accept: list[str]) -> str:
    argv = ["generate", str(_project(tmp, home)), "-o", "-", "--offline"]
    _ok(argv + ["--creation-datetime", _WHEN], mp, accept)
    return ""  # the SBOM is on stdout, checked with it


def _library(tmp: Path, _mp: pytest.MonkeyPatch, home: str, accept: list[str]) -> str:
    out = tmp / "o.json"
    config = PitloomConfig(accept_url_credentials=tuple(accept))
    generate_project_sbom(
        _project(tmp, home), output_path=out, offline=True, pitloom_config=config
    )
    return out.read_text(encoding="utf-8")


def _hook(tmp: Path, _mp: pytest.MonkeyPatch, home: str, accept: list[str]) -> str:
    return hook_sbom(_project(tmp, home, accept))


def wheel_of(tmp: Path, home: str) -> Path:
    metadata = (
        "Metadata-Version: 2.4\nName: demo\nVersion: 1.0\n"
        f"Project-URL: Homepage, {home}\nRequires-Dist: {DEP}\n"
    )
    return write_wheel(tmp, metadata)


def embedded(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as zf:
        return "".join(
            zf.read(n).decode("utf-8") for n in zf.namelist() if "/sboms/" in n
        )


def _embed_wheel(
    tmp: Path, mp: pytest.MonkeyPatch, home: str, accept: list[str]
) -> str:
    wheel = wheel_of(tmp, home)
    _ok(
        ["embed-wheel", str(wheel), "--offline", "--creation-datetime", _WHEN],
        mp,
        accept,
    )
    return embedded(wheel)


def given_sbom(tmp: Path, mp: pytest.MonkeyPatch, home: str) -> Path:
    """A ``demo`` 1.0 SBOM holding *home*, written with every credential
    allowed: what ``embed-wheel --sbom`` is then given."""
    sbom = tmp / "given.spdx3.json"
    (tmp / "given").mkdir()
    wheel = wheel_of(tmp / "given", home)
    argv = ["wheel", str(wheel), "-o", str(sbom), "--offline"]
    argv += ["--allow-url-credentials", "--creation-datetime", _WHEN]
    assert _cli(argv, mp) == 0
    return sbom


def _embed_given(
    tmp: Path, mp: pytest.MonkeyPatch, home: str, accept: list[str]
) -> str:
    sbom = given_sbom(tmp, mp, home)
    wheel = wheel_of(tmp, "https://e.example/h")
    _ok(["embed-wheel", str(wheel), "--sbom", str(sbom)], mp, accept)
    return embedded(wheel)


def _merge(tmp: Path, mp: pytest.MonkeyPatch, home: str, accept: list[str]) -> str:
    fragments = tmp / "fragments"
    fragments.mkdir()
    data = json.loads(FRAGMENT_FIXTURE.read_text(encoding="utf-8"))
    for element in data["@graph"]:
        if "software_downloadLocation" in element:
            element["software_downloadLocation"] = home
    (fragments / "a.json").write_text(json.dumps(data), encoding="utf-8")
    _ok(["merge", str(fragments), "-o", str(tmp / "o.json")], mp, accept)
    return (tmp / "o.json").read_text(encoding="utf-8")


def _croissant(tmp: Path, _mp: pytest.MonkeyPatch, home: str, accept: list[str]) -> str:
    card = tmp / "croissant.json"
    card.write_text(
        json.dumps(
            {
                "@context": {"@vocab": "https://schema.org/"},
                "@type": "Dataset",
                "name": "d",
                "url": home,
            }
        ),
        encoding="utf-8",
    )
    dataset = DatasetReference(role="trainedOn", metadata=read_croissant(card))
    sbom = build_model(AiModelMetadata(name="m", datasets=[dataset]), CREATED)
    config = PitloomConfig(accept_url_credentials=tuple(accept))
    return sbom.to_json(credentials=config.credential_policy)


Surface = Callable[[Path, pytest.MonkeyPatch, str, list[str]], str]

SURFACES: dict[str, Surface] = {
    "cli-generate": _generate,
    "cli-stdout": _stdout,
    "library": _library,
    "hook": _hook,
    "embed-wheel": _embed_wheel,
    "embed-wheel-sbom": _embed_given,
    "merge": _merge,
    "croissant": _croissant,
}


def refuse(surface: str, tmp: Path, mp: pytest.MonkeyPatch, home: str) -> str:
    """Run *surface* expecting a refusal; the error's text."""
    with pytest.raises((ValueError, Refused)) as caught:
        SURFACES[surface](tmp, mp, home, [])
    if not isinstance(caught.value, Refused):
        assert code_of(caught.value) == REFUSED
    return str(caught.value)


def said_refused(err: str, caplog: pytest.LogCaptureFixture) -> bool:
    """Whether the refusal was said, on stderr or as a log record."""
    codes = {getattr(r, CODE_ATTR, "") for r in caplog.records}
    return f"[{REFUSED}]" in err or REFUSED in codes


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_a_planted_secret_is_refused_and_reaches_no_stream(
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.chdir(tmp_path)
    with caplog.at_level(logging.INFO, logger="pitloom"):
        error = refuse(surface, tmp_path, monkeypatch, HOME)
    out, err = capsys.readouterr()
    assert not leaks(out, err, caplog.text, error)
    assert said_refused(err, caplog) and offered(err + caplog.text)
    assert not (tmp_path / "o.json").exists() and "@graph" not in out
    if surface.startswith("embed-wheel"):
        assert not embedded(tmp_path / "demo-1.0-py3-none-any.whl")


_GHP = "ghp_T0KEN" + "aB3" * 10 + "x"


def _merge_id(tmp: Path, mp: pytest.MonkeyPatch) -> None:
    """``merge`` of a fragment whose element id holds a token."""
    fragments = tmp / "fragments"
    fragments.mkdir()
    text = FRAGMENT_FIXTURE.read_text(encoding="utf-8")
    old = "https://spdx.org/spdxdocs/pitloom-test/DatasetPackage/tiny-image-01"
    (fragments / "a.json").write_text(
        text.replace(old, f"https://e.example/{_GHP}#tiny"), encoding="utf-8"
    )
    _ok(["merge", str(fragments), "-o", str(tmp / "o.json")], mp, [])


def test_a_merged_element_id_holding_a_token_is_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An id is refused as it stands, never rewritten with its references
    (the id-collision rule went with the rewrite)."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(Refused):
        _merge_id(tmp_path, monkeypatch)
    _, err = capsys.readouterr()
    assert f"[{REFUSED}]" in err and "/spdxId" in err and _GHP[4:] not in err
    assert not (tmp_path / "o.json").exists()


#: A value behind a format character: a PURL holding a token, a URL and an
#: scp-style address.
_MARKED = {
    "purl": "\u200bpkg:pypi/x@1?token=S3CRET&vcs_url=https://e.example/h?code=1",
    "url": "\ufeffhttps://u:S3CRET@e.example/h?code=1",
    "scp": "\u202eu:S3CRET@e.example:h",
}


@pytest.mark.parametrize("value", sorted(_MARKED))
@pytest.mark.parametrize("surface", ["cli-generate", "library", "hook", "merge"])
def test_a_value_behind_a_format_character_is_refused_masked(
    surface: str,
    value: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A format character in front of a value hides no secret from the
    check, and no line shows the secret."""
    monkeypatch.chdir(tmp_path)
    with caplog.at_level(logging.INFO, logger="pitloom"):
        refuse(surface, tmp_path, monkeypatch, _MARKED[value])
    _, err = capsys.readouterr()
    assert "S3CRET" not in err + caplog.text and "code=1" not in err
    assert said_refused(err, caplog)


def _registry_surfaces(tmp: Path, mp: pytest.MonkeyPatch) -> dict[str, object]:
    """Each registry surface given a credentialed namespace or key: its code
    (an exception's, else the exit status)."""
    found: dict[str, object] = {}
    calls: dict[str, Callable[[], object]] = {
        "library-new": lambda: IdRegistry.new("demo", namespace=_NS),
        "constructor": lambda: IdRegistry(namespace=_NS),
        "register": lambda: IdRegistry(namespace="https://h/ns").register(
            "ai_AIPackage", HOME
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
    found["cli-key"] = _cli(base + ["-e", f"{HOME}:ai_AIPackage", "src"], mp)
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
    assert not leaks(err) and not (tmp_path / "r.json").exists()


def run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(  # nosec B603
        [sys.executable, "-m", "pitloom", *args],
        capture_output=True,
        check=False,
        timeout=120,
        cwd=tmp_path,
    )


@pytest.mark.parametrize("verbose", [False, True], ids=["default", "verbose"])
def test_a_project_with_planted_secrets_is_refused_in_a_real_process(
    tmp_path: Path, verbose: bool
) -> None:
    """Stdout and stderr (also under ``-v``) hold no secret, each value is
    named once with its fingerprint, and no SBOM is written."""
    proj = _project(tmp_path, HOME)
    args = ["generate", str(proj), "-o", str(tmp_path / "out.json")]
    done = run(tmp_path, *args, *(["-v"] if verbose else []))
    err = done.stderr.decode()
    assert done.returncode == 1, err
    assert not leaks(done.stdout.decode(), err)
    assert err.count(f"[{REFUSED}]") == len(offered(err)) + 1 >= 3
    assert not (tmp_path / "out.json").exists()


def test_the_import_route_and_the_generate_route_store_no_credential_key(
    tmp_path: Path,
) -> None:
    """``-e`` is refused before anything is said about the entity; an
    imported SBOM element with the same key is skipped; neither stores it."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x\n", encoding="utf-8")
    key = f"https://u:{SECRETS[0]}@h/m"
    done = run(
        tmp_path, "id", "generate", "-o", "reg.json", "-e", key + ":ai_AIPackage", "src"
    )
    err = done.stderr.decode()
    assert done.returncode == 1 and "[credentials-unsafe/registry]" in err
    assert "stored by name" not in err and not leaks(err)
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
    done = run(tmp_path, "id", "import", "s.json", "-o", "reg2.json")
    assert done.returncode == 0 and not leaks(done.stderr.decode())
    assert not leaks((tmp_path / "reg2.json").read_text(encoding="utf-8"))


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
    done = run(
        tmp_path, "id", "generate", "-o", "r.json", "-e", f"{name}:software_File", "src"
    )
    assert done.returncode == 0, done.stderr
    assert name in (tmp_path / "r.json").read_text(encoding="utf-8")
