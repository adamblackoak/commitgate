# Threat model

The proof addresses one transition risk: authority is obtained for one proposal but a different or unauthorised consequence reaches the adapter.

Covered adversarial conditions include:

- payload mutation after admission;
- tenant, request, decision, proposal-digest, action or policy-scope mismatch;
- missing or caller-tampered execution authority;
- future-issued, altered-lifetime or expired authority;
- reuse of consumed authority;
- invalid policy authority;
- missing, rebound or wrong-role human approval;
- duplicate attempts after a terminal receipt;
- incomplete reservation without a terminal receipt;
- two threaded duplicate callers racing before terminal receipt creation;
- adapter failure followed by a duplicate attempt;
- replay comparison attempting no mutation or authority creation.

For pre-consequence binding/authority failures, tests assert zero adapter invocation.

The concurrency claim is deliberately narrow: reservation mutation is synchronized for threaded callers sharing one in-process `CommitGateState`. It does not cover multiple processes or distributed execution.

Out of scope: compromised hosts, malicious adapter implementations, process-restart durability, cross-process/distributed transaction atomicity, external settlement truth, key management, production authentication, general policy correctness, host clock adjustment, or model-behaviour safety.
