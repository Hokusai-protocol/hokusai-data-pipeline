from __future__ import annotations

from scripts.model_30.attribute_retraining import _build_cohorts, _identity_by_row_index


def _block(
    *,
    submission_id: str,
    row_start: int,
    row_end: int,
    account_id: str | None = None,
    wallet: str | None = None,
) -> dict[str, object]:
    return {
        "submission_id": submission_id,
        "row_start": row_start,
        "row_end": row_end,
        "row_count": row_end - row_start + 1,
        "account_id": account_id,
        "wallet": wallet,
    }


def test_build_cohorts_groups_by_account_id_preferring_account_over_wallet() -> None:
    manifest = {
        "blocks": [
            _block(submission_id="s1", row_start=0, row_end=1, account_id="user-a", wallet="0xaa"),
            _block(submission_id="s2", row_start=2, row_end=2, account_id="user-a"),
            _block(submission_id="s3", row_start=3, row_end=3, wallet="0xbb"),
        ]
    }

    cohorts = {cohort.cohort_id: cohort for cohort in _build_cohorts(manifest)}

    # account_id keys its cohort and carries the wallet through; the wallet-only block is its own.
    assert set(cohorts) == {"user-a", "0xbb"}
    assert cohorts["user-a"].account_id == "user-a"
    assert cohorts["user-a"].wallet == "0xaa"
    assert cohorts["user-a"].row_count == 3
    assert cohorts["user-a"].submission_ids == ("s1", "s2")
    assert cohorts["0xbb"].account_id is None
    assert cohorts["0xbb"].wallet == "0xbb"


def test_build_cohorts_skips_blocks_with_no_identity() -> None:
    manifest = {
        "blocks": [
            _block(submission_id="s1", row_start=0, row_end=0),  # no account_id, no wallet
            _block(submission_id="s2", row_start=1, row_end=1, account_id="user-a"),
        ]
    }

    cohorts = _build_cohorts(manifest)

    assert [cohort.cohort_id for cohort in cohorts] == ["user-a"]


def test_identity_by_row_index_maps_rows_to_account_identity() -> None:
    blocks = [
        _block(submission_id="s1", row_start=0, row_end=1, account_id="user-a", wallet="0xaa"),
        _block(submission_id="s2", row_start=2, row_end=2, wallet="0xbb"),
        _block(submission_id="s3", row_start=3, row_end=3),  # no identity
    ]

    identities = _identity_by_row_index(blocks=blocks, row_count=4)

    assert identities == ["user-a", "user-a", "0xbb", None]
