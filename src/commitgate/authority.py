from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import Admission, ApprovalFixture, AuthorityType, DecisionFixture, DecisionOutcome, ExecutionToken, new_id
from .state import CommitGateState

DEFAULT_TOKEN_TTL = timedelta(minutes=5)


class AuthorityError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_decision_binding(admission: Admission, decision: DecisionFixture) -> None:
    if decision.tenant_id != admission.tenant_id:
        raise AuthorityError("decision tenant does not match admission")
    if decision.request_id != admission.request_id:
        raise AuthorityError("decision request does not match admission")
    if decision.proposal_digest != admission.proposal_digest:
        raise AuthorityError("decision digest does not match admission")


def issue_policy_authority(
    state: CommitGateState,
    admission: Admission,
    decision: DecisionFixture,
    *,
    now: datetime | None = None,
    ttl: timedelta = DEFAULT_TOKEN_TTL,
) -> ExecutionToken:
    _validate_decision_binding(admission, decision)
    if decision.outcome != DecisionOutcome.ALLOW:
        raise AuthorityError("policy authority requires an allow decision")
    issued_at = now or utc_now()
    token = ExecutionToken(
        tenant_id=admission.tenant_id,
        request_id=admission.request_id,
        decision_id=decision.decision_id,
        token_id=new_id("token"),
        proposal_digest=admission.proposal_digest,
        action_type=admission.proposal.action_type,
        policy_version=decision.policy_version,
        authority_type=AuthorityType.POLICY,
        authority_id=decision.policy_version,
        authority_role=None,
        issued_at=issued_at,
        expires_at=issued_at + ttl,
    )
    return state.save_token(token, ttl)


def issue_human_authority(
    state: CommitGateState,
    admission: Admission,
    decision: DecisionFixture,
    approval: ApprovalFixture,
    *,
    now: datetime | None = None,
    ttl: timedelta = DEFAULT_TOKEN_TTL,
) -> ExecutionToken:
    _validate_decision_binding(admission, decision)
    if decision.outcome != DecisionOutcome.REQUIRES_APPROVAL:
        raise AuthorityError("human authority requires an approval decision")
    if not approval.approved:
        raise AuthorityError("approval is not approved")
    if approval.tenant_id != admission.tenant_id or approval.request_id != admission.request_id:
        raise AuthorityError("approval scope does not match admission")
    if approval.decision_id != decision.decision_id:
        raise AuthorityError("approval decision does not match")
    if approval.proposal_digest != admission.proposal_digest:
        raise AuthorityError("approval digest does not match")
    if approval.policy_version != decision.policy_version:
        raise AuthorityError("approval policy version does not match")
    if approval.required_approver_role != decision.required_approver_role:
        raise AuthorityError("approval required role does not match decision")
    if approval.actor_role != decision.required_approver_role:
        raise AuthorityError("approver does not hold the required role")
    issued_at = now or utc_now()
    token = ExecutionToken(
        tenant_id=admission.tenant_id,
        request_id=admission.request_id,
        decision_id=decision.decision_id,
        token_id=new_id("token"),
        proposal_digest=admission.proposal_digest,
        action_type=admission.proposal.action_type,
        policy_version=decision.policy_version,
        authority_type=AuthorityType.HUMAN,
        authority_id=approval.actor_id,
        authority_role=approval.actor_role,
        approval_id=approval.approval_id,
        issued_at=issued_at,
        expires_at=issued_at + ttl,
    )
    return state.save_token(token, ttl)
