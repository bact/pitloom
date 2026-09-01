# ruff: noqa: F403, F405
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom import assemble
from pitloom.assemble import (
    _model_generator,
    enrich_model,
    generate,
    generate_model_sbom,
)
from pitloom.assemble._model_generator import _write_output_file
from pitloom.assemble.spdx3.document import (
    build,
    build_model,
)
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectFile, ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.extract.ai_model import read_ai_model

from ..conftest import (
    _AI_MODEL_FIXTURES,
    _AI_MODEL_ROOT,
    _check_license_relationships,
    _make_wheel,
)


def test_build_package_files_have_sha256_verified_using() -> None:
    """Every file (not directory) software_File must carry a SHA-256
    verifiedUsing hash matching the corresponding ProjectFile.digest_sha256."""
    files = [
        ProjectFile(
            physical_path="src/pkg/__init__.py",
            distribution_path="pkg/__init__.py",
            digest_sha256="a" * 64,
        ),
        ProjectFile(
            physical_path="src/pkg/module.py",
            distribution_path="pkg/module.py",
            digest_sha256="b" * 64,
        ),
    ]
    project = ProjectMetadata(name="file-hash-project", version="1.0.0", files=files)
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())

    exporter = build(doc)
    graph = json.loads(exporter.to_json())["@graph"]

    file_elements = [e for e in graph if e.get("type") == "software_File"]
    by_name = {e["name"]: e for e in file_elements}

    # Directory node: no verifiedUsing hash.
    assert "verifiedUsing" not in by_name["pkg"]

    # File nodes: exactly one SHA-256 Hash matching the source digest.
    for pf in files:
        file_elem = by_name[pf.distribution_path]
        assert file_elem["software_fileKind"] == "file"
        (hash_obj,) = file_elem["verifiedUsing"]
        assert hash_obj["algorithm"] == "sha256"
        assert hash_obj["hashValue"] == pf.digest_sha256


def test_enrich_then_merge_matches_one_shot_enrich() -> None:
    """generate_model_sbom(enrich=True) in one shot must produce the same
    enrichment evidence as: generate a base SBOM with enrich=False, run
    enrich_model() separately, then merge_fragments() the two -- the
    design invariant behind exposing enrichment as its own CLI/API surface
    (see the plan's Surface 2(d))."""
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(fixture.read_bytes())
        (tmppath / "README.md").write_text(
            "---\nlicense: apache-2.0\ndatasets:\n  - tiny-imagenet\n---\n"
        )

        # One-shot.
        one_shot = json.loads(generate_model_sbom(model_path, enrich=True))
        one_shot_ds = {
            e["name"]
            for e in one_shot["@graph"]
            if e.get("type") == "dataset_DatasetPackage"
        }
        one_shot_ann_fields = {
            c["field"]
            for e in one_shot["@graph"]
            if e.get("type") == "Annotation" and e.get("statement")
            for c in json.loads(e["statement"]).get("changes", [])
            if json.loads(e["statement"]).get("kind") == "enrichment"
        }

        # Two-step: base without enrichment, then a separate fragment, merged.
        base_json = generate_model_sbom(model_path, enrich=False)
        fragment_json = enrich_model(model_path)
        fragment_path = tmppath / "enrichment.spdx3.json"
        fragment_path.write_text(fragment_json)

        exporter = Spdx3JsonExporter()
        # Re-deserialize the base doc into the exporter's object set, then merge.
        with tempfile.NamedTemporaryFile(
            suffix=".spdx3.json", mode="w", delete=False, dir=tmpdir
        ) as base_file:
            base_file.write(base_json)
            base_file_path = Path(base_file.name)
        with base_file_path.open("rb") as f:
            spdx3.JSONLDDeserializer().read(f, exporter.object_set)

        merge_fragments(tmppath, [fragment_path.name], exporter)
        merged = json.loads(exporter.to_json())

        merged_ds = {
            e["name"]
            for e in merged["@graph"]
            if e.get("type") == "dataset_DatasetPackage"
        }
        merged_ann_fields = {
            c["field"]
            for e in merged["@graph"]
            if e.get("type") == "Annotation" and e.get("statement")
            for c in json.loads(e["statement"]).get("changes", [])
            if json.loads(e["statement"]).get("kind") == "enrichment"
        }

        assert merged_ds == one_shot_ds == {"tiny-imagenet"}
        assert (
            merged_ann_fields
            == one_shot_ann_fields
            == {
                "license",
                "datasets:tiny-imagenet",
            }
        )


@pytest.mark.parametrize(
    "fixture_path",
    _AI_MODEL_FIXTURES,
    ids=[f"{p.parent.name}/{p.name}" for p in _AI_MODEL_FIXTURES],
)
def test_fixture_license_export(fixture_path: Path) -> None:
    """Extract metadata from a fixture file and verify SPDX 3 license output.

    Skips when:
    - The fixture file is absent from the repository clone.
    - The required optional library is not installed.
    - The model format does not embed a license (``meta.license is None``).

    When a license is present, asserts that the assembled ``build_model()``
    output contains both ``hasDeclaredLicense`` and ``hasConcludedLicense``
    relationships pointing to a ``simplelicensing_SimpleLicensingText`` element
    whose ``simplelicensing_licenseText`` matches the extracted license string.
    """
    if not fixture_path.exists():
        pytest.skip(f"Fixture not found: {fixture_path}")

    try:
        meta = read_ai_model(fixture_path)
    except ImportError as exc:
        pytest.skip(str(exc))

    if meta.license is None:
        pytest.skip(f"No license metadata embedded in {fixture_path.name}")

    exporter = build_model(meta, CreationMetadata())
    data = json.loads(exporter.to_json(pretty=True))
    graph = data["@graph"]

    ai_pkgs = [e for e in graph if e.get("type") == "ai_AIPackage"]
    assert len(ai_pkgs) == 1
    assert meta.license is not None  # type: ignore[comparison-overlap]
    _check_license_relationships(graph, ai_pkgs[0]["spdxId"], meta.license)


def test_generate_smart_entrypoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """generate() smart entrypoint auto-detects targets correctly."""
    monkeypatch.chdir(tmp_path)
    pyproject = '[project]\nname = "smart-pkg"\nversion = "0.1.0"\n'
    (tmp_path / "pyproject.toml").write_text(pyproject)

    # 1. Directory target
    proj_json = generate(tmp_path)
    assert "smart-pkg" in proj_json

    # 2. Wheel target
    wheel_path = _make_wheel(tmp_path, "smart-wheel", "1.0.0")
    wheel_json = generate(wheel_path)
    assert "smart-wheel" in wheel_json


@pytest.mark.parametrize("target", ["env", "environment", "--env"])
def test_generate_dispatches_env_target(
    target: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """generate() recognises every "env" spelling and dispatches to
    generate_env_sbom() rather than treating it as a project path."""
    called: dict[str, object] = {}

    def _fake_generate_env_sbom(**kwargs: object) -> str:
        called.update(kwargs)
        return "env-sbom"

    monkeypatch.setattr(assemble, "generate_env_sbom", _fake_generate_env_sbom)
    assert generate(target) == "env-sbom"
    assert "output_path" in called


def test_generate_dispatches_huggingface_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Hugging Face model id/URL dispatches to generate_model_sbom(),
    not the local-file or project fallback paths."""
    called: dict[str, object] = {}

    def _fake_generate_model_sbom(source: object, **kwargs: object) -> str:
        called["source"] = source
        called.update(kwargs)
        return "model-sbom"

    monkeypatch.setattr(assemble, "generate_model_sbom", _fake_generate_model_sbom)
    assert generate("hexgrad/Kokoro-82M") == "model-sbom"
    assert called["source"] == "hexgrad/Kokoro-82M"
    assert "enrich" in called


@pytest.mark.parametrize("suffix", [".gguf", ".pt2"])
def test_generate_dispatches_local_ai_model_file_by_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str
) -> None:
    """A local file whose extension matches a known AI-model format
    dispatches to generate_model_sbom(), even though it is a real file
    on disk (unlike the Hugging Face source string case above). ``.pt2``
    is a regression case: it was missing from generate()'s extension
    tuple, so a PyTorch PT2/ExecuTorch file silently fell through to
    project-SBOM generation instead."""
    model_path = tmp_path / f"weights{suffix}"
    model_path.write_bytes(b"\x00")

    called: dict[str, object] = {}

    def _fake_generate_model_sbom(source: object, **kwargs: object) -> str:
        called["source"] = source
        called.update(kwargs)
        return "model-sbom"

    monkeypatch.setattr(assemble, "generate_model_sbom", _fake_generate_model_sbom)
    assert generate(model_path) == "model-sbom"
    assert called["source"] == model_path
    assert "enrich" in called


def test_write_output_file_to_stdout_adds_missing_trailing_newline(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """output_path == "-" writes to stdout, appending a newline only when
    the SBOM JSON does not already end with one."""
    _write_output_file("no-newline", Path("-"))
    assert capsys.readouterr().out == "no-newline\n"

    _write_output_file("has-newline\n", Path("-"))
    assert capsys.readouterr().out == "has-newline\n"


def test_generate_model_sbom_huggingface_offline_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Hugging Face source with offline=True (or an offline pyproject.toml
    default) is rejected before any network access is attempted."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="Offline mode enabled"):
        generate_model_sbom("hexgrad/Kokoro-82M", offline=True)


def test_generate_model_sbom_huggingface_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Hugging Face source (offline=False) fetches the model via
    read_huggingface() and builds the SBOM without an entity id lookup."""
    monkeypatch.chdir(tmp_path)
    fake_model = object()

    def _fake_read_huggingface(source: str) -> object:
        assert source == "hexgrad/Kokoro-82M"
        return fake_model

    class _FakeExporter:
        def to_json(self, *, pretty: bool, describe_relationship: bool) -> str:
            return "{}"

    def _fake_build_model(model: object, *args: object, **kwargs: object) -> object:
        assert model is fake_model
        assert kwargs["entity_spdx_id"] is None
        return _FakeExporter()

    monkeypatch.setattr(_model_generator, "read_huggingface", _fake_read_huggingface)
    monkeypatch.setattr(_model_generator, "build_model", _fake_build_model)

    result = generate_model_sbom("hexgrad/Kokoro-82M", offline=False)
    assert result == "{}"


def test_generate_smart_entrypoint_sdist_file_target(tmp_path: Path) -> None:
    """A file target whose extension matches none of the AI-model
    extensions (e.g. an sdist archive) falls through to
    generate_project_sbom() -- covers the "file, but not a model file"
    branch in generate()'s dispatch, and generate_project_sbom()'s
    target_path.is_file() branch (merkle_root=None, files taken from
    already-parsed project_metadata, no directory-only merge_fragments())."""
    import io
    import tarfile

    sdist_path = tmp_path / "smart-sdist-pkg-1.0.0.tar.gz"
    pkg_info = "Metadata-Version: 2.1\nName: smart-sdist-pkg\nVersion: 1.0.0\n"
    with tarfile.open(sdist_path, "w:gz") as tf:
        pkg_bytes = pkg_info.encode("utf-8")
        ti = tarfile.TarInfo(name="smart-sdist-pkg-1.0.0/PKG-INFO")
        ti.size = len(pkg_bytes)
        tf.addfile(ti, io.BytesIO(pkg_bytes))

    sdist_json = generate(sdist_path)
    assert "smart-sdist-pkg" in sdist_json
