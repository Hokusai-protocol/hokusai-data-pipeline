# ruff: noqa: ANN101
"""Gate adapters for arms that are already frozen, and the registry the runner reads.

Arms 1 and 2 are the HOK-3024 baselines: the same code, fixed hyperparameters and
variants, fitted on the gate's training rows. Arms 3 to 6 are added to
:data:`ARM_FACTORIES` by the sessions that build them, each at a frozen version.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import pandas as pd

from src.arbiter.baselines import fit_and_score
from src.arbiter.gate import REHEARSAL_VERSION, ArmAdapter, ArmContext
from src.arbiter.llm_arm import FrontierLlmArm

BASELINE_VERSION = "hok-3024/1.0.0"


class BaselineArms:
    """Arms 1 and 2 (HOK-3024). The prior is fitted too but is not an arm."""

    arm_id = "hok-3024-baselines"
    version = BASELINE_VERSION

    _ROLES = {
        "trivial.feature.shape.loc_touched": "arm1",
        "trivial.feature.shape.files_touched": "arm1",
        "trivial.feature.history.file_commits_90d": "arm1",
        "trivial.feature.author.repo_commits_prior": "arm1",
        "trivial_lr": "arm1",
        "jit_lr": "arm2",
        "jit_gbm": "arm2",
    }

    def variants(self) -> Mapping[str, str]:
        return dict(self._ROLES)

    def fit(self, train: pd.DataFrame, context: ArmContext) -> dict[str, Any]:
        # fit_and_score fits and scores in one pass; keep the training rows for score().
        return {"train": train}

    def score(
        self, fitted: Mapping[str, Any], rows: pd.DataFrame, context: ArmContext
    ) -> Mapping[str, pd.DataFrame]:
        train = fitted["train"]
        columns = list(context.feature_columns)
        scored = fit_and_score(
            train[columns],
            train["label"],
            rows[columns],
            context.categories,
            weights=train["sample_weight"],
        )
        out = {}
        for s in scored:
            if s.arm not in self._ROLES:
                continue
            frame = pd.DataFrame({"score": s.score}, index=rows.index)
            if s.probability:
                frame["probability"] = s.score
            out[s.arm] = frame
        return out


STAND_IN_ID = "rehearsal-stand-ins"


class RehearsalStandIns:
    """Rehearsal only: JIT LR stands in for arm 4 and JIT GBM for arm 5.

    Only the roles no registered arm covers are filled. It lets the whole gate
    run on a rehearsal slice before arms 4 and 5 exist.
    :func:`src.arbiter.gate.score_once` refuses it on the sealed slice.
    """

    arm_id = STAND_IN_ID
    version = REHEARSAL_VERSION
    _SOURCE = {"arm4": "jit_lr", "arm5": "jit_gbm"}

    def __init__(self, roles: tuple[str, ...] = ("arm4", "arm5")) -> None:
        unknown = set(roles) - set(self._SOURCE)
        if unknown or not roles:
            raise ValueError(f"Stand-ins exist for {sorted(self._SOURCE)}, not {sorted(unknown)}")
        self.roles = tuple(roles)

    def variants(self) -> Mapping[str, str]:
        return {f"stand_in.{r}": r for r in self.roles}

    def fit(self, train: pd.DataFrame, context: ArmContext) -> dict[str, Any]:
        return BaselineArms().fit(train, context)

    def score(
        self, fitted: Mapping[str, Any], rows: pd.DataFrame, context: ArmContext
    ) -> Mapping[str, pd.DataFrame]:
        scored = BaselineArms().score(fitted, rows, context)
        return {f"stand_in.{r}": scored[self._SOURCE[r]] for r in self.roles}


ARM_FACTORIES: dict[str, Callable[[], ArmAdapter]] = {
    BaselineArms.arm_id: BaselineArms,
    STAND_IN_ID: RehearsalStandIns,
    FrontierLlmArm.arm_id: FrontierLlmArm,
}
