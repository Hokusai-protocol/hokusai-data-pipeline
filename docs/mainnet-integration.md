# Mainnet Integration (Data Pipeline)

**Network:** Ethereum mainnet (chainId **1**) · **Deployed:** 2026-07-01 · **Governance handoff:** 2026-07-01T22:04Z

**Source of truth:** [`deployments/mainnet.addresses.json`](../deployments/mainnet.addresses.json) — vendored copy of the canonical export from the `hokusai-token` repo (`deployments/mainnet.addresses.json` + `docs/mainnet-frontend-integration.md`). Keep the vendored copy in sync on redeploy.

> ⚠️ Sepolia is still supported for dev/test. This doc covers the mainnet configuration only; it does not remove the Sepolia path.

## What the pipeline reads

This repo does **not** hardcode contract addresses. The mint / attestation flow reads everything from environment variables, which are injected at deploy time from AWS SSM parameters (see `.github/workflows/deploy.yml`). To run against mainnet, these must resolve to the mainnet values below:

| Env var | Mainnet value | Source in `mainnet.addresses.json` |
|---|---|---|
| `MINT_CHAIN_ID` | `1` | `chainId` |
| `MINT_VERIFYING_CONTRACT` | `0xE9D40B96703391464bc6b0ea0b4F0404399AaCE7` | `contracts.DeltaVerifier` |
| `DELTA_VERIFIER_ADDRESS` | `0xE9D40B96703391464bc6b0ea0b4F0404399AaCE7` | `contracts.DeltaVerifier` |
| `MODEL_REGISTRY_ADDRESS` | `0x0a09B52fE6b55dE42676b3F68BED76793FB9FEe9` | `contracts.ModelRegistry` |
| `ETH_RPC_URL` | *(mainnet RPC endpoint)* | infra SSM (not in this repo) |
| `MINT_SUBMITTER_ADDRESS` | *(mainnet submitter — KMS)* | infra SSM `/hokusai/production/ethereum/mainnet/submitter_address` |
| `MINT_ATTESTER_ADDRESS` | *(mainnet attester)* | infra SSM |
| `PENDING_CLAIMS_ESCROW_ADDRESS` | *(mainnet PendingClaimsEscrow)* | infra SSM — **no mainnet value in the token export yet; confirm before enabling escrow fallback**|

> `MINT_CHAIN_ID` was previously never injected by `deploy.yml`. The mainnet deploy path now sets it explicitly (mainnet = `1`). The code has no default and hard-fails if it is unset (`src/eip712/mint_authorization.py`).

## Model tokens

| Model | modelId | Token (18d) | AMM Pool | CRR |
|---|---|---|---|---|
| HMESS — Hokusai Messaging | 28 | `0x559028b237ff7d4b019d90250D70c604f4894379` | `0xC187ffc6a465247f228a63f00C2515041792A0fA` | 30% |
| HLEAD — Sales Lead Scoring | 27 | `0x25618B023c0e65E4daDb21ee04dc010AaE84B1F5` | `0xa6D4a50496ce6808508e6DCaB19D57845D4e30e4` | 10% |
| HROUT — Task Routing | 30 | `0x8866f3262621daBCC973f6D3A4953E7ad9F56D39` | `0x6C40EF10da0c0Fc87352b0026A49a6769af12816` | 20% |

Reserve token is **USDC** (`0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`, **6** decimals). Model tokens are **18** decimals — handle the mismatch explicitly in any pricing/display.

## Indexer / backfill

Backfill from `deploymentBlocks` in [`mainnet.addresses.json`](../deployments/mainnet.addresses.json) — earliest is `ModelRegistry` at block **25440259**. Pools were created ~block **25440290+**.

Model tokens use a **bonding-curve AMM**: investor supply is minted on purchase, not pre-minted. `totalSupply` at launch equals only the minted supplier allocation and grows as buyers mint against the curve — do **not** treat `maxSupply` as circulating supply.

## Governance (read before wiring any privileged call)

Ownership was handed off at launch — the deployer is fully revoked. Any privileged/admin action routes through governance, not a backend key:

- **48h Timelock** `0xcd8076D7a15E97946fAD0baA32Bf358be3D927C8` (min delay 172800s).
- **Admin Safe** `0x158B985CC667b4E022AD05B99E89007790da66E2` (token owner, params GOV_ROLE, DeltaVerifier + DataContributionRegistry admin; also emergency Safe).

Read paths (balances, quotes, registry lookups, events) need none of this. Only mint/param/role changes do, and those go through the Safe/timelock.
