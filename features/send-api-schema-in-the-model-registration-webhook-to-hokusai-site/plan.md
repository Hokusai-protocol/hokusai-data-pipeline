# HOK-1470 Implementation Plan

**Issue:** Send api_schema in the model registration webhook to hokusai-site
**Branch:** `task/send-api-schema-in-the-model-registration-webhook-to-hokusai-site`
**Repo:** `hokusai-data-pipeline`

## 1. Context & Findings

### 1.1 Receiving end (already shipped — HOK-1465)

`hokusai-site` PR #281 (commit `9211de1`) added `model.api_schema` support to:

- `packages/web/src/lib/webhook-utils.ts` → the **original-format** Zod schema (`webhookSchema`) now declares `api_schema: jsonObjectSchema.nullish()` on the nested `model` object.
- `packages/web/src/lib/model-registration-webhook.ts` → reads `validatedPayload.model.api_schema`; `undefined` is a no-op, `null` clears, an object value is persisted via Prisma to `Model.api_schema`.
- `packages/web/src/types/api/webhook.ts` → `MLflowWebhookPayload.model.api_schema?: Record<string, unknown> | null`.

**Crucial detail:** the site supports two payload shapes. The Zod parsers run in this order inside `validateWebhookPayload`:

1. **SDK shape** — flat fields (`event_type`, `token_id`, `model_name`, `status`, …). `api_schema` is **not** part of `sdkWebhookSchema` and the SDK→`MLflowWebhookPayload` transformer **does not propagate it**.
2. **Original MLflow shape** — `{event_type, model: {id, name, status, version, run_id, user_id, api_schema}, timestamp, source: 'mlflow'}`. This is the shape that surfaces `model.api_schema` to the handler.

→ To get `model.api_schema` persisted on the site without another hokusai-site change, the data pipeline must send a payload that the site parses via the **original-format schema**, not the SDK schema. Practically: omit `token_id` at the top level so SDK parsing fails fast and the original-format parser runs.

### 1.2 Sending paths in this repo

There are two independent webhook senders:

| # | Sender | File | Triggered by | Current payload shape |
|---|---|---|---|---|
| A | `WebhookPublisher` | `src/events/publishers/webhook_publisher.py` | `ModelRegistryHooks.on_model_registered_with_baseline` (in turn called by `EnhancedModelRegistry.register_tokenized_model_with_events` / `register_baseline_with_events`) | flat SDK shape (`token_id`, `model_id`, `model_name`, `metric_name`, …) |
| B | `_notify_site_of_registration` | `hokusai-ml-platform/src/hokusai/cli.py` | `hokusai model register` CLI command | flat SDK shape (`token_id`, `model_name`, `model_version`, `metric_name`, `tags`, …) |

Default URL for both is now `https://hokus.ai/api/webhooks/model-registration` (PR #142 `54076da`).

### 1.3 MLflow signature → JSON Schema

`mlflow.models.signature.ModelSignature` has `inputs` and `outputs`, each a `mlflow.types.Schema`. A column-based `Schema` exposes `inputs` (list of `ColSpec` with `name`, `type`, `optional`); a tensor-based `Schema` returns `TensorSpec` items without column names. For col-spec signatures, conversion to JSON Schema (`type: 'object', properties, required`) is straightforward via `MlflowDataType` mapping:

| MLflow type | JSON Schema |
|---|---|
| `string` | `{"type":"string"}` |
| `integer` / `long` | `{"type":"integer"}` |
| `float` / `double` | `{"type":"number"}` |
| `boolean` | `{"type":"boolean"}` |
| `binary` | `{"type":"string","format":"byte"}` |
| `datetime` | `{"type":"string","format":"date-time"}` |

For tensor specs (no column names) we return `None` and let the site fall back to its sensible defaults.

The signature is fetched via `mlflow.models.get_model_info(model_uri)` after registration. Failure (network, permission, missing artifact, no signature logged) MUST degrade silently — `api_schema` is optional and the webhook must still succeed without it.

### 1.4 Acceptance contract from the site

- `api_schema.inputSchema` — JSON Schema object.
- `api_schema.outputSchema` — JSON Schema object.
- Optional: `endpoint`, `method`, `exampleInput`, `exampleOutput`, `errorCodes` — site fills sensible defaults if omitted.
- Field is optional end-to-end.

### 1.5 Decision summary

- **Switch both webhook senders to the original MLflow payload shape** (`{event_type, model: {…}, timestamp, source: 'mlflow'}`). This is the single coherent way to deliver `model.api_schema` without a hokusai-site code change. The site has accepted both shapes since #232; we are only narrowing the sent shape. Idempotency on the site is computed from `event_type:model.id:timestamp` so the existing `X-Hokusai-Signature` HMAC and `X-Hokusai-Idempotency-Key` header continue to work.
- Add a small `mlflow_signature_to_api_schema` utility used by both senders.
- Carry `api_schema` through `ModelReadyToDeployMessage` so callers can inject it without coupling `WebhookPublisher` to MLflow.
- Derive the signature at the call sites that have access to MLflow / model URI; keep failures non-fatal.

## 2. Implementation Phases

### Phase 1 — Schema conversion utility (pure, easy to test)

**New file:** `src/events/api_schema.py`

Public API:

```python
def derive_api_schema(signature: Optional["ModelSignature"]) -> Optional[Dict[str, Any]]
def derive_api_schema_from_uri(model_uri: Optional[str]) -> Optional[Dict[str, Any]]
```

- `derive_api_schema(signature)` — returns `{"inputSchema": …, "outputSchema": …}` or `None` (any failure / missing piece).
- `derive_api_schema_from_uri(model_uri)` — convenience wrapper that calls `mlflow.models.get_model_info(model_uri)` and feeds `info.signature` into `derive_api_schema`. Catches all exceptions, logs a warning, returns `None`.
- Internal `_schema_to_jsonschema(schema)` handles only column-based `mlflow.types.Schema`; for tensor specs (or anything without `.inputs` of `ColSpec`) returns `None`.
- Internal `_mlflow_type_to_jsonschema(t)` returns the `{"type": …}` (and optionally `"format"`) dict per the table above; unknown types return `None` so the column gets dropped (or the whole conversion bails).

### Phase 2 — Carry `api_schema` through `ModelReadyToDeployMessage`

**File:** `src/events/schemas.py`

- Add optional field: `api_schema: Optional[Dict[str, Any]] = None`.
- Update `validate()` schema to accept `api_schema` as `{"type": ["object", "null"]}` (no further structural validation — the field is opaque to us).
- Update `to_dict()` round-trip path (already handled by `asdict`, just verify).

### Phase 3 — Update `WebhookPublisher` to send original MLflow shape

**File:** `src/events/publishers/webhook_publisher.py`

Replace `_create_webhook_payload` so that it returns:

```python
{
    "event_type": "model_registered",
    "model": {
        "id": message.token_symbol.lower(),     # site finds model by slug / token ticker
        "name": message.model_name,
        "status": message.status,                # "registered"
        "version": message.model_version,
        "run_id": message.mlflow_run_id,         # only if not None
        "user_id": <pulled from tags.user_id or tags.fulfilled_by_user_id>,  # only if present
        "api_schema": message.api_schema,        # only if not None
    },
    "timestamp": message.timestamp.isoformat() + "Z",  # ISO 8601 UTC
    "source": "mlflow",
}
```

- Drop `None`-valued fields from the inner `model` dict — keep the wire payload clean and let the original Zod schema treat them as `optional`.
- Update `_validate_payload` to validate the new shape: required `event_type`, `model.id`, `model.name`, `model.status`, `timestamp`, `source`. Drop the SDK-shape required-field list.
- Keep the `X-Hokusai-Signature` HMAC unchanged; signature is over the body bytes regardless of shape.
- Keep `X-Hokusai-Idempotency-Key` header — harmless, the site ignores it but it is useful for retry tracing on our side.
- Plumb `api_schema` through `publish_model_ready` (kwarg) → constructs `ModelReadyToDeployMessage`.

**File:** `src/events/publishers/redis_publisher.py` and `src/events/publishers/composite_publisher.py`

- Add the `api_schema` kwarg pass-through to keep interface symmetry. Redis publisher just stores the field in the queued message; downstream consumers get it for free.

### Phase 4 — Wire api_schema into the `ModelRegistryHooks` chain

**File:** `src/services/model_registry_hooks.py`

- Add `model_uri: Optional[str] = None` and/or `api_schema: Optional[Dict[str, Any]] = None` kwargs to `on_model_registered_with_baseline`.
- Inside the hook: if `api_schema` is `None` and `model_uri` is provided, call `derive_api_schema_from_uri(model_uri)`. Failure → `None`. Pass result to `publisher.publish_model_ready(api_schema=…)`.

**File:** `src/services/enhanced_model_registry.py`

- `register_tokenized_model_with_events`: forward `model_uri` to the hook (already in scope as a parameter).
- `register_baseline_with_events`: forward `entry.mlflow_version` → build `f"models:/{model_type}/{entry.mlflow_version}"` URI, pass to hook. If `mlflow_version` is missing, skip URI.

### Phase 5 — Update the SDK CLI sender

**File:** `hokusai-ml-platform/src/hokusai/cli.py`

- After `registry.register_tokenized_model(...)` returns, call `derive_api_schema_from_uri(f"models:/{result['model_name']}/{result['version']}")` to fetch the signature post-registration. Wrap in try/except; default to `None`.
- Refactor `_notify_site_of_registration` to build the original-format payload:

  ```python
  payload = {
      "event_type": "model_registered",
      "model": {
          "id": result["token_id"].lower(),
          "name": result["model_name"],
          "status": "registered",
          "version": str(result["version"]),
          **({"run_id": result["mlflow_run_id"]} if result.get("mlflow_run_id") else {}),
          **({"api_schema": api_schema} if api_schema else {}),
      },
      "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
      "source": "mlflow",
  }
  ```

- The CLI cannot import the data-pipeline `src/events/api_schema.py` (separate package). Add a small helper inside `hokusai-ml-platform/src/hokusai/registration/api_schema.py` (or inline near `_notify_site_of_registration`) that re-implements the same `signature → ModelApiSpec` conversion. Keep it self-contained — no shared module across packages.
- Update CLI signature so `_notify_site_of_registration` accepts `api_schema` argument (or derives internally given a URI).

### Phase 6 — Tests

#### Phase 6.1 — Unit: schema conversion (`tests/unit/test_api_schema.py`, new)

- Column-spec signature with mixed types (string, integer, double, boolean) → exact JSON Schema output, with `required` reflecting non-optional cols.
- Column-spec signature with `optional=True` columns → those keys appear in `properties` but not in `required`.
- Tensor-spec signature → returns `None`.
- `signature=None` → returns `None`.
- `derive_api_schema_from_uri` with patched `get_model_info`:
  - Happy path returns dict.
  - `get_model_info` raises → returns `None`, no exception bubbles.
  - `get_model_info(...).signature is None` → returns `None`.

#### Phase 6.2 — Unit: webhook publisher (`tests/unit/test_webhook_publisher.py`, update)

- Update existing `_create_webhook_payload` / `_validate_payload` tests to assert the new original-format shape (`payload["model"]["id"] == token.lower()`, `payload["source"] == "mlflow"`, no top-level `token_id`).
- New: `api_schema` propagates through `publish_model_ready` → ends up at `payload["model"]["api_schema"]`.
- New: `api_schema` omitted when `None` (key absent from `model` dict).
- New: `user_id` extracted from `tags.user_id` → `payload["model"]["user_id"]`.
- Validate that `_send_webhook` posts JSON whose decoded structure parses against the original Zod schema (compile a minimal jsonschema check, or assert key presence).

#### Phase 6.3 — Unit: registry hooks (`tests/unit/test_model_registry_hooks.py`, update)

- `on_model_registered_with_baseline` with `model_uri` set + patched `derive_api_schema_from_uri` returning a dict → `publisher.publish_model_ready` called with `api_schema=<dict>`.
- Same with `derive_api_schema_from_uri` returning `None` → `api_schema` kwarg is `None`.
- Caller-provided `api_schema` kwarg takes precedence over URI-derived one.

#### Phase 6.4 — Unit: CLI notifier (`hokusai-ml-platform/tests/test_cli.py`, update)

- Stub `urllib.request.urlopen` and capture body. Assert payload is original-format with `model.id`, `model.name`, `model.status == "registered"`, `source == "mlflow"`.
- With patched `get_model_info` returning a synthetic signature → body contains `model.api_schema.inputSchema.properties`.
- With patched `get_model_info` raising → body has `model` block but no `api_schema` key.

#### Phase 6.5 — Integration: webhook delivery (`tests/integration/test_webhook_integration.py`, update)

- Update assertions for the new payload shape (replace `received["token_id"]` etc. with `received["model"]["id"]`).
- Add a test that posts a payload with `api_schema` and asserts the test server received the nested object intact.

#### Phase 6.6 — Smoke / acceptance trace

- Document (in commit message + PR) how to verify against a staging hokusai-site: log a model with `mlflow.pyfunc.log_model(..., signature=infer_signature(X, y))`, register via `EnhancedModelRegistry.register_tokenized_model_with_events`, confirm `Model.api_schema` is non-null on the site DB and the API integration tab renders the inferred fields.

### Phase 7 — Status reporting + polish

- Update status file at major checkpoints (`Phase N start`, `Phase N done`).
- Re-run `pytest tests/unit/test_webhook_publisher.py tests/unit/test_model_registry_hooks.py tests/unit/test_api_schema.py hokusai-ml-platform/tests/test_cli.py` — green before PR.
- Lint: `ruff` over touched files. (`ruff_original.toml` is committed; default `ruff check src tests` per repo convention.)

## 3. Edge Cases & Risk Notes

- **No signature logged** — `derive_api_schema_from_uri` returns `None`, payload omits `api_schema`. Site treats as no-op. ✅
- **`mlflow.models.get_model_info` requires MLflow tracking URI** — already configured in the same process for both call sites (CLI sets it via `mlflow.set_tracking_uri`; service path runs alongside MLflow). If misconfigured, exception is swallowed, payload still sent. ✅
- **Tensor signatures** — explicitly return `None`. The site handles missing `api_schema` fine. ✅
- **Site Zod parsing precedence** — we deliberately drop `token_id` from the top level so the SDK parser fails and the original parser runs. Any future flat field added by the data pipeline that collides with `sdkWebhookSchema.required` could resurrect that path. Add a regression test that fails if `_create_webhook_payload` ever emits both `token_id` and `model` at the top level.
- **Idempotency** — the site computes its own key from `event_type:model.id:timestamp`. Two registrations of the same token within the same UTC second with the same timestamp string would dedupe. This matches existing behaviour (we already pin `timestamp = message.timestamp`).
- **Backward-compat for prior data-pipeline payloads in flight** — none expected; webhooks are synchronous from this repo and no queue holds old payloads.
- **Logged eventLog payload changes** — the site stores the validated (transformed) payload in `EventLog.payload`. The new shape will appear there going forward. This is observable but acceptable; existing eventLog rows are untouched.

## 4. Files Touched (summary)

**New:**
- `src/events/api_schema.py`
- `tests/unit/test_api_schema.py`
- `hokusai-ml-platform/src/hokusai/registration/api_schema.py` *(or inline helper inside `cli.py`)*

**Modified:**
- `src/events/schemas.py`
- `src/events/publishers/webhook_publisher.py`
- `src/events/publishers/redis_publisher.py`
- `src/events/publishers/composite_publisher.py`
- `src/services/model_registry_hooks.py`
- `src/services/enhanced_model_registry.py`
- `hokusai-ml-platform/src/hokusai/cli.py`
- `tests/unit/test_webhook_publisher.py`
- `tests/unit/test_model_registry_hooks.py`
- `tests/integration/test_webhook_integration.py`
- `hokusai-ml-platform/tests/test_cli.py`

## 5. Release Readiness

- `database_change_risk`: none
- `env_changes`: none
- `config_changes`: none
- `manual_steps`: none

No DB migration, no new env vars, no infra changes. The deployed Docker image picks up the new payload shape automatically; the site already accepts both shapes (and prefers the original-format path because we are dropping `token_id` from the top level).

## 6. Open Questions / Follow-ups

- Do we want a parallel SDK-format `api_schema` propagation in hokusai-site `webhook-utils.ts` so older data-pipeline clients (e.g., contributor-side SDK installs that haven't pulled this update) can also surface `api_schema`? Not in scope here; track separately if observed in the wild.
- Should `register_tokenized_model_with_events` accept an explicit `api_schema` override for cases where the caller already has a `ModelApiSpec` (e.g., proposal authors providing it)? Defer until concrete need.
