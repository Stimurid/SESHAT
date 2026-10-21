# S-F07-PDF-SANDBOX-001 — ephemeral PDF parser boundary

This path accepts only an already admitted `RuntimeSourceAccess` FULL read and
an externally configured, reviewed `repository@sha256:...` container image.
The host verifies declared and actual PDF media, F07 receipt, version, length
and SHA. It sends bounded bytes and excerpt via stdin; it never parses the
PDF. `pypdf==6.21.1` runs only in the one-shot Linux container. The child
F07 copy is transport plumbing, not independent rights evidence; the host
replaces its receipt hash with the original F07 FULL receipt hash and checks
all source/page/excerpt bindings it can independently check.

The Docker daemon and image are trusted execution components. `--user`
does not prove a rootless daemon. Deployment preflight must verify Docker
daemon ownership, Linux mode, image review and pinned digest, resource flag
support, and a bounded timeout/cleanup drill on the actual host. A rootless
or equivalently isolated daemon is preferred. No fallback invokes the
in-process parser on real or untrusted input. The legacy PR #68 helper
remains for deterministic synthetic QA only.

The container uses no network, mounts, extra capabilities or persistent
storage, and has read-only root, nonroot UID, `no-new-privileges`, 32 PIDs,
256 MiB memory and swap, one CPU quota, and 16 MiB temporary space. A
supervisor imposes a wall clock limit and force-removes its uniquely named
container on failure. If Docker or cleanup cannot be verified, treat the
operation as failed and inspect the host before accepting another job.

The receipt is `OWNER_PRIVATE`, with source and excerpt hashes that may be
guessable. Rights independently attested = NO; human acceptance =
NOT_ASSERTED; status remains PROPOSED. A trusted image pin is an engineering
dependency, not proof that source rights, physical page layout, OCR, a
MethodBody, model result, science, or customer release is accepted.

The CI smoke uses an explicitly test-only local image tag and invented
in-memory two-page PDF. Mocked subprocess tests check failure handling and
argv construction, not OS isolation. A successful exact-SHA Docker smoke and
independent security review are required before considering the resource
barrier tested. Real source use additionally needs owner F07 rights and
selection review. There is no server, daemon, issuer or publication path.
