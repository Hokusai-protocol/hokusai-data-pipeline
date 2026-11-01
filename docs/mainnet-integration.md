# Mainnet Integration (Data Pipeline)

**Network:** Ethereum mainnet (chainId **1**) · **Deployed:** 2026-10-29 (relaunch; replaces the paused 2026-07-01 deployment) · **Governance handoff:** 2026-10-29T16:14Z

**Source of truth:** [`deployments/mainnet.addresses.json`](../deployments/mainnet.addresses.json) — vendored copy of the canonical export from the `hokusai-token` repo (`deployments/mainnet.addresses.json` + `docs/mainnet-frontend-integration.md`). Keep the vendored copy in sync on redeploy.

> ⚠️ Sepolia is still supported for dev/test. This doc covers the mainnet configuration only; it does not remove the Sepolia path.

## What the pipeline reads

This repo does **not** hardcode contract addresses. The mint / attestation flow reads everything from environment variables, which are injected at deploy time from AWS SSM parameters (see `.github/workflows/deploy.yml`). To run against mainnet, these must resolve to the mainnet values below:

| Env var | Mainnet value | Source in `mainnet.addresses.json` |
|---|---|---|
| `MINT_CHAIN_ID` | `1` | `chainId` |
| `MINT_VERIFYING_CONTRACT` | `0x645bfdFD78BEA0eC8D3e783E4993c70035761853` | `contracts.DeltaVerifier` |
| `DELTA_VERIFIER_ADDRESS` | `0x645bfdFD78BEA0eC8D3e783E4993c70035761853` | `contracts.DeltaVerifier` |
| `MODEL_REGISTRY_ADDRESS` | `0x2B8aA4BC2d2697320EAEA52D0CB5e10d64b4092B` | `contracts.ModelRegistry` |
| `ETH_RPC_URL` | *(mainnet RPC endpoint)* | infra SSM (not in this repo) |
| `MINT_SUBMITTER_ADDRESS` | *(mainnet submitter — KMS)* | infra SSM `/hokusai/production/ethereum/mainnet/submitter_address` |
| `MINT_ATTESTER_ADDRESS` | *(mainnet attester)* | infra SSM |
| `PENDING_CLAIMS_ESCROW_ADDRESS` | *(mainnet PendingClaimsEscrow)* | `settlement.PendingClaimsEscrow` (`0xC05F6244a1C94129F54dbcFe1261c8CAB3E05623`); infra SSM `/hokusai/production/contracts/pending_claims_escrow_address` |

> `MINT_CHAIN_ID` was previously never injected by `deploy.yml`. The mainnet deploy path now sets it explicitly (mainnet = `1`). The code has no default and hard-fails if it is unset (`src/eip712/mint_authorization.py`).

## Model tokens

| Model | modelId | Token (18d) | AMM Pool | CRR |
|---|---|---|---|---|
| HMESS — Hokusai Messaging | 28 | `0x2f3216DC669A7981bC0873214ba62Cf3527ebD66` | `0x0da186a5608Fc08B3bC1200953F495baC0F5AC84` | 20% |
| HLEAD — Sales Lead Scoring | 27 | `0x81c7C304FAAbB29436DACdc9efca6629dEBEE3A4` | `0x287f2E95ea02e22A719273Ad298e9cCB7F907ceC` | 20% |
| HROUT — Task Routing | 30 | `0xfC35fDb18bb015D4DC05B5f60d77753A4B6d3799` | `0x026DdABc0dF1010c871BAf19d9F2ED8DF148b400` | 20% |

Reserve token is **USDC** (`0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`, **6** decimals). Model tokens are **18** decimals — handle the mismatch explicitly in any pricing/display.

## Indexer / backfill

Backfill from `deploymentBlocks` in [`mainnet.addresses.json`](../deployments/mainnet.addresses.json) — earliest is `ModelRegistry` at block **26298878**. Pools were created ~2026-10-29T15:49Z. AMM pools are now upgradeable proxies (TransparentUpgradeableProxy); index events from the pool (proxy) address.

Model tokens use a **bonding-curve AMM**: investor supply is minted on purchase, not pre-minted. `totalSupply` at launch equals only the minted supplier allocation and grows as buyers mint against the curve — do **not** treat `maxSupply` as circulating supply.

## Governance (read before wiring any privileged call)

Ownership was handed off at launch — the deployer is fully revoked. Any privileged/admin action routes through governance, not a backend key:

- **48h Timelock** `0xcd8076D7a15E97946fAD0baA32Bf358be3D927C8` (min delay 172800s; owns the model tokens since the relaunch).
- **Admin Safe** `0x158B985CC667b4E022AD05B99E89007790da66E2` (params GOV_ROLE, DeltaVerifier + DataContributionRegistry admin; also emergency Safe).

Read paths (balances, quotes, registry lookups, events) need none of this. Only mint/param/role changes do, and those go through the Safe/timelock.
