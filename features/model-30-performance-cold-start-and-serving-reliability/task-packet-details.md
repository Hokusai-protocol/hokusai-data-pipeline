## 1. Objective

### What
Verify, and close any residual gaps in, the Model 30 cold-start and serving-reliability bucket by running end-to-end cold/warm benchmarks, confirming the latency budget holds in CI and against the deployed service, and producing checked-in evidence that Model 30 returns valid predictions reliably after deployment.

### Why
HOK-1869 is the parent bucket for sub-tasks HOK-1874 (cold-start / cache-warming) and HOK-1875 (latency budget), both marked Done. The bucket itself is still open because nothing has yet confirmed end-to-end that the deployed Model 30 path meets the bucket's goal ("serve valid predictions quickly and reliably after deployment"). Urgent priority with three component labels (router/serving/api) indicates this is on the critical path. Verifying the rollup prevents the sub-tasks from being claimed complete while a real-world cold-start or reliability regression still exists.

### Scope In
- End-to-end cold-start measurement against the deployed development API (`api.hokus.ai`) for Model 30 (`technical_task_router`), comparing to the budget in `configs/model_30_budget.yaml`.
- End-to-end warm-path latency measurement (p50/p95/p99) using `scripts/model_30/latency_smoke_check.py` and `scripts/model_30/profile_inference.py`.
- Verification that the prewarm path in `src/api/main.py` and the `/ready` endpoint in `src/api/routes/health.py` correctly gate readiness behind Model 30 warmup (tests added in HOK-1874 should pass on this branch).
- Verification that `.github/workflows/model-30-latency-check.yml` runs and gates merges on the latency budget.
- Reliability check: drive the curated payload set in `data/test_fixtures/model_30_curated_payload.json` against the deployed adapter and record success rate plus any 5xx/422 occurrences.
- Producing a short summary report under `features/model-30-performance-cold-start-and-serving-reliability/` capturing measured cold/warm numbers, success rate, and the budget config in effect.
- Small reliability fixes scoped to the Model 30 adapter / serving path if validation surfaces clear regressions (e.g. a missing retry, a stale cached handle, a Sentry-unswallowed exception). Larger fixes spawn follow-up issues.

### Scope Out
- Redesign or replacement of the Model 30 runtime / packaging (tracked separately under `features/investigate-model-30-runtime-and-packaging-alternatives-for-dramatic-speedup/`).
- Changes to the latency budget values themselves (HOK-1875 owns this; reopen that issue if the budget needs revision).
- Changes to the warmup architecture / strategy (HOK-1874 owns this).
- Generic API/MLflow infrastructure work outside the Model 30 serving path (auth, MLflow upgrade, DNS, mTLS — separate features).
- Model retraining or evaluation changes (`scripts/model_30/evaluate_technical_task_router.py`, scorer registry).
- 422 request-contract investigations (tracked under `features/investigate-model-30-request-contract-422s/`).

---

## 2. Technical Context

### Repository
`hokusai-data-pipeline` (this repo). No cross-repo changes are anticipated; if validation reveals that ALB health-check timing or ECS task-definition warmup grace needs adjustment, file a follow-up issue against `hokusai-infrastructure` rather than editing it here.

### Key Files

- `src/api/endpoints/model_30_adapter.py` — Model 30 inference adapter (entry point under test).
- `src/api/endpoints/model_serving.py` — Generic serving endpoint that dispatches to the Model 30 adapter.
- `src/api/main.py` — FastAPI app; contains startup prewarm logic from HOK-1874.
- `src/api/routes/health.py` — `/healthz` and `/ready` endpoints; `/ready` gates on Model 30 warmup state.
- `configs/model_30_budget.yaml` — Latency budget thresholds enforced by CI (owned by HOK-1875).
- `scripts/model_30/latency_smoke_check.py` — Smoke-check script used by the CI latency workflow.
- `scripts/model_30/profile_inference.py` — Local profiling harness.
- `scripts/diagnostics/compare_model_30_vs_21_latency.py` — Cold/warm comparison helper.
- `scripts/diagnostics/reproduce_model_30_inference.py` — Reproducer for direct inference calls.
- `.github/workflows/model-30-latency-check.yml` — CI workflow enforcing the budget.
- `data/test_fixtures/model_30_curated_payload.json` — Curated payload corpus for reliability checks.
- `data/test_fixtures/model_30_minimal_payload.json` — Minimal payload smoke input.
- `tests/unit/test_model_30_latency_budget.py` — Budget loading and enforcement.
- `tests/unit/test_model_30_warmup.py` — Warmup behavior contract (HOK-1874).
- `tests/unit/test_api_startup_prewarm.py` — Startup prewarm hook (HOK-1874).
- `tests/unit/test_ready_endpoint_model_30.py` — `/ready` gating on Model 30.
- `tests/unit/test_profile_inference.py` — Profile script unit tests.
- `tests/integration/test_model_30_mlflow_serving.py` — Integration test against an MLflow-backed serving path.
- `docs/model-30-serving.md` — Operational documentation for Model 30 serving.
- `features/model-30-performance-cold-start-and-serving-reliability/SUMMARY.md` (new) — Rollup verification report.

### Relevant Subsystem Specs

> ⚠️ **Knowledge Gap**: No subsystem specs found under `.wavemill/context/` for the Model 30 serving subsystem. After implementation, consider running `wavemill context init --force` to create subsystem documentation for the Model 30 serving / adapter path. The authoritative narrative lives in `docs/model-30-serving.md`, the related INVESTIGATION.md files under `features/`, and the test suite — treat those as the de facto spec until codified.

### Dependencies
- **HOK-1875 (Done)** — Latency budget. `configs/model_30_budget.yaml` and `.github/workflows/model-30-latency-check.yml` must be present and green.
- **HOK-1874 (Done)** — Cold-start / cache-warming. Startup prewarm must populate the adapter's model handle and `/ready` must reflect warm state.
- **MLflow service** — Adapter loads the registered Model 30 (`technical_task_router`) from MLflow; the development MLflow service must be reachable at `http://mlflow.hokusai-development.local:5000` for integration tests.
- **Auth service** — `/api/v1/models/{id}/predict` is JWT-gated; reliability runs need a valid development JWT.
- **ECS / ALB (hokusai-development)** — Cold-start measurements must use a forced new deployment so the latency captured is real (post-task-start, post-prewarm).

### Architecture Notes
- The serving path is: ALB → `api.hokus.ai` → `src/api/main.py` (FastAPI) → middleware (auth, scanner filter, validation logging) → `src/api/endpoints/model_serving.py` → `src/api/endpoints/model_30_adapter.py` → MLflow-loaded model.
- HOK-1874 introduced a startup prewarm hook in `src/api/main.py` and a Model 30 readiness gate in `src/api/routes/health.py`. Cold-start latency for the *first user request* should now be dominated by network + light Python work, not model load.
- HOK-1875 added `configs/model_30_budget.yaml` and a CI workflow that runs `scripts/model_30/latency_smoke_check.py`. The budget config has p50/p95/p99 thresholds for the warm path; cold-path thresholds may be separate (verify when reading the file).
- Both `model_30_adapter.py` and `model_serving.py` have churned heavily in recent commits. Read them fresh before changing anything; do not assume a particular function signature from older PRs.
- The latency-trace endpoint (`src/api/endpoints/latency_trace.py`) and the diagnostics scripts under `scripts/diagnostics/` exist specifically to attribute time across the inference stack — use them to ground claims rather than guessing.

---

## 3. Implementation Approach

1. **Audit the rollup state.** Read `configs/model_30_budget.yaml`, `src/api/main.py` (prewarm), `src/api/routes/health.py` (ready), `src/api/endpoints/model_30_adapter.py`, and `src/api/endpoints/model_serving.py`. Confirm the HOK-1874 and HOK-1875 deliverables are present and internally consistent on this branch. Note any obvious gaps (e.g. prewarm imports model but `/ready` never checks it, or budget config has placeholder thresholds).
2. **Run the local test suite for Model 30.** Execute the unit and integration tests listed under Key Files; capture failures. This is the first signal of latent rollup issues.
3. **Run the latency CI workflow locally (or in a draft PR).** Confirm `.github/workflows/model-30-latency-check.yml` passes against `configs/model_30_budget.yaml`. If it does not pass, root-cause whether it is a budget issue (HOK-1875), a serving regression (this task), or test/data drift (curated payload fixtures).
4. **Profile a cold path end-to-end.** Force a new ECS deployment for `hokusai-api-development` and time the first successful `/api/v1/models/{id}/predict` call against the curated payload. Capture timestamps for: ECS task START → first /healthz 200 → first /ready 200 → first /predict 200. Compare to budget cold-start thresholds.
5. **Profile the warm path end-to-end.** After the cold capture, run `scripts/model_30/latency_smoke_check.py` and `scripts/diagnostics/compare_model_30_vs_21_latency.py` (or equivalent warm driver) for at least 50 sequential calls. Record p50/p95/p99 and compare to `configs/model_30_budget.yaml`.
6. **Reliability sweep.** Iterate over `data/test_fixtures/model_30_curated_payload.json` (and the minimal fixture). Record HTTP status, top-level error code, and per-call latency. Required success rate threshold: see Section 4.
7. **Triage residual gaps.** For each failure observed in steps 2–6:
   - If the fix is small, scoped to the Model 30 serving path, and uncontroversial (e.g. swallowing a transient exception that should be surfaced, missing await, stale handle), patch it in this task with a focused commit.
   - If the fix is larger or crosses subsystem boundaries (auth, MLflow upgrade, infrastructure), open a follow-up issue with a link back to HOK-1869 and document the deferral in the summary report.
8. **Write the rollup summary.** Create `features/model-30-performance-cold-start-and-serving-reliability/SUMMARY.md` capturing: branch + commit SHA at measurement, environment, raw cold/warm numbers, success rate, budget values in effect, links to HOK-1874 / HOK-1875 / any new follow-ups, and a pass/fail verdict against Section 4. Do not duplicate the SUMMARY into other docs; cross-link `docs/model-30-serving.md` if a *user-facing* operational note is needed.
9. **Open the PR.** Reference HOK-1869 in the title, list HOK-1874 and HOK-1875 as the satisfied sub-tasks in the body, and attach the SUMMARY report. Keep the diff minimal — this is a verification rollup, not a re-implementation.

---

## 4. Success Criteria

### Functional Requirements

- [ ] **[REQ-F1]** With a fresh ECS deployment of `hokusai-api-development`, the first successful Model 30 prediction served via `/api/v1/models/{model_id}/predict` returns HTTP 200 within the cold-start latency threshold defined in `configs/model_30_budget.yaml`. If no separate cold threshold is defined there, the cold-path p100 over the first 5 requests after deploy must be ≤ 2× the warm p95 threshold in the same file.
- [ ] **[REQ-F2]** Warm-path latency for Model 30 against the curated payload (`data/test_fixtures/model_30_curated_payload.json`), measured over a single contiguous run of at least 50 sequential requests issued after warmup, satisfies every threshold in `configs/model_30_budget.yaml` (p50, p95, p99 as configured).
- [ ] **[REQ-F3]** The `/ready` endpoint in `src/api/routes/health.py` returns HTTP 503 (not 200) until the Model 30 prewarm completes successfully, and returns HTTP 200 thereafter. This is exercised by `tests/unit/test_ready_endpoint_model_30.py` and verified by observing the deployed service during a cold start.
- [ ] **[REQ-F4]** Running `python scripts/model_30/latency_smoke_check.py` against the deployed development API exits 0 and prints measured percentiles that are at or below the configured budget.
- [ ] **[REQ-F5]** Driving every payload in `data/test_fixtures/model_30_curated_payload.json` once against the deployed development API yields ≥ 99% HTTP 200 responses (i.e. at most one non-200 across the corpus, and that one must be a deterministic 4xx for a known-invalid payload, not a 5xx).
- [ ] **[REQ-F6]** `.github/workflows/model-30-latency-check.yml` runs on the PR for this issue and concludes with status `success`.
- [ ] **[REQ-F7]** `features/model-30-performance-cold-start-and-serving-reliability/SUMMARY.md` (new) exists in the PR and contains: commit SHA measured against, environment (`development`), raw numbers for cold/warm latencies and reliability sweep, the budget values in effect at measurement time, and an explicit "PASS" or "FAIL" verdict for each of REQ-F1..REQ-F5.

### Non-Functional Requirements
- [ ] No new dependencies added to `requirements-api.txt` or `pyproject.toml` solely to perform validation (use existing tooling).
- [ ] Any code changes preserve current behavior for non-Model-30 model IDs (e.g. Model 21 path remains untouched).
- [ ] Sentry/observability hooks already added by recent commits remain in place (do not silently swallow exceptions in the adapter).
- [ ] Docker builds, if performed, use `--platform linux/amd64` per `CLAUDE.md`.

### Code Quality
- [ ] Follows existing codebase patterns (FastAPI routers, pytest unit/integration layout, scripts under `scripts/model_30/` or `scripts/diagnostics/`).
- [ ] Python type hints preserved/added; no untyped `Any` introduced.
- [ ] `ruff` / `flake8` (whichever the repo uses) and `pytest` pass locally.

---

## 5. Implementation Constraints

- **Code style:** Match the existing Python conventions in `src/api/` — FastAPI routers, Pydantic schemas under `src/api/schemas/`, dependency injection via `src/api/dependencies.py`. Run the repo's standard lint before pushing.
- **Testing:** New behavioral assertions go under `tests/unit/` or `tests/integration/` mirroring existing layout. Do not modify the assertions in `tests/unit/test_model_30_latency_budget.py`, `tests/unit/test_model_30_warmup.py`, `tests/unit/test_api_startup_prewarm.py`, or `tests/unit/test_ready_endpoint_model_30.py` — those encode the HOK-1874/HOK-1875 contracts. Strengthening them with additional cases is allowed; loosening is not.
- **Security:** All `/api/v1/...` requests in validation runs must include a real auth-service-issued JWT. Do not bypass auth in production-shaped tests, and do not commit any token to the repo.
- **Performance:** Do not regress warm-path p95 beyond `configs/model_30_budget.yaml`. If a candidate reliability fix slows warm path, prefer reverting or revising the fix over loosening the budget.
- **Backwards compatibility:** `/api/v1/models/{id}/predict` request and response shapes are external contracts — do not change them. Internal helpers in `src/api/endpoints/model_30_adapter.py` can be refactored if needed for reliability fixes.
- **Scope discipline:** This is a rollup verification task, not a re-implementation of cold-start or budget. If verification reveals that HOK-1874 or HOK-1875 was incomplete, reopen the appropriate sub-task rather than absorbing scope here.
- **Docker:** If a redeploy is performed, build with `--platform linux/amd64` and push to the correct ECR repo (CI/CD uses `hokusai-api`, Terraform uses `hokusai/api` — use the CI/CD name when pushing via the standard workflow).

---

## 6. Validation Steps

### Functional Requirement Validation

**[REQ-F1] Cold-start budget is met**

Validation scenario:
1. Setup: Branch is deployed to `hokusai-api-development` via `aws ecs update-service --cluster hokusai-development --service hokusai-api-development --force-new-deployment`. Wait for the new task to reach RUNNING. Note the wall-clock timestamp of task START from `aws ecs describe-tasks`.
2. Action: Poll `/healthz` until 200, then poll `/ready` until 200, then issue exactly one POST to `/api/v1/models/{technical_task_router_id}/predict` with the body from `data/test_fixtures/model_30_minimal_payload.json` and a valid JWT. Capture: t_task_start, t_healthz_200, t_ready_200, t_first_predict_200, and the predict response latency reported by the client.
3. Expected result: First `/predict` returns HTTP 200 with a body that schema-matches the Model 30 response. (t_first_predict_200 − t_task_start) is ≤ the cold-start budget in `configs/model_30_budget.yaml` (or, if no explicit cold budget exists, ≤ 2× the warm p95 threshold).
4. Edge cases:
   - `/ready` never returns 200 within 5 minutes of task START → FAIL REQ-F1 and REQ-F3; investigate prewarm path in `src/api/main.py` before continuing.
   - First `/predict` returns 5xx → FAIL; capture the response body and CloudWatch log line and treat as a reliability regression.

**[REQ-F2] Warm-path budget is met across 50+ sequential requests**

Validation scenario:
1. Setup: The service from REQ-F1 is warm (at least one successful predict has completed). Have `data/test_fixtures/model_30_curated_payload.json` available locally.
2. Action: Issue at least 50 sequential POSTs to `/predict`, each with a payload sampled (round-robin or random with fixed seed) from the curated fixture. Record per-request latency; compute p50, p95, p99.
3. Expected result: Every percentile threshold present in `configs/model_30_budget.yaml` is satisfied by the measured run. No request returns 5xx.
4. Edge cases:
   - Any 5xx during the warm sweep → FAIL and capture the first failing payload for triage.
   - p99 exceeds budget while p95 passes → FAIL (the budget treats all configured percentiles as hard).

**[REQ-F3] /ready gates correctly on Model 30 warmup**

Validation scenario:
1. Setup: Force a new deployment as in REQ-F1.
2. Action: From the time `/healthz` first returns 200, poll `/ready` every 250ms until it returns 200. Also confirm that issuing a `/predict` call *before* `/ready` returns 200 either fails fast or is correctly queued (do not assume — observe).
3. Expected result: `/ready` returns 503 with a Model-30-specific body (e.g. `{"ready": false, "reasons": ["model_30_not_warm"]}` or equivalent — whatever the implementation chose) until prewarm finishes, then flips to 200 and stays 200.
4. Edge cases:
   - `/ready` returns 200 before prewarm has actually loaded the model (false-ready) → FAIL.
   - `/ready` permanently returns 503 → FAIL; treat as prewarm crash and check CloudWatch logs.

**[REQ-F4] latency_smoke_check.py exits 0 against deployed dev**

Validation scenario:
1. Setup: Service warm from REQ-F1.
2. Action: `python scripts/model_30/latency_smoke_check.py --target https://api.hokus.ai ...` (use the script's actual CLI; do not invent flags — read the file).
3. Expected result: Exit code 0; stdout contains measured percentiles all ≤ budget; stderr empty or informational only.
4. Edge cases:
   - Script exits non-zero with a budget violation → FAIL REQ-F2/F4.
   - Script exits non-zero due to auth → fix the invocation, not a verification failure.

**[REQ-F5] Reliability sweep ≥ 99% success**

Validation scenario:
1. Setup: Service warm. Curated fixture available.
2. Action: For each payload in `data/test_fixtures/model_30_curated_payload.json`, issue one POST to `/predict`. Record HTTP status and (for non-200) the response body's error code.
3. Expected result: ≥ 99% HTTP 200 across the corpus. Any non-200 must be a deterministic 4xx (e.g. 422 with a specific validation message) tied to a known-invalid payload, never a 5xx.
4. Edge cases:
   - One 5xx in the corpus → FAIL.
   - 422 on a payload that the curated fixture asserts should be valid → FAIL (escalate to the 422 investigation feature folder but mark this rollup FAIL).

**[REQ-F6] Latency CI workflow passes**

Validation scenario:
1. Setup: PR opened.
2. Action: Wait for `.github/workflows/model-30-latency-check.yml` to run.
3. Expected result: Workflow concludes with status `success`.
4. Edge cases:
   - Workflow fails on budget → re-run validation; if reproducible, treat as a serving regression in this task.
   - Workflow is skipped (path filter excludes changes) → manually trigger it via `workflow_dispatch` and confirm green.

**[REQ-F7] SUMMARY.md is present and complete**

Validation scenario:
1. Setup: PR opened.
2. Action: Open `features/model-30-performance-cold-start-and-serving-reliability/SUMMARY.md`.
3. Expected result: File contains, at minimum, all required sections: commit SHA, environment, raw cold numbers, raw warm numbers, success-rate sweep, budget snapshot, per-REQ pass/fail verdicts, links to HOK-1874/HOK-1875 and any spawned follow-ups.
4. Edge cases:
   - SUMMARY references thresholds that don't match the actual `configs/model_30_budget.yaml` at PR HEAD → FAIL (drifted report).
   - SUMMARY records FAIL on any REQ-F1..F5 → the PR is not Done; address the failure first.

---

### Input/Output Verification

**Valid Inputs:**
- Input: A curated payload from `data/test_fixtures/model_30_curated_payload.json` POSTed to `/api/v1/models/{technical_task_router_id}/predict` with a valid JWT, after `/ready` returns 200 → Expected: HTTP 200, JSON body conforming to the Model 30 response schema, latency under the warm p95 budget.
- Input: `data/test_fixtures/model_30_minimal_payload.json` POSTed against a freshly cold service post-`/ready` → Expected: HTTP 200, latency under the cold-start budget.

**Invalid Inputs:**
- Input: POST to `/predict` before `/ready` returns 200 → Expected: deterministic fast-fail (503 or queued-then-served; whichever the implementation actually does — verify, don't assume). No silent hangs and no 5xx.
- Input: Malformed payload (e.g. missing required field per `src/api/schemas/technical_task_router_inputs.py`) → Expected: HTTP 422 with a Pydantic validation error body identifying the missing field. No 5xx, no Sentry-swallowed exception.
- Input: Missing or invalid JWT → Expected: HTTP 401 from `src/middleware/auth.py`. No 500.

---

### Standard Validation Commands

```bash
# 1. Lint (use the repo's actual linter; ruff is the most likely)
ruff check src/ tests/ scripts/model_30/
# Expected: no errors

# 2. Targeted unit tests (Model 30 surface area)
pytest tests/unit/test_model_30_latency_budget.py \
       tests/unit/test_model_30_warmup.py \
       tests/unit/test_api_startup_prewarm.py \
       tests/unit/test_ready_endpoint_model_30.py \
       tests/unit/test_model_30_adapter.py \
       tests/unit/test_model_serving.py \
       tests/unit/test_profile_inference.py
# Expected: all pass

# 3. Integration test (requires MLflow reachable; will be skipped or run in CI)
pytest tests/integration/test_model_30_mlflow_serving.py
# Expected: passes or is skipped with a clear reason

# 4. Latency smoke check (against deployed dev)
python scripts/model_30/latency_smoke_check.py  # add flags per the script
# Expected: exit 0, percentiles ≤ budget
```

---

### Manual Verification Checklist

- [ ] Forced a new deployment of `hokusai-api-development` and observed `/ready` transition from 503 → 200 only after prewarm logs in CloudWatch indicate Model 30 is loaded.
- [ ] Drove the curated fixture corpus against the deployed dev service and confirmed ≥ 99% 200 responses with zero 5xx.
- [ ] CloudWatch log group `/ecs/hokusai-api-development` shows no unhandled exceptions from `model_30_adapter.py` during the verification window.
- [ ] Sentry (if integrated) shows no new Model 30 issues triggered by the verification run.
- [ ] `features/model-30-performance-cold-start-and-serving-reliability/SUMMARY.md` exists, is committed, and matches observed numbers.

---

## 7. Definition of Done

- [ ] All [REQ-F1]..[REQ-F7] criteria met and recorded as PASS in SUMMARY.md.
- [ ] All validation steps executed; outputs (numbers, status codes) captured in SUMMARY.md.
- [ ] No unrelated changes included in the PR.
- [ ] Sub-tasks HOK-1874 and HOK-1875 referenced in the PR description; HOK-1869 referenced in the title.
- [ ] PR created with a clear description and the SUMMARY artifact linked.
- [ ] If any residual gap was deferred, a follow-up Linear issue exists and is linked from SUMMARY.md.

---

## 8. Rollback Plan

- **Code revert:** This task is primarily verification. If any small code fix is included and turns out to regress the warm path, revert with `git revert <sha>` and redeploy the previous image. Because the budget CI gate is in place, a regression would also be caught pre-merge.
- **Deployment revert:** If a forced redeploy of `hokusai-api-development` exposes a latent reliability issue and rolling forward is not fast enough, redeploy the previous image tag found in ECR (`hokusai-api` repo, prior commit SHA tag) via `aws ecs update-service ... --task-definition <prior-task-def-arn>`.
- **No data migrations** are introduced by this task; no DB rollback required.
- **No feature flag** is introduced; the Model 30 path is already live.

---

## 9. Release Readiness
- **database_change_risk**: none
- **env_changes**: none
- **config_changes**: none
- **manual_steps**: Force a new ECS deployment of `hokusai-api-development` after merging to capture an authentic cold-start measurement; archive the SUMMARY.md results.

---

## 10. Proposed Labels

**Risk Level** (Required):

**Selected**: `Risk: Medium`

**Justification**: Verification-led rollup against a live serving path. No schema or contract changes are expected, but any incidental fix touches the model serving hot path, and the task involves a forced ECS redeploy of the dev API — Medium is the right floor.

---

**Files to Modify** (Auto-detected):
- `src/api/endpoints/model_30_adapter.py` (only if a reliability gap is found)
- `src/api/endpoints/model_serving.py` (only if a reliability gap is found)
- `features/model-30-performance-cold-start-and-serving-reliability/SUMMARY.md` (new)
- `scripts/model_30/latency_smoke_check.py` (only if script needs a minor fix)
- `docs/model-30-serving.md` (only if user-facing operational note needed)

**Label**: `Files: model_30_adapter.py, model_serving.py, SUMMARY.md, latency_smoke_check.py, model-30-serving.md`

**Purpose**: Prevents parallel tasks from modifying the same Model 30 serving files.

---

**Architectural Layer** (Recommended):

**Selected**: `Layer: API`, `Layer: Service`

**Purpose**: API endpoints (`src/api/endpoints/`) and service-layer adapter logic. Can run in parallel with UI/Database/Infra tasks.

---

**Area** (Recommended):

**Selected**: `Area: ModelServing` (component label already in Linear: `Component: Modelservingservice`, `Component: Modelapiservice`, `Component: Model30technicaltaskrouter`)

**Purpose**: Avoid running concurrent tasks against the Model 30 / serving path.

---

**Test Coverage** (Auto-detected):

**Selected**: `Tests: Integration`

**Purpose**: Includes targeted unit tests plus an integration test (`tests/integration/test_model_30_mlflow_serving.py`) plus live deployment smoke check. Can run in parallel with other Integration tasks that touch unrelated subsystems.

---

**Component** (Optional):

**Selected**: `Component: Model30TechnicalTaskRouter`, `Component: ModelServingService`, `Component: ModelAPIService` (matches Linear labels already on the issue).

**Purpose**: Avoid running 2+ tasks modifying the Model 30 serving components in parallel.

---

### Label Summary

```
Suggested labels for this task:
- Risk: Medium
- Files: model_30_adapter.py, model_serving.py, SUMMARY.md, latency_smoke_check.py, model-30-serving.md
- Layer: API
- Layer: Service
- Area: ModelServing
- Tests: Integration
- Component: Model30TechnicalTaskRouter
- Component: ModelServingService
- Component: ModelAPIService
```

**How these labels help the autonomous workflow:**
- **Risk: Medium** — Bounded change scope, but touches a live serving hot path; cap concurrency.
- **Files: ...** — Prevents file conflicts with HOK-1874/HOK-1875 follow-ups or other Model 30 work.
- **Layer: API + Service** — Can run in parallel with Database / Infra / UI tasks elsewhere in the repo.
- **Area: ModelServing** — Blocks concurrent tasks against the Model 30 path.
- **Tests: Integration** — Slower test runtime; do not overlap with other integration-heavy Model 30 work.
- **Component labels** — Mirror the Linear issue's component tags for routing.