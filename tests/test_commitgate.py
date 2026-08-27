from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from threading import Event
import math

import pytest

from commitgate import AuthorityError, CommitGateState, ExecutionBoundary, ExecutionIntegrityError, MockAdapter, Proposal, admit, allow_decision, approval_required_decision, approved_fixture, issue_human_authority, issue_policy_authority, proposal_digest
from commitgate.integrity import execution_idempotency_key
from commitgate.models import ExecutionStatus, TokenStatus

NOW = datetime(2026, 8, 27, 8, 0, tzinfo=timezone.utc)


def refund(amount=25):
    return Proposal(action_type="refund_customer", payload={"customer_id": "cus_123", "amount": amount, "currency": "GBP"}, evidence=({"evidence_id": "ticket_123", "type": "ticket"},))


def policy_setup(*, now=NOW, ttl=timedelta(minutes=5)):
    state = CommitGateState()
    admission = admit("tenant_demo", refund(), request_id="req_demo")
    decision = allow_decision(admission, decision_id="dec_demo")
    token = issue_policy_authority(state, admission, decision, now=now, ttl=ttl)
    return state, admission, decision, token


def mutate_authority(state, token, **changes):
    for field, value in changes.items():
        setattr(token, field, value)
    with state._lock:
        persisted = state._tokens[token.token_id]
        for field, value in changes.items():
            setattr(persisted, field, value)
        state._tokens[token.token_id] = persisted


def assert_refused(state, admission, decision, token, *, reason, proposal=None, approval=None):
    adapter = MockAdapter()
    with pytest.raises(ExecutionIntegrityError) as exc:
        ExecutionBoundary(state).execute(admission, decision, token, proposal or refund(), adapter, approval=approval, now=NOW)
    assert exc.value.reason_code == reason
    assert adapter.calls == []
    return exc.value


def test_canonical_object_order_and_tenant_binding():
    a = Proposal("x", {"b": 2, "a": 1})
    b = Proposal("x", {"a": 1, "b": 2})
    assert proposal_digest("t1", a) == proposal_digest("t1", b)
    assert proposal_digest("t1", a) != proposal_digest("t2", a)


def test_array_order_and_payload_mutation_change_digest():
    assert proposal_digest("t", Proposal("x", {"items": ["a", "b"]})) != proposal_digest("t", Proposal("x", {"items": ["b", "a"]}))
    assert proposal_digest("t", refund(25)) != proposal_digest("t", refund(26))


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_rejected(value):
    with pytest.raises(ValueError, match="non-finite"):
        admit("t", Proposal("x", {"value": value}))


def test_unchanged_executes_and_receipt_is_bound():
    state, admission, decision, token = policy_setup()
    adapter = MockAdapter()
    receipt = ExecutionBoundary(state).execute(admission, decision, token, refund(), adapter, now=NOW)
    assert receipt.status == ExecutionStatus.EXECUTED
    assert receipt.proposal_digest == admission.proposal_digest == decision.proposal_digest
    assert receipt.decision_id == decision.decision_id and receipt.token_id == token.token_id
    assert len(adapter.calls) == 1 and token.status == TokenStatus.CONSUMED
    assert state.get_token(token.token_id).status == TokenStatus.CONSUMED


def test_proposal_drift_blocks_before_adapter():
    state, admission, decision, token = policy_setup()
    assert_refused(state, admission, decision, token, reason="proposal_drift", proposal=refund(26))
    assert token.status == TokenStatus.ISSUED


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("tenant", "tenant_scope_mismatch"),
        ("request", "request_scope_mismatch"),
        ("decision", "decision_scope_mismatch"),
        ("digest", "proposal_digest_mismatch"),
        ("action", "action_scope_mismatch"),
        ("policy", "policy_scope_mismatch"),
    ],
)
def test_scope_mismatch_blocks_before_adapter(case, reason):
    state, admission, decision, token = policy_setup()
    if case == "tenant":
        decision = replace(decision, tenant_id="tenant_other")
    elif case == "request":
        decision = replace(decision, request_id="req_other")
    elif case == "decision":
        mutate_authority(state, token, decision_id="dec_other")
    elif case == "digest":
        decision = replace(decision, proposal_digest="0" * 64)
    elif case == "action":
        mutate_authority(state, token, action_type="update_ticket")
    elif case == "policy":
        mutate_authority(state, token, policy_version="other-policy")
    assert_refused(state, admission, decision, token, reason=reason)


def test_missing_token_blocks_before_adapter():
    state, admission, decision, token = policy_setup()
    with state._lock:
        state._tokens.pop(token.token_id)
    assert_refused(state, admission, decision, token, reason="execution_token_missing")


def test_supplied_token_must_match_authoritative_state():
    state, admission, decision, token = policy_setup()
    supplied = replace(token, authority_id="tampered")
    assert_refused(state, admission, decision, supplied, reason="execution_token_identity_mismatch")


def test_future_issued_token_blocks_before_adapter():
    state, admission, decision, token = policy_setup(now=NOW + timedelta(minutes=1))
    assert_refused(state, admission, decision, token, reason="execution_token_not_yet_valid")


def test_altered_authoritative_lifetime_blocks_before_adapter():
    state, admission, decision, token = policy_setup()
    mutate_authority(state, token, expires_at=token.expires_at + timedelta(seconds=1))
    assert_refused(state, admission, decision, token, reason="execution_token_lifetime_invalid")


def test_configurable_ttl_and_expiry():
    state, admission, decision, token = policy_setup(ttl=timedelta(minutes=2))
    adapter = MockAdapter()
    with pytest.raises(ExecutionIntegrityError) as exc:
        ExecutionBoundary(state).execute(admission, decision, token, refund(), adapter, now=NOW + timedelta(minutes=2))
    assert exc.value.reason_code == "token_expired"
    assert adapter.calls == []


def test_consumed_token_reuse_cannot_reinvoke_adapter():
    state, admission, decision, token = policy_setup()
    adapter = MockAdapter()
    boundary = ExecutionBoundary(state)
    boundary.execute(admission, decision, token, refund(), adapter, now=NOW)
    with pytest.raises(ExecutionIntegrityError) as exc:
        boundary.execute(admission, decision, token, refund(), adapter, now=NOW)
    assert exc.value.reason_code == "token_consumed"
    assert len(adapter.calls) == 1


def test_policy_authority_binding_is_rechecked():
    state, admission, decision, token = policy_setup()
    mutate_authority(state, token, authority_id="other-policy")
    assert_refused(state, admission, decision, token, reason="policy_authority_invalid")


def test_same_digest_duplicate_returns_terminal_receipt_without_second_adapter_call():
    state, admission, decision, token1 = policy_setup()
    token2 = issue_policy_authority(state, admission, decision, now=NOW)
    adapter = MockAdapter()
    boundary = ExecutionBoundary(state)
    first = boundary.execute(admission, decision, token1, refund(), adapter, now=NOW)
    duplicate = boundary.execute(admission, decision, token2, refund(), adapter, now=NOW)
    assert duplicate == first
    assert len(adapter.calls) == 1
    assert token2.status == TokenStatus.CONSUMED


def test_incomplete_reservation_never_fabricates_duplicate_success():
    state, admission, decision, token = policy_setup()
    key = execution_idempotency_key(admission)
    assert state.reserve_execution(key, admission.proposal_digest).status == "reserved"
    adapter = MockAdapter()
    with pytest.raises(ExecutionIntegrityError) as exc:
        ExecutionBoundary(state).execute(admission, decision, token, refund(), adapter, now=NOW)
    assert exc.value.reason_code == "idempotency_receipt_missing"
    assert token.status == TokenStatus.ISSUED
    assert adapter.calls == []


class BlockingAdapter(MockAdapter):
    def __init__(self, entered, release):
        super().__init__()
        self.entered = entered
        self.release = release

    def execute(self, proposal):
        self.calls.append(proposal)
        self.entered.set()
        assert self.release.wait(timeout=2)
        return {"accepted": True, "action_type": proposal.action_type}


def test_threaded_concurrent_duplicate_cannot_cross_incomplete_reservation():
    state, admission, decision, token1 = policy_setup()
    token2 = issue_policy_authority(state, admission, decision, now=NOW)
    entered = Event()
    release = Event()
    adapter = BlockingAdapter(entered, release)
    boundary = ExecutionBoundary(state)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(boundary.execute, admission, decision, token1, refund(), adapter, now=NOW)
        assert entered.wait(timeout=2)
        second_future = pool.submit(boundary.execute, admission, decision, token2, refund(), adapter, now=NOW)
        with pytest.raises(ExecutionIntegrityError) as exc:
            second_future.result(timeout=2)
        assert exc.value.reason_code == "idempotency_receipt_missing"
        assert token2.status == TokenStatus.ISSUED
        release.set()
        first = first_future.result(timeout=2)

    assert len(adapter.calls) == 1
    duplicate = boundary.execute(admission, decision, token2, refund(), adapter, now=NOW)
    assert duplicate == first
    assert len(adapter.calls) == 1


def test_adapter_failure_is_terminal_and_authority_stays_consumed():
    state, admission, decision, token1 = policy_setup()
    token2 = issue_policy_authority(state, admission, decision, now=NOW)
    adapter = MockAdapter(fail=True)
    boundary = ExecutionBoundary(state)
    failed = boundary.execute(admission, decision, token1, refund(), adapter, now=NOW)
    assert failed.status == ExecutionStatus.FAILED
    assert failed.result["error_type"] == "RuntimeError"
    assert token1.status == TokenStatus.CONSUMED
    duplicate = boundary.execute(admission, decision, token2, refund(), adapter, now=NOW)
    assert duplicate == failed
    assert len(adapter.calls) == 1


def human_setup():
    state = CommitGateState()
    admission = admit("tenant_demo", refund(125), request_id="req_review")
    decision = approval_required_decision(admission, required_role="refund_reviewer", decision_id="dec_review")
    approval = approved_fixture(admission, decision, actor_id="alice", actor_role="refund_reviewer", approval_id="approval_review")
    token = issue_human_authority(state, admission, decision, approval, now=NOW)
    return state, admission, decision, approval, token


def test_human_authority_binds_real_actor_and_role():
    state, admission, decision, approval, token = human_setup()
    adapter = MockAdapter()
    receipt = ExecutionBoundary(state).execute(admission, decision, token, refund(125), adapter, approval=approval, now=NOW)
    assert receipt.authority_id == "alice"
    assert receipt.authority_role == "refund_reviewer"
    assert len(adapter.calls) == 1


def test_wrong_role_cannot_issue_human_authority():
    state = CommitGateState()
    admission = admit("tenant_demo", refund(125))
    decision = approval_required_decision(admission, required_role="refund_reviewer")
    bad = approved_fixture(admission, decision, actor_role="support_agent")
    with pytest.raises(AuthorityError, match="required role"):
        issue_human_authority(state, admission, decision, bad, now=NOW)


@pytest.mark.parametrize("case", ["missing", "rebound"])
def test_missing_or_rebound_human_authority_blocks_before_adapter(case):
    state, admission, decision, approval, token = human_setup()
    supplied = None if case == "missing" else replace(approval, actor_id="mallory")
    reason = "human_authority_missing" if case == "missing" else "human_authority_mismatch"
    assert_refused(state, admission, decision, token, reason=reason, proposal=refund(125), approval=supplied)


def test_comparative_replay_creates_no_authority_or_execution():
    state, admission, decision, token = policy_setup()
    boundary = ExecutionBoundary(state)
    adapter = MockAdapter()
    assert boundary.compare_replay(admission, refund()) is True
    assert boundary.compare_replay(admission, refund(26)) is False
    assert state.get_token(token.token_id).status == TokenStatus.ISSUED
    assert adapter.calls == []
