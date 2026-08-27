from __future__ import annotations

from .models import Admission, ApprovalFixture, DecisionFixture, DecisionOutcome, new_id

DEFAULT_POLICY_VERSION = "commitgate.fixture-policy.v1"


def allow_decision(admission: Admission, *, policy_version: str = DEFAULT_POLICY_VERSION, decision_id: str | None = None) -> DecisionFixture:
    return DecisionFixture(tenant_id=admission.tenant_id, request_id=admission.request_id, decision_id=decision_id or new_id("dec"), proposal_digest=admission.proposal_digest, policy_version=policy_version, outcome=DecisionOutcome.ALLOW)


def approval_required_decision(admission: Admission, *, required_role: str = "reviewer", policy_version: str = DEFAULT_POLICY_VERSION, decision_id: str | None = None) -> DecisionFixture:
    return DecisionFixture(tenant_id=admission.tenant_id, request_id=admission.request_id, decision_id=decision_id or new_id("dec"), proposal_digest=admission.proposal_digest, policy_version=policy_version, outcome=DecisionOutcome.REQUIRES_APPROVAL, required_approver_role=required_role)


def approved_fixture(admission: Admission, decision: DecisionFixture, *, actor_id: str = "reviewer_1", actor_role: str | None = None, approval_id: str | None = None) -> ApprovalFixture:
    required_role = decision.required_approver_role or "reviewer"
    return ApprovalFixture(tenant_id=admission.tenant_id, request_id=admission.request_id, decision_id=decision.decision_id, approval_id=approval_id or new_id("approval"), proposal_digest=admission.proposal_digest, policy_version=decision.policy_version, actor_id=actor_id, actor_role=actor_role or required_role, required_approver_role=required_role, approved=True)
