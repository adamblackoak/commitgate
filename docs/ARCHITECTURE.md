# Architecture

CommitGate is a narrow boundary between an already-evaluated proposal and a consequential adapter.

```text
proposal
  -> canonical identity
  -> decision fixture
  -> persisted scoped authority
  -> immediate binding + stored-authority validation
  -> atomic in-process execution reservation
  -> authority consumption
  -> adapter
  -> bound terminal receipt
```

The extraction deliberately begins after broad governance reasoning. It accepts a deterministic decision fixture instead of implementing AgentGate's parent policy machinery.

Proposal identity includes tenant, action type, payload and evidence. Object keys are canonicalised; array order remains significant; non-finite numbers are rejected before admission.

Policy authority can be issued only for an `allow` decision. Human authority can be issued only for a `requires_approval` decision with a bound approval whose actor actually holds the required role. Authority records are scoped to tenant, request, decision, proposal digest, action type, policy version and authority identity. TTL is configurable with a five-minute default.

Immediately before adapter invocation, CommitGate recomputes proposal identity and validates the supplied token against synchronized authoritative state. It then atomically reserves the digest-bound idempotency key within the shared in-process state. A conflicting or incomplete reservation stops before the adapter. A terminal duplicate returns the existing receipt without invoking the adapter again.

Authority is consumed before the adapter. Adapter failure therefore produces a terminal failure receipt rather than implicit reuse of the same authority.

The synchronization model is synchronous/threaded callers sharing one `CommitGateState` instance. No cross-process or distributed atomicity is claimed. All default state is in memory and disappears on process restart.

The included replay function is comparative only: it reports whether a candidate proposal has the admitted identity. It creates no decision, token, authority or execution.
