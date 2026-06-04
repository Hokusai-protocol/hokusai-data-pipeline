"""Public request schema for MLflow-backed sales lead scoring serving."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

MODEL_27_INPUT_FIELDS: tuple[str, ...] = (
    "Customer ID",
    "first_industry",
    "first_segment",
    "first_region",
    "first_subregion",
    "first_country",
    "first_product",
    "first_sales",
    "first_quantity",
    "first_discount",
    "total_profit",
)


class SalesLeadScoringInputs(BaseModel):
    """Validated public payload for Model 27 sales lead scoring."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    customer_id: str = Field(alias="Customer ID")
    first_industry: str
    first_segment: str
    first_region: str
    first_subregion: str
    first_country: str
    first_product: str
    first_sales: float
    first_quantity: float
    first_discount: float
    total_profit: float
