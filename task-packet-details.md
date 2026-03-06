## 1. Objective

### What
Create an `EvaluationSchedule` SQLAlchemy model, Pydantic schemas, service layer, and CRUD API endpoints that allow model owners to configure automatic evaluation schedules for their models.

### Why
Model owners need continuous benchmark tracking without manual triggers. This is the configuration layer for the V1 Scheduled Evaluations milestone — a future scheduler will read these records to trigger evaluations, but this task only covers the configuration CRUD.

### Scope In
- `EvaluationSchedule` SQLAlchemy model with: id (UUID PK), model_id (string, indexed, unique), cron_expression (string), enabled (bool), last_run_at (datetime nullable), next_run_at (datetime nullable), created_at, updated_at
- Alembic migration for the new table
- Pydantic schemas: Create, Update, Response
- Service layer with BenchmarkSpec prerequisite check
- API endpoints: POST, GET, PUT, DELETE at `/api/v1/models/{model_id}/evaluation-schedule`
- Unit tests for model, schemas, service, and routes

### Scope Out
- Actual cron scheduler/worker that triggers evaluations (future task)
- Integration with evaluation execution pipeline
- UI components in hokusai-site
- `next_run_at` computation from cron expression (future — just store as provided or null)

---

## 2. Technical Context

### Repository
`hokusai-data-pipeline` (this repo)

### Key Files

**New files:**
- `src/api/models/evaluation_schedule.py` — SQLAlchemy model
- `src/api/schemas/evaluation_schedule.py` — Pydantic schemas
- `src/api/routes/evaluation_schedule.py` — FastAPI router
- `src/api/services/governance/evaluation_schedule.py` — Service layer
- `migrations/versions/011_add_evaluation_schedule.py` — Alembic migration
- `tests/unit/test_evaluation_schedule_service.py` — Service tests
- `tests/unit/test_evaluation_schedule_routes.py` — Route tests
- `tests/unit/test_evaluation_schedule_schemas.py` — Schema tests

**Modified files:**
- `src/api/models/__init__.py` — Register new model
- `src/api/schemas/__init__.py` — Export new schemas
- `src/api/routes/__init__.py` — Register new router
- `src/api/main.py` — Include router
- `src/api/dependencies.py` — Add service factory if needed

### Relevant Subsystem Specs

- **Api** (`.wavemill/context/src-api.md`)
  - **Key Constraints**: Follow `DatasetLicense` model pattern (UUID PK, created_at/updated_at); follow `src/api/routes/benchmark_specs.py` pattern for CRUD routers with `require_auth`
  - **Known Failure Modes**: Evaluation fails with missing dataset error when no BenchmarkSpec — this task adds another guard at schedule creation time
  - **Testing Patterns**: BenchmarkSpec service/schema/route tests as reference

- **Database** (`.wavemill/context/src-database.md`)
  - **Key Constraints**: Use Alembic for migrations; follow existing migration numbering (next is 011)

- **Evaluation** (`.wavemill/context/src-evaluation.md`)
  - **Key Constraints**: Schedule config is read-only from evaluation perspective — this task only creates the config store

### Dependencies
- `src/api/models/benchmark_spec.py` — Must query BenchmarkSpec to validate prerequisite
- `src/api/services/governance/benchmark_specs.py` — `get_active_spec_for_model()` used for prerequisite check
- `src/api/models/db_base.py` — Base class for SQLAlchemy models
- `croniter` package (for cron expression validation) — add to `requirements-api.txt`

### Architecture Notes
- Follow the BenchmarkSpec CRUD pattern established in HOK-914/915/916 (the most recent and closest analog)
- One schedule per model (unique constraint on model_id) — POST creates, PUT updates
- Route nesting under `/api/v1/models/{model_id}/evaluation-schedule` (singular, since it's one-per-model)
- Service layer validates BenchmarkSpec existence before allowing schedule creation

---

## 3. Implementation Approach

1. **Add `croniter` dependency** to `requirements-api.txt` for cron expression validation

2. **Create SQLAlchemy model** (`src/api/models/evaluation_schedule.py`)
   - UUID primary key, model_id (String, unique index), cron_expression (String), enabled (Boolean, default True), last_run_at (DateTime nullable), next_run_at (DateTime nullable), created_at/updated_at with server defaults
   - Follow `DatasetLicense` / `BenchmarkSpec` model patterns

3. **Create Alembic migration** (`migrations/versions/011_add_evaluation_schedule.py`)
   - Create `evaluation_schedules` table with unique index on `model_id`

4. **Create Pydantic schemas** (`src/api/schemas/evaluation_schedule.py`)
   - `EvaluationScheduleCreate`: model_id (auto from path), cron_expression (required), enabled (optional, default True)
   - `EvaluationScheduleUpdate`: cron_expression (optional), enabled (optional), next_run_at (optional)
   - `EvaluationScheduleResponse`: all fields, `ConfigDict(from_attributes=True)`

5. **Create service layer** (`src/api/services/governance/evaluation_schedule.py`)
   - `create_schedule(db, model_id, data)` — check BenchmarkSpec exists, check no existing schedule, create
   - `get_schedule(db, model_id)` — return schedule or None
   - `update_schedule(db, model_id, data)` — partial update
   - `delete_schedule(db, model_id)` — delete and return success bool

6. **Create route file** (`src/api/routes/evaluation_schedule.py`)
   - `POST /api/v1/models/{model_id}/evaluation-schedule` — create (409 if no BenchmarkSpec, 409 if already exists)
   - `GET /api/v1/models/{model_id}/evaluation-schedule` — get (404 if not found)
   - `PUT /api/v1/models/{model_id}/evaluation-schedule` — update (404 if not found)
   - `DELETE /api/v1/models/{model_id}/evaluation-schedule` — delete (404 if not found)
   - All endpoints use `require_auth` and audit logging

7. **Wire up** — register model in `__init__.py`, add router to `main.py`, export schemas

8. **Write tests** — unit tests for schemas (validation), service (CRUD + BenchmarkSpec check), routes (HTTP layer)

---

## 4. Success Criteria

### Functional Requirements

- [ ] **[REQ-F1]** `EvaluationSchedule` SQLAlchemy model exists with all specified fields (id, model_id, cron_expression, enabled, last_run_at, next_run_at, created_at, updated_at) and model_id has a unique index
- [ ] **[REQ-F2]** POST endpoint creates a schedule when the model has an active BenchmarkSpec
- [ ] **[REQ-F3]** POST endpoint returns 409 when the model has no active BenchmarkSpec
- [ ] **[REQ-F4]** POST endpoint returns 409 when a schedule already exists for the model
- [ ] **[REQ-F5]** GET endpoint returns the schedule for a given model_id (404 if none)
- [ ] **[REQ-F6]** PUT endpoint updates an existing schedule's fields (404 if none)
- [ ] **[REQ-F7]** DELETE endpoint removes the schedule (404 if none)
- [ ] **[REQ-F8]** Cron expression validation rejects invalid expressions (400)
- [ ] **[REQ-F9]** All endpoints enforce authentication via `require_auth`

### Non-Functional Requirements
- [ ] Alembic migration is reversible (has downgrade)
- [ ] No N+1 queries in service layer

### Code Quality
- [ ] Follows existing codebase patterns (BenchmarkSpec CRUD as reference)
- [ ] Python types are correct throughout
- [ ] No lint errors (`ruff check`)

---

## 5. Implementation Constraints

- **Code style**: Follow existing patterns in `src/api/models/benchmark_spec.py`, `src/api/routes/benchmarks.py`, `src/api/schemas/benchmark_spec.py`
- **Testing**: Unit tests with mocked DB sessions (follow `tests/unit/test_benchmark_spec_service.py` pattern)
- **Security**: All endpoints require auth; no unauthenticated access
- **Cron validation**: Use `croniter.is_valid()` — do not write custom cron parsing
- **Database**: UUID primary keys, `server_default=sa.text("gen_random_uuid()")` for PG compatibility
- **Migration numbering**: Next available is `011_`
- **One schedule per model**: Enforce via unique constraint on `model_id`, not application logic alone

---

## 6. Validation Steps

### Functional Requirement Validation

**[REQ-F1] EvaluationSchedule model has correct schema**

Validation scenario:
1. Setup: Read `src/api/models/evaluation_schedule.py`
2. Action: Inspect model class attributes
3. Expected result:
   - `id` column: UUID, primary key, server-generated default
   - `model_id` column: String, not nullable, unique index
   - `cron_expression` column: String, not nullable
   - `enabled` column: Boolean, default True
   - `last_run_at` column: DateTime, nullable
   - `next_run_at` column: DateTime, nullable
   - `created_at` column: DateTime, server default `now()`
   - `updated_at` column: DateTime, server default `now()`, onupdate
4. Edge cases:
   - Table name is `evaluation_schedules`
   - Index name follows convention: `ix_evaluation_schedules_model_id`

**[REQ-F2] POST creates schedule with valid BenchmarkSpec**

Validation scenario:
1. Setup: Mock DB with model "model-123" that has an active BenchmarkSpec
2. Action: `POST /api/v1/models/model-123/evaluation-schedule` with body `{"cron_expression": "0 */6 * * *"}`
3. Expected result: HTTP 201, response contains `id`, `model_id: "model-123"`, `cron_expression: "0 */6 * * *"`, `enabled: true`
4. Edge cases:
   - `enabled: false` in body → Schedule created but disabled
   - Minimal body (only cron_expression) → defaults applied correctly

**[REQ-F3] POST returns 409 when no BenchmarkSpec**

Validation scenario:
1. Setup: Mock DB with model "model-456" that has NO BenchmarkSpec
2. Action: `POST /api/v1/models/model-456/evaluation-schedule` with body `{"cron_expression": "0 */6 * * *"}`
3. Expected result: HTTP 409, error message indicates BenchmarkSpec is required
4. Edge cases:
   - Model has an inactive BenchmarkSpec (is_active=False) → Also 409

**[REQ-F4] POST returns 409 when schedule already exists**

Validation scenario:
1. Setup: Mock DB with model "model-123" that has BenchmarkSpec AND existing schedule
2. Action: `POST /api/v1/models/model-123/evaluation-schedule` with body `{"cron_expression": "0 0 * * *"}`
3. Expected result: HTTP 409, error message indicates schedule already exists

**[REQ-F5] GET returns schedule or 404**

Validation scenario:
1. Setup: Mock DB with schedule for "model-123"
2. Action: `GET /api/v1/models/model-123/evaluation-schedule`
3. Expected result: HTTP 200, full schedule object returned
4. Edge cases:
   - No schedule exists → HTTP 404 with message "No evaluation schedule found for model model-999"

**[REQ-F6] PUT updates existing schedule**

Validation scenario:
1. Setup: Mock DB with existing schedule for "model-123" (cron="0 */6 * * *", enabled=True)
2. Action: `PUT /api/v1/models/model-123/evaluation-schedule` with body `{"cron_expression": "0 0 * * *", "enabled": false}`
3. Expected result: HTTP 200, updated fields reflected in response
4. Edge cases:
   - Partial update (only `enabled`) → Other fields unchanged
   - No schedule exists → HTTP 404

**[REQ-F7] DELETE removes schedule**

Validation scenario:
1. Setup: Mock DB with schedule for "model-123"
2. Action: `DELETE /api/v1/models/model-123/evaluation-schedule`
3. Expected result: HTTP 204 (no content)
4. Edge cases:
   - No schedule → HTTP 404

**[REQ-F8] Invalid cron expression rejected**

Validation scenario:
1. Setup: N/A
2. Action: `POST /api/v1/models/model-123/evaluation-schedule` with body `{"cron_expression": "not a cron"}`
3. Expected result: HTTP 422 (validation error), message indicates invalid cron expression
4. Edge cases:
   - Empty string → 422
   - 6-field cron (with seconds) → Accept or reject per `croniter` behavior — document which
   - Valid 5-field cron `"0 */6 * * *"` → Accepted
   - `"@daily"` shorthand → Accepted if croniter supports it

**[REQ-F9] Auth enforcement**

Validation scenario:
1. Setup: No auth token
2. Action: Any endpoint without Authorization header
3. Expected result: HTTP 401 Unauthorized

---

### Input/Output Verification

**Valid Inputs:**
- POST `{"cron_expression": "0 */6 * * *"}` → 201, schedule created with enabled=true
- POST `{"cron_expression": "0 0 * * 1", "enabled": false}` → 201, schedule created disabled
- PUT `{"enabled": false}` → 200, schedule updated
- PUT `{"cron_expression": "30 2 * * *"}` → 200, cron updated

**Invalid Inputs:**
- POST `{"cron_expression": "invalid"}` → 422, "Invalid cron expression"
- POST `{}` (missing cron_expression) → 422, "cron_expression is required"
- POST without auth → 401
- GET for nonexistent model → 404
- DELETE for nonexistent schedule → 404

---

### Standard Validation Commands

```bash
# 1. Lint passes
ruff check src/api/models/evaluation_schedule.py src/api/schemas/evaluation_schedule.py src/api/routes/evaluation_schedule.py src/api/services/governance/evaluation_schedule.py
# Expected: no errors

# 2. Tests pass
pytest tests/unit/test_evaluation_schedule_service.py tests/unit/test_evaluation_schedule_routes.py tests/unit/test_evaluation_schedule_schemas.py -v
# Expected: all tests pass

# 3. Migration check
python -c "from migrations.versions import *; print('Migration imports OK')"
# Expected: no import errors

# 4. Model import check
python -c "from src.api.models.evaluation_schedule import EvaluationSchedule; print(EvaluationSchedule.__tablename__)"
# Expected: prints "evaluation_schedules"
```

---

### Manual Verification Checklist

- [ ] Migration file has both `upgrade()` and `downgrade()` functions
- [ ] Unique constraint on model_id prevents duplicate schedules at DB level
- [ ] Schema validation rejects invalid cron expressions before hitting the service layer
- [ ] Service checks BenchmarkSpec existence before creating schedule
- [ ] All four HTTP methods (POST, GET, PUT, DELETE) are registered on the router
- [ ] Router is included in `src/api/main.py`

---

## 8. Definition of Done

- [ ] All success criteria met
- [ ] All validation steps pass with specific, measurable outcomes
- [ ] Each functional requirement has at least one concrete validation scenario
- [ ] Edge cases are documented and tested
- [ ] No unrelated changes included
- [ ] Commit message references HOK-920
- [ ] PR created with clear description

---

## 9. Rollback Plan

- Revert commit: `git revert <sha>`
- Migration rollback: `alembic downgrade -1` (drops `evaluation_schedules` table)
- No data dependencies — table is new, no existing data affected
- No other services depend on this table yet

---

## 10. Proposed Labels

**Risk Level**: `Risk: Medium`
**Justification**: New model + migration + CRUD endpoints — follows well-established patterns but adds a new DB table.

**Files to Modify**:
- `src/api/models/evaluation_schedule.py`
- `src/api/schemas/evaluation_schedule.py`
- `src/api/routes/evaluation_schedule.py`
- `src/api/services/governance/evaluation_schedule.py`
- `migrations/versions/011_add_evaluation_schedule.py`

**Label**: `Files: evaluation_schedule.py, 011_add_evaluation_schedule.py`

**Architectural Layer**: `Layer: API`, `Layer: Database`

**Area**: `Area: Evaluation`

**Test Coverage**: `Tests: Unit`

### Label Summary

```
Suggested labels for this task:
- Risk: Medium
- Files: evaluation_schedule.py, 011_add_evaluation_schedule.py
- Layer: API, Database
- Area: Evaluation
- Tests: Unit
```

**How these labels help the autonomous workflow:**
- **Risk: Medium** — Max 2 Medium risk tasks in parallel
- **Files** — New files, unlikely to conflict with parallel tasks
- **Layer: API, Database** — Migration requires sequential deployment ordering
- **Area: Evaluation** — Avoid running with other evaluation-area tasks
- **Tests: Unit** — Can run in parallel with other unit test tasks