# CommitGate

**The action that executes must be the exact action that was evaluated and authorised.**

This is a bounded consequence-control proof extracted from CommitGate work developed for OpenAI Build Week 2026. It demonstrates the CommitGate invariant without publishing the complete parent AgentGate governance platform.

## Included

- canonical SHA-256 proposal identity;
- rejection of non-finite proposal values;
- deterministic decision fixtures rather than the AgentGate policy engine;
- synchronized in-process authoritative token state;
- configurable, expiring, single-use execution authority (five-minute default);
- immediate pre-adapter binding and stored-token identity validation;
- atomic in-process execution reservation for threaded callers;
- digest-bound duplicate and incomplete-reservation protection;
- terminal execution receipts;
- adversarial tests for drift, scope mismatch, token tampering/lifetime, approval rebinding, duplicate races, adapter failure and replay non-mutation.

## Deliberately excluded

The parent platform's general policy engine, evidence/risk evaluation machinery, broad approval framework, unrelated action workflows, product roadmap and general replay capability are not included.

## State and concurrency boundary

The default `CommitGateState` is deliberately small and in memory. It uses a thread lock around authority and reservation mutation, so the demonstrated atomicity claim is limited to synchronous/threaded callers sharing one state instance.

Process restart loses issued/consumed authority state, reservations and receipts. Separate processes do not share state. Applications that need restart durability or cross-process consistency must provide equivalent durable storage and atomicity outside this proof.

Expiry enforcement uses UTC wall-clock timestamps. The authority TTL is configurable and defaults to five minutes. No claim is made here about resilience to host clock adjustment.

## Run

Requires Python 3.12+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest -q
```

## Provenance

CommitGate was developed against an existing private AgentGate baseline during OpenAI Build Week 2026.

- Private parent repository: `adamblackoak/agentgate`
- AgentGate baseline commit: `8b61015037f7e6d0cb4fa21517f4c6af059f6942`
- Original development branch: `buildweek/commitgate`
- Submission-candidate tag: `buildweek-commitgate-submission`

This extraction preserves lineage references while intentionally omitting the complete parent implementation. Publication of a future standalone repository would establish public availability from that publication event; it would not retroactively turn private commit timestamps into independent third-party proof of creation dates.

## Claim boundary

This is an in-memory proof. Authority tokens are authoritative only within the shared `CommitGateState`; they are not signed capabilities or durable credentials. The adapter is a mock. No distributed exactly-once, cross-process atomicity, restart durability or external-settlement claim is made.

## Licence

This is a source-available, provenance-first release rather than an open-source release. The `LICENSE` permits viewing, GitHub cloning/forking, and local copying/execution for inspection, evaluation and testing. It does not grant broader modification, redistribution, deployment or commercial-use rights.

Built wheels are verification artifacts for the release process and are not distributed as public release assets or through a package index under this release posture.
