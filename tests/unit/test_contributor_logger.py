"""Unit tests for contributor attribution utilities."""

from src.utils.contributor_logger import build_contributor_attribution


def test_build_contributor_attribution_from_explicit_inputs() -> None:
    attribution = build_contributor_attribution(
        contributor_id="author-1",
        contributor_role="prompt_author",
        contributors_by_role={
            "training_data_uploader": "uploader-1",
            "human_labeler": "labeler-1",
        },
    )

    assert attribution.primary_contributor_id == "author-1"
    assert attribution.contributors_by_role == {
        "prompt_author": "author-1",
        "training_data_uploader": "uploader-1",
        "human_labeler": "labeler-1",
    }

    tags = attribution.to_mlflow_tags()
    assert tags["contributor_id"] == "author-1"
    assert tags["hokusai.contributor.prompt_author_id"] == "author-1"
    assert tags["hokusai.contributor.training_data_uploader_id"] == "uploader-1"
    assert tags["hokusai.contributor.human_labeler_id"] == "labeler-1"


def test_build_contributor_attribution_merges_from_inputs() -> None:
    attribution = build_contributor_attribution(
        contributor_id="author-1",
        contributor_role="prompt_author",
        inputs={
            "training_data_uploader_id": "uploader-2",
            "human_labeler_id": "labeler-2",
            "contributor_id": "author-override",
            "contributor_role": "prompt_author",
        },
    )

    assert attribution.contributors_by_role["prompt_author"] == "author-override"
    assert attribution.contributors_by_role["training_data_uploader"] == "uploader-2"
    assert attribution.contributors_by_role["human_labeler"] == "labeler-2"
