# SESHAT: operator-local no-server MethodBody slice v0.1

Status: **ENGINEERING_SMOKE_ONLY / NOT_SCIENCE_READY / NOT_CUSTOMER_READY**.

This is a standalone additive operator route. The original G1/F07/F08
report bridge and its real-source `FABRIC_METHOD_ATTESTATION_REQUIRED`
guard are intentionally unchanged. The owner discontinued the separate
privileged issuer server; no component here reinstalls it.

## What actually executes

- `operator_methodbody.py`: one Python callback invoked locally with
  complete supplied UTF-8 bytes, the exact submitted MethodBody bytes and
  method identity/version, with pre-checked source and method SHA-256.
- `operator_builtin_method.py`: **one bounded declarative operation**,
  `literal_span_find`, whose chosen needle is taken from the pinned JSON
  MethodBody bytes. It returns the exact byte offset and byte length of a
  match. No dynamic import or execution of untrusted method code.
- `operator_sqlite_ledger.py`: local private SQLite journal; the run_id is
  persisted PENDING *before* the call and set COMPLETE after receipt writing.
  On crash or unknown outcome, a later process refuses to re-invoke it
  automatically. Repeated identical COMPLETE requests return the stored
  receipt. Changed fingerprints fail closed.
- `operator_local_demo.py`: two dissimilar **invented** fixtures, runnable
  in separate processes, with fresh readback from SQLite. There is no
  external LLM, no private document and no charge.

## Evidence semantics

- `SELF_OBSERVED_UNATTESTED` is mandatory. SQLite checksums detect
  accidental drift and support local readback, **not** third-party authority.
  A filesystem principal who can rewrite both JSON and checksum can forge it.
- Source bytes are SHA pinned; rights basis and view are **operator declared**.
  Matching them proves only local consistency, not an F07 provider grant.
  `SourceAccessReceipt.detail` says so. FULL_REQUIRED in this module
  denotes that complete declared UTF-8 bytes were supplied and checked;
  PDF parsing, full document rights and actual page mapping are not proven.
- Any supplied `OperatorClaim.page` is refused without a verified page
  map. Byte-exact offsets into UTF-8 input may still be verified.
- The invoked callback receives the pinned method bytes; a generic
  caller-supplied callback may ignore them. This module **does not attest
  Python callable source code or the semantics of an authorial MethodBody**.
  The built-in declarative interpreter is the only bounded example which
  actually interprets pinned method instructions.
- `declared_model_identity` is untrusted operator declaration; this run
  does NOT establish real provider/model execution. Tokens/cost default
  UNKNOWN; unknown paid outcomes must not be retried automatically.
- Receipt is owner-private and proposal-only. Human decision
  `ACCEPTED` is never minted here. Customer export requires separately
  reviewed prose and evidence rights. There is no actual customer R01/R02
  or scientific assessment of a real corpus in this v0.1 slice.
- A required owner exclusion policy is an operator responsibility:
  active source selection must inject the current private exclusion set.
  Fixture IDs in the demo are invented and are not a corpus admission.
  The public module does not embed private source identifiers.

## Reproduce the bounded operator smoke

From repo worktree, use a Python 3.11+ environment with dependencies:

```
set PYTHONPATH=src
python -m pytest -q -p no:cacheprovider tests/fabric_waves/test_operator_methodbody.py tests/fabric_waves/test_operator_sqlite_ledger.py tests/fabric_waves/test_operator_builtin_method.py
python -m ruff check --no-cache .
python -m seshat.fabric_waves.operator_local_demo --fixture materials --out PRIVATE_DIR
python -m seshat.fabric_waves.operator_local_demo --fixture organization --out PRIVATE_DIR
python -m seshat.fabric_waves.operator_local_demo --fixture materials --out PRIVATE_DIR --verify-only
python -m seshat.fabric_waves.operator_local_demo --fixture organization --out PRIVATE_DIR --verify-only
```

The two demos produce different method/source/output digests and the
readback process verifies each receipt without repeating the call.

## Unclosed gates for genuinely authorial/model-driven science

1. Runtime admission from a real F07 source reader that checks
   original complete PDF bytes, caller rights and verified physical pages,
   including denial on partial/revoked/stale source.
2. A real authorial MethodBody interpreter/provider adapter which shows
   that exactly the pinned method was used; the callback and script currently
   remain independently supplied except for the built-in grammar.
3. Actual observed Hub/local model job, original output/cost-or-UNKNOWN
   and failure semantics (without relying on untrusted status self-claims).
4. No accidental duplicate paid call after crash/timeout. The PENDING
   reservation is local only and requires explicit operator reconciliation.
5. Independent exact-commit source audit and whole-product regression.
6. Domain-science review and customer reporting R01-R09 are separate gates.

No service, live ACL, active provider, protected source, original G1 bridge
or public repository release is changed by this slice.
