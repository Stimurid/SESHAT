# Fabric waves — portable carpet receipt (issue #60)

Portable `receipt.json` from `carpet_portfolio` export includes:

- `portfolio_digest_sha256` — legacy combined digest of `activations.jsonl` and `waves.jsonl` (unchanged).
- `artifact_file_digests` — per-file SHA256 and byte length for the seven exported artifacts (excluding `receipt.json`).
- `source_modules` — `SOURCE_MODULE_BYTES_VERIFIED` manifest of loaded `fabric_waves` Python module file bytes.
- `git` — optional `GIT_ATTESTED` head/tree when `git` is available; otherwise explicit `GIT_NOT_ATTESTED` with null SHAs.

Strict external oracles that require non-null Git strings in the portable receipt alone remain a separate coordinator gate: bind trusted HEAD/TREE to the same `source_modules.manifest_sha256` via an external attestation sidecar rather than inferring Git from the runtime container.
