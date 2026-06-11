# Attester Signing Runbook

Use this flow for every publish that requires DeltaVerifier attester signatures.

1. Run `hokusai attest build <run_id>`.
2. Read the full typed-data render on screen. The digest is printed at the end and must match the JSON file being signed.
3. Sign the generated typed-data JSON on the hardware wallet or Safe.
4. Run `hokusai attest attach <run_id> <signature...>`.
5. Confirm the command prints `ready to publish` with the recovered signer addresses and threshold.

What the signer is approving:

- `modelId`: on-chain numeric model identifier.
- `pipelineRunId`: evaluation run identifier being published.
- `baselineScoreBps` and `candidateScoreBps`: the accepted before/after metric values.
- `baselineCommitment`: current on-chain lineage head. Refuse if it does not match the rehearsal artifact or if it changed unexpectedly.
- `candidateCommitment`: candidate weight commitment for this publish.
- `datasetHash`, `attestationHash`, `idempotencyKey`: anchors tying the publish to the evaluated artifact set.
- `contributors`: recipient wallets and weights.

Refuse to sign when:

- The rendered `modelId`, run id, or contributor set is not the expected publish.
- `baselineCommitment` differs from the reviewed rehearsal artifact.
- The hardware-wallet view or digest differs from the JSON file produced by `attest build`.
- You are asked to attach extra signatures "for safety". Removed attesters or threshold changes can poison the whole submission.

Gate 9 rehearsal:

1. Run `attest build` on a staging candidate.
2. Compare the render to the operator packet.
3. Sign with the staging device.
4. Run `attest attach`.
5. Re-run `attest build` before publish if the baseline moved at any point.
