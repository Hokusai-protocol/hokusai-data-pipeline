# Weight Commitment Genesis

The first lineage commitment for a model must be computed with the same `sha256-merkle-v1` algorithm used by the production mint path.

Included files:

- all non-symlink files under the artifact directory

Excluded files:

- `MLmodel`
- anything under `metadata/`
- any path containing `registered_model_meta`

To compute the genesis value for Model 30:

```bash
python scripts/model_30/compute_weight_genesis.py \
  models:/Technical\ Task\ Router/7 \
  --model-id-uint 30
```

The script prints:

- the resolved artifact directory
- the algorithm id
- included and excluded file counts
- the `0x`-prefixed commitment
- the owner-only handoff call: `ModelRegistry.setWeightGenesis(modelId, commitment)`

`setWeightGenesis` is write-once and owner-only. The steady-state baseline commitment used for minting is not recomputed locally; it is read from `DeltaVerifier.modelWeightHead(modelId)` and falls back to `ModelRegistry.weightGenesis(modelId)` only when the on-chain head is still zero.
