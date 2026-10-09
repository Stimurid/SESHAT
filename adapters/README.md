# Adapters

Adapters connect independently governed hosts to SESHAT.

Planned host adapters:
- Socrates
- LitOps
- Tinkuy
- Quinta / AgentRun
- D20
- Indago
- PRAGMA / Paideia

An adapter may translate:
- source identity and addressing;
- host state into SESHAT ResearchObject / DerivedObject contracts;
- host run/profile semantics into OperationSpec;
- evidence/provenance formats;
- research requests and returns;
- acceptance/decision signals;
- invalidation notifications.

Adapters must not move semantic authority from the host into SESHAT accidentally.
