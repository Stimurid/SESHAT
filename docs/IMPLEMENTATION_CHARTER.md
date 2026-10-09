# SESHAT Implementation Charter v0.1

## Mission

SESHAT is a shared analytic runtime. Its job is to provide reusable execution mechanics for evidence-addressable analytic work while leaving domain methods and semantic authority with each host.

The first full profile is Sechenovka authorabstract analysis. The architecture must remain usable by at least one independent second host before any existing local analytic plumbing is deprecated.

## Non-goals

SESHAT is not:
- a universal prompt;
- a single mandatory pipeline;
- a replacement for Socrates, LitOps, Tinkuy, Quinta, D20, Indago, PRAGMA or Paideia;
- a claim that every analytic object can be reduced to one prior cut;
- a storage home for donor systems;
- a factory that invents missing method bodies.

## Core contracts to freeze before implementation

### ResearchObject
A versioned analytic subject with one or more source carriers and stable identity.

### SourceCarrier / SourceAddress
A carrier and an addressable location inside it. Addresses are evidence pointers, not semantic truth.

### Observation / CutSpec
A bounded observation over source material. A cut may guide later work but is non-sovereign unless a method explicitly makes it authoritative.

### AnalyticObjectSpec
Declares what kind of thing an operation reconstructs or evaluates.

### EvidenceAccessProfile
Declares the evidence topology needed by an operation.

Initial profile classes:
- EAP-META
- EAP-FULL-RECON
- EAP-FULL+STATE
- EAP-LOCAL+CHECK
- EAP-CORPUS
- EAP-EXTERNAL-JOIN
- EAP-DECISION

### RawAccessPolicy
At minimum:
- NEVER
- DRILLBACK
- FULL_REQUIRED

### OperationSpec
Must declare:
- target analytic object;
- methodological frame/body;
- evidence access profile;
- raw access policy;
- dependencies;
- output schema;
- applicability conditions;
- acceptance/decision right.

### DerivedObject
A versioned result with provenance, lineage, status, applicability and uncertainty.

### Dependency / Invalidation
A typed graph describing what downstream state becomes stale when upstream evidence or projections change.

### APORIA
A first-class unresolved contradiction, insufficiency or method failure that can trigger reread, reconciliation or research.

### Acceptance / DecisionRight
Separates machine production of evidence/proposals from semantic or consequential acceptance.

### ResearchNeed / EvidenceReturn
A typed handoff from analytic runtime to research machinery such as Indago and the return of sourced evidence.

### ProjectionSpec
A versioned view over accepted/working state. A projection is rebuildable and does not silently become semantic canon.

## Architectural law

The runtime does not assume a universal linear sequence.

A valid host may use:
- full-package reconstruction;
- focused extraction with drillback;
- mutually constraining operations;
- a DAG;
- iterative reconciliation;
- corpus projections over versioned per-object state;
- external evidence joins;
- decision projections with explicit rights.

## Object ↔ Method

For Sechenovka and similar tasks, Object and Method are co-constraining hypotheses.

A target runtime must permit:

```
Object_v1 <-> Method_v1
      |
   mismatch / aporia
      |
Object_v2 and/or Method_v2
```

Lineage and evidence must survive every revision.

## Donor rule

Every imported capability receives one disposition:
- REUSE
- WRAP
- EXTRACT
- COMPLETE
- DEPRECATE

Documentation similarity is not enough for REUSE. An implementation witness is required.

## Initial implementation slice

Do not implement 39 analytic agents.

First slice:
1. Object
2. Method
3. Infrastructure
4. Novelty
5. Limitations

Then:
- one corpus projection: Object clusters;
- one external/decision projection after the core is stable.

## Acceptance before migration

SESHAT cannot replace host-local plumbing until:
1. the core is executable;
2. provenance and invalidation are tested;
3. the first profile works reproducibly;
4. at least two independent hosts consume the shared runtime;
5. migration is adapter-based, not copy/paste.
