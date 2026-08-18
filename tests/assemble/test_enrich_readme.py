# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.enrich.readme: local README/model-card frontmatter enrichment."""

import tempfile
from pathlib import Path

from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.enrich.readme import (
    ReadmeEnricher,
    _find_model_card_file,
    _parse_frontmatter,
)

# ---------------------------------------------------------------------------
# _parse_frontmatter
# ---------------------------------------------------------------------------


def test_parse_frontmatter_basic() -> None:
    text = "---\nlicense: mit\ndatasets:\n  - foo\n---\n\nSome prose.\n"
    assert _parse_frontmatter(text) == {"license": "mit", "datasets": ["foo"]}


def test_parse_frontmatter_no_delimiters() -> None:
    assert _parse_frontmatter("Just prose, no frontmatter.\n") is None


def test_parse_frontmatter_unclosed_block() -> None:
    assert _parse_frontmatter("---\nlicense: mit\n") is None


def test_parse_frontmatter_malformed_yaml() -> None:
    text = "---\nlicense: [unterminated\n---\n"
    assert _parse_frontmatter(text) is None


def test_parse_frontmatter_non_mapping_root() -> None:
    text = "---\n- just\n- a\n- list\n---\n"
    assert _parse_frontmatter(text) is None


def test_parse_frontmatter_empty_block() -> None:
    assert _parse_frontmatter("---\n---\n") is None


# ---------------------------------------------------------------------------
# _find_model_card_file
# ---------------------------------------------------------------------------


def test_find_model_card_file_readme() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "README.md").write_text("---\nlicense: mit\n---\n")
        assert _find_model_card_file(p) == p / "README.md"


def test_find_model_card_file_case_insensitive() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "readme.md").write_text("---\nlicense: mit\n---\n")
        found = _find_model_card_file(p)
        assert found is not None
        assert found.name.lower() == "readme.md"


def test_find_model_card_file_readme_priority_over_model_card() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "README.md").write_text("---\nlicense: mit\n---\n")
        (p / "MODEL_CARD.md").write_text("---\nlicense: apache-2.0\n---\n")
        assert _find_model_card_file(p) == p / "README.md"


def test_find_model_card_file_falls_back_to_model_card() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "MODEL_CARD.md").write_text("---\nlicense: apache-2.0\n---\n")
        assert _find_model_card_file(p) == p / "MODEL_CARD.md"


def test_find_model_card_file_none_present() -> None:
    with tempfile.TemporaryDirectory() as d:
        assert _find_model_card_file(Path(d)) is None


# ---------------------------------------------------------------------------
# ReadmeEnricher.enrich
# ---------------------------------------------------------------------------


def test_enrich_no_readme_is_noop() -> None:
    with tempfile.TemporaryDirectory() as d:
        model = AiModelMetadata()
        result = ReadmeEnricher().enrich(model, model_dir=Path(d))
    assert result.source_name == "readme"
    assert not result.fields
    assert model.license is None
    assert not model.datasets


def test_enrich_fills_license_gap() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "README.md").write_text("---\nlicense: mit\n---\n")
        model = AiModelMetadata()
        result = ReadmeEnricher().enrich(model, model_dir=p)
    assert model.license == "mit"
    assert model.provenance["license"] == "Source: README.md | Method: yaml_frontmatter"
    assert len(result.fields) == 1
    assert result.fields[0].field == "license"
    assert result.fields[0].before is None
    assert result.fields[0].after == "mit"
    assert result.fields[0].role == "detected"


def test_enrich_never_overwrites_existing_license() -> None:
    """Gap-filling only -- an already-extracted license is never replaced,
    same 'primary wins' discipline as merge_project_metadata()."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "README.md").write_text("---\nlicense: apache-2.0\n---\n")
        model = AiModelMetadata(license="MIT")
        result = ReadmeEnricher().enrich(model, model_dir=p)
    assert model.license == "MIT"
    assert not result.fields


def test_enrich_adds_dataset_references() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "README.md").write_text(
            "---\ndatasets:\n  - tiny-imagenet\n  - imagenet-val\n---\n"
        )
        model = AiModelMetadata()
        result = ReadmeEnricher().enrich(model, model_dir=p)
    assert [ref.metadata.name for ref in model.datasets] == [
        "tiny-imagenet",
        "imagenet-val",
    ]
    assert all(ref.role == "trainedOn" for ref in model.datasets)
    assert len(result.fields) == 2
    assert {f.field for f in result.fields} == {
        "datasets:tiny-imagenet",
        "datasets:imagenet-val",
    }


def test_enrich_dedupes_datasets_by_name() -> None:
    """A dataset already present (by name) is not re-added, and does not
    appear in the result's changed fields."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "README.md").write_text(
            "---\ndatasets:\n  - already-there\n  - new-one\n---\n"
        )
        model = AiModelMetadata(
            datasets=[
                DatasetReference(
                    role="trainedOn", metadata=DatasetMetadata(name="already-there")
                )
            ]
        )
        result = ReadmeEnricher().enrich(model, model_dir=p)
    names = [ref.metadata.name for ref in model.datasets]
    assert names == ["already-there", "new-one"]
    assert len(result.fields) == 1
    assert result.fields[0].field == "datasets:new-one"


def test_enrich_ignores_non_string_dataset_entries() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "README.md").write_text("---\ndatasets:\n  - 42\n  - valid-name\n---\n")
        model = AiModelMetadata()
        result = ReadmeEnricher().enrich(model, model_dir=p)
    assert [ref.metadata.name for ref in model.datasets] == ["valid-name"]
    assert len(result.fields) == 1


def test_enrich_malformed_frontmatter_is_noop() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "README.md").write_text("---\nlicense: [unterminated\n---\n")
        model = AiModelMetadata()
        result = ReadmeEnricher().enrich(model, model_dir=p)
    assert not result.fields
    assert model.license is None


def test_enrich_no_frontmatter_prose_only_is_noop() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "README.md").write_text("# My Model\n\nJust prose here.\n")
        model = AiModelMetadata()
        result = ReadmeEnricher().enrich(model, model_dir=p)
    assert not result.fields


def test_enrich_oserror_recovery() -> None:
    """_find_model_card_file and enricher handle OSError gracefully."""
    from unittest.mock import MagicMock, patch

    mock_dir = MagicMock(spec=Path)
    mock_dir.iterdir.side_effect = OSError("permission denied")
    assert _find_model_card_file(mock_dir) is None

    # Read error on card file
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        card = p / "README.md"
        card.write_text("---\nlicense: mit\n---\n")
        with patch.object(Path, "read_text", side_effect=OSError("read error")):
            model = AiModelMetadata()
            result = ReadmeEnricher().enrich(model, model_dir=p)
            assert not result.fields


def test_run_enrichers_failing_enricher_logged() -> None:
    """run_enrichers logs and continues when an enricher raises an exception."""
    from unittest.mock import MagicMock, patch

    from pitloom.core.enrich_config import EnrichConfig
    from pitloom.enrich import run_enrichers

    failing_enricher = MagicMock()
    failing_enricher.name = "broken"
    failing_enricher.enrich.side_effect = RuntimeError("broken enricher")

    with patch(
        "pitloom.enrich.ReadmeEnricher",
        return_value=failing_enricher,
    ):
        model = AiModelMetadata()
        cfg = EnrichConfig(local=True)
        results = run_enrichers(model, cfg, Path("/tmp"))
        assert results == []


def test_enricher_protocol_raises_not_implemented() -> None:
    """Enricher.enrich raises NotImplementedError when invoked directly."""
    import pytest

    from pitloom.enrich.base import Enricher

    with pytest.raises(NotImplementedError):
        Enricher.enrich(None, None, model_dir=Path("/tmp"))  # type: ignore[arg-type]
