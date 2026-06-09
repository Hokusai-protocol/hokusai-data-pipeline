# Mint Rail

## Real mint rail

The production mint rail for accepted DeltaOne evaluations is:

1. `EvaluationService` or scheduler-triggered evaluation
2. `DeltaOneMintOrchestrator._execute_mint()`
3. `MintRequestPublisher.publish()`
4. Redis queue `hokusai:mint_requests`
5. Downstream `contract-deployer`
6. Downstream `DeltaVerifier`

The payload contract for this handoff is defined in `schema/mint_request.v1.json`.

`src/api/services/token_mint_hook.py` is not part of the real mint rail. The legacy `TokenMintHook` is audit/dry-run only and does not mint on-chain. It runs after Redis publication succeeds and exists only for audit logging, compatibility, and optional secondary notifications.

## Legacy hook

The legacy hook is intentionally secondary:

1. The canonical mint authorization happens when the Redis `MintRequest` is durably published.
2. Canonical score advancement happens only after that publish succeeds.
3. The legacy hook runs after publish and does not control the real mint rail.

Operators should treat any `token_mint_hook` status as audit metadata, not as proof of settlement.

## Monitoring

Monitor the following before enabling unattended scheduling:

- `hokusai:mint_requests` queue depth
- `hokusai:mint_requests:dlq` depth
- Alert if mint queue depth remains non-zero for more than 15 minutes after score advancement

Closed-loop settlement confirmation is not yet available in this repo. Until a settlement callback exists, a sustained non-zero queue is the proxy alert for "score advanced without on-chain settlement."

TODO: add a downstream settlement callback such as `POST /api/v1/settlements/{id}` for direct settlement confirmation.

## Pause / Kill-Switch Runbook

1. Set `MINT_PAUSED=true` and redeploy. The orchestrator returns `status="paused"` before publish.
2. Let downstream consumers drain `hokusai:mint_requests` until queue depth is `0`.
3. Set `ENABLE_EVALUATION_SCHEDULER=false` and redeploy.
4. Disable or restrict the AWS KMS signing key used for mainnet signer custody.
5. Verify CloudWatch alarms and Grafana panels show queue depth returning to `0`.

## Signer custody

Mainnet or staging signer custody must use KMS/HSM-backed signing, not environment-variable custody. `SIGNER_CUSTODY_MODE=env` is for development-only use.

## Scheduler enablement gate

Do not enable `ENABLE_EVALUATION_SCHEDULER=true` until all five gates are green:

1. Gate 1: existing scheduler functional gate
2. Gate 2: existing end-to-end mint/publish gate
3. Gate 3: existing reliability/ops gate
4. Gate 4: existing production readiness gate
5. Gate 5: [HOK-2058](https://linear.app/hokusai/issue/HOK-2058/gate-5-attribution-and-economics-soundness-tests) economics guardrails and kill-switch validation

Gate 5 is mainnet-money safety, not just test coverage.

Before setting `ENABLE_EVALUATION_SCHEDULER=true` in any environment, confirm:

- Budget guardrails are configured
- `MINT_PAUSED=false`
- signer custody is `kms` for staging/production
- queue depth and DLQ monitoring are deployed
- Gates 1 through 5 are green

No committed environment file should set `ENABLE_EVALUATION_SCHEDULER=true` by default.
