## Weight Commitment Algorithm (HOK-2129)

**Algorithm ID**: `sha256-merkle-v1`

Leaf construction:
- Each leaf = SHA-256 over raw on-disk bytes of an included file (streamed in 1 MiB chunks)
- Canonical identity: `(POSIX relative path, sha256 hex digest, size bytes)`

File ordering: POSIX-relative paths sorted lexicographically (byte order, locale-independent)

Merkle construction:
- Fold pairwise: `sha256(left_digest_bytes || right_digest_bytes)`
- Odd-node handling: last node duplicated before pairing
- Single file: root = single leaf digest
- Empty (no included files): `ValueError`

Excluded paths (MLflow volatile metadata):
- `MLmodel` — contains `utc_time_created`, `model_uuid` (change each save)
- `metadata/` subtree — MLflow registry timestamps
- `registered_model_meta` anywhere in path

Router serializer spike result (HOK-2129): router `cloudpickle` round-trips are covered by unit tests and currently expected to remain byte-stable for both unloaded and fixture-loaded `TechnicalTaskRouterModel` instances.
