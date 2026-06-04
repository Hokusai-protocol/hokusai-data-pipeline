# Model 27 Serving

Model 27 serves the public "Sales Lead Scoring" contract through the shared MLflow-backed API path at `POST /api/v1/models/27/predict`.

## Request contract

The public request schema is `sales_lead_scoring_inputs/v1` with these required fields:

- `Customer ID`
- `first_industry`
- `first_segment`
- `first_region`
- `first_subregion`
- `first_country`
- `first_product`
- `first_sales`
- `first_quantity`
- `first_discount`
- `total_profit`

Example request body:

```json
{
  "inputs": {
    "Customer ID": "CG-12520",
    "first_industry": "Technology",
    "first_segment": "Enterprise",
    "first_region": "North America",
    "first_subregion": "US East",
    "first_country": "United States",
    "first_product": "Analytics Suite",
    "first_sales": 12500.0,
    "first_quantity": 25.0,
    "first_discount": 0.1,
    "total_profit": 3200.0
  }
}
```

Example response shape:

```json
{
  "lead_score": 82,
  "conversion_probability": 0.82,
  "recommendation": "Hot",
  "confidence": 0.82
}
```

## Environment

- `MODEL_27_MLFLOW_URI`: optional override for the default `models:/Sales Lead Scoring@production`

## Registry runbook

1. Run `python -m scripts.model_27.inspect_mlflow_registry --tracking-uri <uri>` in an environment with MLflow auth and mTLS configured.
2. Confirm the candidate registered model name and version in `scripts/model_27/inspect_report.json`.
3. Run `python -m scripts.model_27.restore_sales_lead_scoring --registered-name "Sales Lead Scoring" --version <version> --alias production --tracking-uri <uri>`.
4. Capture the printed `rollback_command` before promoting beyond development.

If the trained artifact signature diverges from the advertised 11-field request contract, update the adapter mapping in `src/api/endpoints/sales_lead_scoring_adapter.py` before deploying.
