# Provider execution evidence

HOK-3495 extends the owning SDK v4 provider contract through canonical intake. `provider_executions` stays optional and closed: it carries pseudonymous session/launch/response identities, requested restrictions, scoped price snapshots, raw usage counters, observed host/model facts and nullable billed charges. Historical v4 rows retain their reference-pricing behavior.

The schema mirror in `src/model_30/provider-execution.v1.schema.json` comes from the SDK's identically named schema. Update both with the conformance fixtures. `tests/fixtures/contribution_v4/provider_execution_replay.json` is reconstructed by Wavemill's actual producer, redactor and SDK builder; its test compares the same bytes before canonical ingestion. It is not a live provider comparison.

Canonical rows preserve per-stage `execution_evidence`. Complete billed observations use their reported charges, including zero, before model reference pricing. Unbilled turns are repriced only through existing `usage_cost` primitives: endpoint snapshots use endpoint rates, while model snapshots remain reference evidence. Mixed sources retain a billed lower bound, billing coverage and cost basis. Missing observations or usage yield an incomplete total, never a fabricated zero. `charge_trust: contributor_reported` means the host claims to have observed these charges; intake has not independently verified an invoice. This change does not certify a provider or independently attest its prices.

Failure attribution is stored with the economics. A non-model fault leaves canonical model `success` unknown while retaining the execution outcome and cost. Model faults remain negative outcomes. The existing `routing_join` retains the inference decision and measured overrides; no new inference-link mechanism is added.

Rollout: merge/deploy this compatible consumer before enabling Wavemill's producer. Existing rows and stored corpora need no migration; endpoint qualification and provider choice remain HOK-3496/HOK-3497.
