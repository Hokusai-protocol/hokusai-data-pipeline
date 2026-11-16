# Shared task-cost rates (HOK-3421)

New canonical contribution rows use `configs/hokusai_token_prices.v1.json`,
the SDK-generated `hokusai_token_prices/v1` artifact. The SDK and server price
API-equivalent resource consumption independently of subscription, discounts or
subsidies. Contributor dollar totals remain evidence, not trusted rate inputs.

Each canonical row records `hokusai_token_prices/<version>+sha256:<full digest>`.
Catalog files supply model identity only. The old snapshot-derived
`model_30_token_prices.v1.json` and live catalog/OpenRouter price fallbacks are
removed from server repricing. A null cache rate stays unpriced when usage of
that dimension is nonzero; it never falls back to an invented multiplier.
SDK normalization, rounding, aliases and request-scoped context tiers are covered
by the vendored SDK computation vectors.

## Updating

1. Update and verify rates in the SDK's `packages/core/src/pricing.ts`.
2. Run `pnpm export:token-prices` and the SDK checks; commit the generated table
   and `fixtures/token-prices/parity.v1.json` together.
3. Run `python scripts/model_30/vendor_sdk_token_prices.py /path/to/hokusai-sdk`
   from this repo. It copies both artifacts and records SHA-256 hashes and the
   exact SDK commit in `tests/fixtures/token-prices/provenance.json`.
4. Run `HOKUSAI_SDK_DIR=/path/to/hokusai-sdk python -m pytest
   tests/unit/model_30 --no-cov`. The CI parity workflow also checks the exact
   source bytes from that SDK commit. A change requires an intentional re-vendor.

The SDK artifact records provider URL and verification date per model. On
2026-11-16 the provider pages confirmed Sonnet 5 $2/$10 input/output,
GPT-5.6 Terra $2/$12, and GPT-5.3 Codex cached input $0.175 per million tokens.
The SDK's pinned 2026-11-02 OpenRouter rows supply additional native models;
eval-record snapshots are not copied into this table.

## Release order and frozen history

Merge/publish the SDK first. **Merge the server rate switch only after HOK-3410's
v10 release**, as specified in HOK-3421. The issue is still Backlog as of this
implementation; preparing these PRs does not authorize changing production rates.

Frozen legacy canonical rows retain their stored cost and price provenance. No
backfill, retraining, production deployment or frozen-history repricing is part
of this change. Offline collectors may still use an explicit record snapshot to
reproduce historical records; new server ingestion passes only the SDK snapshot.
Historical cost artifacts needed to reproduce v10 remain part of that release's
frozen evidence, rather than the mutable live server rate file.
