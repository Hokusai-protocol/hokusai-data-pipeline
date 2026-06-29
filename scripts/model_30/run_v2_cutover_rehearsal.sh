#!/usr/bin/env bash
#
# HOK-2217 — Model 30 v2 reward composite cutover rehearsal (dry-run).
#
# Runs the rehearsal end-to-end against a NON-PRODUCTION environment:
#   1. rescore   : re-score the production baseline + latest candidate under v2 AND v1
#   2. baseline  : publish the canonical v2 baseline score + benchmark spec hash
#   3. accepted  : DeltaOne dry-run — improving candidate -> synthetic MintRequest artifact
#   4. rejected  : DeltaOne dry-run — non-improving (baseline vs baseline) -> NO mint
#
# Safety contract:
#   * This script NEVER publishes a MintRequest and NEVER mints on-chain. It only
#     builds, scores, verifies, and writes artifacts to disk.
#   * The synthetic reward legs are hard-blocked on prod/mainnet by the underlying
#     tool; this wrapper additionally refuses ENVIRONMENT in {prod,production,mainnet}.
#   * Use `--check` to validate configuration and compute the spec hash with NO
#     network access before running the live phases.
#
# Run this from a host with access to the target MLflow (bastion / ECS exec / CI),
# not necessarily a laptop.
#
set -euo pipefail

# --------------------------------------------------------------------------- #
# Configuration (override via environment or flags)
# --------------------------------------------------------------------------- #
ENVIRONMENT="${ENVIRONMENT:-canary}"                  # canary | testnet | staging | development
MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI:-}"
BASELINE_URI="${BASELINE_URI:-models:/Technical Task Router@production}"
CANDIDATE_URI="${CANDIDATE_URI:-models:/Technical Task Router@candidate}"
HOLDOUT="${HOLDOUT:-}"                                # path to cleaned holdout CSV
MANIFEST="${MANIFEST:-}"                              # path to Model 30 training manifest JSON
ESCROW_WALLET="${ESCROW_WALLET:-${PENDING_CLAIMS_ESCROW_ADDRESS:-}}"
MODEL_ID_UINT="${MODEL_ID_UINT:-30}"
OUT_DIR="${OUT_DIR:-artifacts/hok-2217-rehearsal}"

# The accepted-leg synthetic builder needs the baseline/candidate MLflow run IDs.
# Provide them explicitly, or point at a real attribution report that carries them.
BASELINE_RUN_ID="${BASELINE_RUN_ID:-}"
CANDIDATE_RUN_ID="${CANDIDATE_RUN_ID:-}"
SOURCE_ATTRIBUTION="${SOURCE_ATTRIBUTION:-}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SPEC_FILE="${REPO_ROOT}/schema/examples/technical_task_router_spec.v2.json"
CANONICAL_SPEC_ID="technical_task_router.benchmark_score/v2"
CANONICAL_METRIC_NAME="technical_task_router.benchmark_score/v2"
CANONICAL_METRIC_FAMILY="continuous"
PRIMARY_METRIC_KEY="technical_task_router.benchmark_score_v2"

FORBIDDEN_ENVS="prod production mainnet"

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
log()  { printf '\033[1;36m[rehearsal]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[ ok ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[fail]\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'USAGE'
Usage: run_v2_cutover_rehearsal.sh [--all|--check|--rescore|--baseline|--accepted|--rejected]

Phases (default: --all, which runs rescore -> baseline -> accepted -> rejected):
  --check     Validate config + compute the v2 spec hash. NO network, NO writes outside OUT_DIR.
  --rescore   Re-score baseline + candidate under v2 (canonical) and v1 (guardrail).
  --baseline  Publish canonical v2 baseline score + spec hash (writes JSON; tags MLflow if reachable).
  --accepted  DeltaOne dry-run: improving candidate -> build + verify synthetic MintRequest.
  --rejected  DeltaOne dry-run: baseline-vs-baseline -> assert NO mint (rejection).
  --all       All of the above (no publish, ever).

Configure via env vars (see top of script): ENVIRONMENT, MLFLOW_TRACKING_URI, BASELINE_URI,
CANDIDATE_URI, HOLDOUT, MANIFEST, ESCROW_WALLET, MODEL_ID_UINT, OUT_DIR.
USAGE
}

# python is always available in this repo's env; jq may not be.
json_get() { # json_get <file> <python-expression-on-`d`>
  python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(eval(sys.argv[2]))" "$1" "$2"
}

assert_non_prod() {
  local env_lc
  env_lc="$(printf '%s' "$ENVIRONMENT" | tr '[:upper:]' '[:lower:]')"
  for bad in $FORBIDDEN_ENVS; do
    if [ "$env_lc" = "$bad" ]; then
      die "ENVIRONMENT='$ENVIRONMENT' is forbidden. The rehearsal runs on canary/testnet/staging/development only."
    fi
  done
  return 0
}

require() { [ -n "${2:-}" ] || die "missing required config: $1"; }
require_file() { [ -f "$1" ] || die "file not found ($2): $1"; }

# --------------------------------------------------------------------------- #
# Phase: check
# --------------------------------------------------------------------------- #
phase_check() {
  log "Validating configuration (no network)"
  assert_non_prod
  require "HOLDOUT" "$HOLDOUT"
  require "MANIFEST" "$MANIFEST"
  require_file "$SPEC_FILE" "canonical v2 spec"
  require_file "$HOLDOUT" "holdout dataset"
  require_file "$MANIFEST" "training manifest"
  [ -n "$ESCROW_WALLET" ] || warn "ESCROW_WALLET unset — required for the accepted-leg synthetic builder."
  [ -n "$MLFLOW_TRACKING_URI" ] || warn "MLFLOW_TRACKING_URI unset — required for rescore/baseline phases."

  local spec_hash
  spec_hash="$(shasum -a 256 "$SPEC_FILE" | awk '{print $1}')"
  mkdir -p "$OUT_DIR"
  printf 'environment=%s\nbenchmark_spec_id=%s\nspec_sha256=%s\nbaseline_uri=%s\ncandidate_uri=%s\n' \
    "$ENVIRONMENT" "$CANONICAL_SPEC_ID" "$spec_hash" "$BASELINE_URI" "$CANDIDATE_URI" \
    | tee "$OUT_DIR/rehearsal_config.txt"
  ok "Config valid. v2 spec sha256 = $spec_hash"
}

# --------------------------------------------------------------------------- #
# Phase: rescore  (baseline + candidate under v2 and v1)
# --------------------------------------------------------------------------- #
phase_rescore() {
  log "Re-scoring baseline vs candidate under v2 (canonical) and v1 (guardrail)"
  require "MLFLOW_TRACKING_URI" "$MLFLOW_TRACKING_URI"
  mkdir -p "$OUT_DIR"

  python3 "${REPO_ROOT}/scripts/model_30/evaluate_technical_task_router.py" \
    --holdout-dataset "$HOLDOUT" \
    --baseline-model-uri "$BASELINE_URI" --baseline-model-id model-30-baseline \
    --candidate-model-uri "$CANDIDATE_URI" --candidate-model-id model-30-candidate \
    --benchmark-version v2 \
    --training-manifest "$MANIFEST" \
    --output-report "$OUT_DIR/compare_v2.json" \
    --log-mlflow --run-name "model-30-v2-cutover-rescore-${ENVIRONMENT}"
  ok "v2 comparison -> $OUT_DIR/compare_v2.json"

  python3 "${REPO_ROOT}/scripts/model_30/evaluate_technical_task_router.py" \
    --holdout-dataset "$HOLDOUT" \
    --baseline-model-uri "$BASELINE_URI" --candidate-model-uri "$CANDIDATE_URI" \
    --benchmark-version v1 \
    --output-report "$OUT_DIR/compare_v1.json"
  ok "v1 guardrail comparison -> $OUT_DIR/compare_v1.json"

  local pm
  pm="$(json_get "$OUT_DIR/compare_v2.json" "d['comparison']['primary_metric']")"
  [ "$pm" = "$PRIMARY_METRIC_KEY" ] || die "v2 comparison primary_metric is '$pm', expected '$PRIMARY_METRIC_KEY'"
  ok "Canonical primary metric confirmed: $pm"
}

# --------------------------------------------------------------------------- #
# Phase: baseline  (publish canonical v2 baseline score + spec hash)
# --------------------------------------------------------------------------- #
phase_baseline() {
  log "Publishing canonical v2 baseline score + spec hash"
  require_file "$OUT_DIR/compare_v2.json" "v2 comparison (run --rescore first)"
  local spec_hash baseline_score candidate_score primary_delta holdout_hash
  spec_hash="$(shasum -a 256 "$SPEC_FILE" | awk '{print $1}')"
  baseline_score="$(json_get "$OUT_DIR/compare_v2.json" "d['comparison']['baseline_metrics']['$PRIMARY_METRIC_KEY']")"
  candidate_score="$(json_get "$OUT_DIR/compare_v2.json" "d['comparison']['candidate_metrics']['$PRIMARY_METRIC_KEY']")"
  primary_delta="$(json_get "$OUT_DIR/compare_v2.json" "d['comparison']['primary_delta']")"
  holdout_hash="$(json_get "$OUT_DIR/compare_v2.json" "d['baseline']['holdout_dataset_sha256']")"

  python3 - "$OUT_DIR/published_v2_baseline.json" <<PY
import json, sys
out = sys.argv[1]
json.dump({
    "benchmark_spec_id": "$CANONICAL_SPEC_ID",
    "spec_sha256": "$spec_hash",
    "metric_name": "$CANONICAL_METRIC_NAME",
    "metric_family": "$CANONICAL_METRIC_FAMILY",
    "baseline_score_v2": $baseline_score,
    "candidate_score_v2": $candidate_score,
    "primary_delta_v2": $primary_delta,
    "holdout_dataset_sha256": "$holdout_hash",
    "environment": "$ENVIRONMENT",
}, open(out, "w"), indent=2, sort_keys=True)
open(out, "a").write("\n")
PY
  ok "Wrote $OUT_DIR/published_v2_baseline.json (baseline v2 score=$baseline_score, spec sha256=$spec_hash)"

  if [ -n "$MLFLOW_TRACKING_URI" ]; then
    log "Tagging MLflow run with the published baseline + spec hash"
    MLFLOW_TRACKING_URI="$MLFLOW_TRACKING_URI" python3 - <<PY || warn "MLflow tagging skipped (tracking server unreachable)"
import mlflow
mlflow.set_experiment("technical-task-router-evaluation")
with mlflow.start_run(run_name="model-30-v2-baseline-publish-${ENVIRONMENT}"):
    mlflow.set_tag("hokusai.model_30.benchmark_spec_id", "$CANONICAL_SPEC_ID")
    mlflow.set_tag("hokusai.model_30.v2_spec_sha256", "$spec_hash")
    mlflow.set_tag("hokusai.model_30.v2_baseline_score", "$baseline_score")
    mlflow.set_tag("hokusai.metric_family", "$CANONICAL_METRIC_FAMILY")
    mlflow.log_artifact("$OUT_DIR/published_v2_baseline.json")
    mlflow.log_artifact("$SPEC_FILE")
PY
    ok "MLflow baseline-publish run recorded"
  fi
  # Show the v2 BenchmarkSpec activation plan (HOK-2217 acceptance criterion 1) as a
  # dry-run. Activation is a governance DB write, so it stays a deliberate separate
  # command — this never applies it.
  if [ -n "${DATABASE_URL:-}" ]; then
    log "Previewing v2 benchmark spec activation (dry-run)"
    python3 "${REPO_ROOT}/scripts/model_30/activate_v2_benchmark_spec.py" \
      --model-id "$MODEL_ID_UINT" || warn "activation preview skipped (spec absent or DB unreachable)"
    warn "To apply, run: scripts/model_30/activate_v2_benchmark_spec.py --model-id $MODEL_ID_UINT --apply"
  else
    warn "Set DATABASE_URL to preview v2 BenchmarkSpec activation, then apply with:"
    warn "  scripts/model_30/activate_v2_benchmark_spec.py --model-id $MODEL_ID_UINT --apply"
  fi
}

# --------------------------------------------------------------------------- #
# DeltaOne gate decision (reads a comparison report; decides accept/reject)
# --------------------------------------------------------------------------- #
gate_decision() { # gate_decision <compare.json> -> prints "accept" or "reject"
  python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print('accept' if float(d['comparison']['primary_delta'])>0 else 'reject')" "$1"
}

# --------------------------------------------------------------------------- #
# Phase: accepted  (improving candidate -> synthetic MintRequest)
# --------------------------------------------------------------------------- #
phase_accepted() {
  log "DeltaOne dry-run (ACCEPTED leg)"
  assert_non_prod
  require "ESCROW_WALLET" "$ESCROW_WALLET"
  require_file "$OUT_DIR/compare_v2.json" "v2 comparison (run --rescore first)"
  require_file "$MANIFEST" "training manifest"

  local decision
  decision="$(gate_decision "$OUT_DIR/compare_v2.json")"
  if [ "$decision" != "accept" ]; then
    warn "v2 primary_delta <= 0: the real candidate did not improve the baseline."
    warn "The synthetic builder fabricates a small positive delta for pipeline testing; proceeding to build the ACCEPTED artifact."
  fi

  # Resolve baseline/candidate run IDs for attribution (explicit IDs or a source report).
  local run_args=()
  if [ -n "$SOURCE_ATTRIBUTION" ]; then
    require_file "$SOURCE_ATTRIBUTION" "source attribution report"
    run_args+=(--source-attribution "$SOURCE_ATTRIBUTION")
  fi
  [ -n "$BASELINE_RUN_ID" ]  && run_args+=(--baseline-run-id "$BASELINE_RUN_ID")
  [ -n "$CANDIDATE_RUN_ID" ] && run_args+=(--candidate-run-id "$CANDIDATE_RUN_ID")
  if [ -z "$SOURCE_ATTRIBUTION" ] && { [ -z "$BASELINE_RUN_ID" ] || [ -z "$CANDIDATE_RUN_ID" ]; }; then
    die "accepted leg needs baseline/candidate run IDs: set BASELINE_RUN_ID and CANDIDATE_RUN_ID, or SOURCE_ATTRIBUTION."
  fi

  ALLOW_SYNTHETIC_REWARD_E2E=true python3 "${REPO_ROOT}/scripts/model_30/build_synthetic_reward_e2e.py" \
    --manifest "$MANIFEST" \
    --comparison-report "$OUT_DIR/compare_v2.json" \
    --environment "$ENVIRONMENT" \
    --model-id-uint "$MODEL_ID_UINT" \
    --escrow-wallet "$ESCROW_WALLET" \
    "${run_args[@]}" \
    --output-dir "$OUT_DIR/accepted"
  # NOTE: intentionally no --publish. Artifacts are written for review only.

  local mint="$OUT_DIR/accepted/synthetic_mint_request.json"
  require_file "$mint" "synthetic MintRequest"
  local got_spec got_name got_family
  got_spec="$(json_get "$mint" "d['benchmark_spec_id']")"
  got_name="$(json_get "$mint" "d['evaluation']['metric_name']")"
  got_family="$(json_get "$mint" "d['evaluation']['metric_family']")"
  [ "$got_spec" = "$CANONICAL_SPEC_ID" ]       || die "MintRequest benchmark_spec_id='$got_spec' != '$CANONICAL_SPEC_ID'"
  [ "$got_name" = "$CANONICAL_METRIC_NAME" ]   || die "MintRequest metric_name='$got_name' != '$CANONICAL_METRIC_NAME'"
  [ "$got_family" = "$CANONICAL_METRIC_FAMILY" ] || die "MintRequest metric_family='$got_family' != '$CANONICAL_METRIC_FAMILY'"
  ok "ACCEPTED MintRequest is v2-conformant: spec=$got_spec name=$got_name family=$got_family"
  ok "Artifacts: $OUT_DIR/accepted/ (NOT published)"
}

# --------------------------------------------------------------------------- #
# Phase: rejected  (non-improving -> no mint)
# --------------------------------------------------------------------------- #
phase_rejected() {
  log "DeltaOne dry-run (REJECTED leg) — scoring baseline against itself for a deterministic non-improvement"
  require "MLFLOW_TRACKING_URI" "$MLFLOW_TRACKING_URI"
  mkdir -p "$OUT_DIR"

  python3 "${REPO_ROOT}/scripts/model_30/evaluate_technical_task_router.py" \
    --holdout-dataset "$HOLDOUT" \
    --baseline-model-uri "$BASELINE_URI" --candidate-model-uri "$BASELINE_URI" \
    --benchmark-version v2 \
    --training-manifest "$MANIFEST" \
    --output-report "$OUT_DIR/compare_v2_reject.json"

  local decision delta
  decision="$(gate_decision "$OUT_DIR/compare_v2_reject.json")"
  delta="$(json_get "$OUT_DIR/compare_v2_reject.json" "d['comparison']['primary_delta']")"
  [ "$decision" = "reject" ] || die "expected rejection (delta<=0) but gate said '$decision' (delta=$delta)"
  ok "REJECTED: v2 primary_delta=$delta -> DeltaOne declines, no MintRequest built (correct)."
}

# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #
main() {
  local mode="${1:---all}"
  case "$mode" in
    -h|--help) usage; exit 0 ;;
    --check)    phase_check ;;
    --rescore)  phase_check; phase_rescore ;;
    --baseline) phase_baseline ;;
    --accepted) phase_check; phase_accepted ;;
    --rejected) phase_check; phase_rejected ;;
    --all)
      phase_check
      phase_rescore
      phase_baseline
      phase_accepted
      phase_rejected
      ok "Rehearsal complete (dry-run). Review artifacts under $OUT_DIR/"
      ;;
    *) usage; die "unknown option: $mode" ;;
  esac
}

main "${1:-}"
