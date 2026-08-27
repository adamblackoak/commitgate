# Limitations

This repository is intentionally a proof slice.

- Authority records, consumed-token state, reservations and receipts are in memory and disappear on process restart.
- Reservation mutation is synchronized only for threaded callers sharing one `CommitGateState` instance.
- No cross-process or distributed atomicity is claimed.
- Execution tokens are mutable in-process authority records, not signed cryptographic capabilities or durable credentials.
- Authority TTL is configurable and defaults to five minutes.
- Expiry enforcement uses UTC wall-clock timestamps; resilience to host clock adjustment is not claimed.
- No production authentication or identity provider is included.
- Decision and approval inputs are fixtures; this is not a general policy-authoring system.
- The adapter is a mock and its receipt is not proof of external settlement.
- A terminal adapter failure does not automatically retry under consumed authority.
- Comparative replay checks proposal identity only and creates no current authority.

Applications that require restart durability or cross-process consistency need an external state implementation with equivalent authority, reservation and atomicity semantics.

These limitations are part of the claim boundary, not pending promises.
