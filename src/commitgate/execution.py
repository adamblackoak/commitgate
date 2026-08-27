from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from .integrity import execution_idempotency_key, proposal_digest
from .models import Admission, ApprovalFixture, AuthorityType, DecisionFixture, DecisionOutcome, ExecutionReceipt, ExecutionStatus, ExecutionToken, Proposal, TokenStatus, new_id
from .state import CommitGateState


class ExecutionIntegrityError(ValueError):
    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class Adapter(Protocol):
    name: str

    def execute(self, proposal: Proposal) -> dict[str, Any]: ...


@dataclass
class MockAdapter:
    name: str = "mock"
    fail: bool = False

    def __post_init__(self) -> None:
        self.calls: list[Proposal] = []

    def execute(self, proposal: Proposal) -> dict[str, Any]:
        self.calls.append(proposal)
        if self.fail:
            raise RuntimeError("mock adapter failure")
        return {"accepted": True, "action_type": proposal.action_type}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ExecutionBoundary:
    def __init__(self, state: CommitGateState) -> None:
        self.state = state

    def execute(
        self,
        admission: Admission,
        decision: DecisionFixture,
        token: ExecutionToken,
        current_proposal: Proposal,
        adapter: Adapter,
        *,
        approval: ApprovalFixture | None = None,
        now: datetime | None = None,
    ) -> ExecutionReceipt:
        checked_at = now or utc_now()
        self._validate_binding(admission, decision, token, current_proposal, approval, checked_at)
        key = execution_idempotency_key(admission)
        reservation = self.state.reserve_execution(key, admission.proposal_digest)
        if reservation.status == "duplicate" and reservation.receipt is not None:
            self._consume(token, checked_at)
            return reservation.receipt
        if reservation.status == "conflict":
            self._fail("idempotency_digest_conflict", "idempotency key is bound to another proposal digest")
        if reservation.status == "incomplete":
            self._fail("idempotency_receipt_missing", "prior reservation has no terminal receipt")

        self._consume(token, checked_at)
        try:
            result = adapter.execute(current_proposal)
            status = ExecutionStatus.EXECUTED
        except Exception as exc:
            result = {"error": "adapter failed", "error_type": type(exc).__name__}
            status = ExecutionStatus.FAILED
        receipt = ExecutionReceipt(
            tenant_id=admission.tenant_id,
            request_id=admission.request_id,
            execution_id=new_id("exec"),
            proposal_digest=admission.proposal_digest,
            decision_id=decision.decision_id,
            policy_version=decision.policy_version,
            authority_type=token.authority_type,
            authority_id=token.authority_id,
            authority_role=token.authority_role,
            token_id=token.token_id,
            idempotency_key=key,
            adapter=adapter.name,
            status=status,
            result=result,
        )
        return self.state.save_receipt(key, receipt)

    def compare_replay(self, admission: Admission, candidate: Proposal) -> bool:
        return proposal_digest(admission.tenant_id, candidate) == admission.proposal_digest

    def _consume(self, token: ExecutionToken, at: datetime) -> None:
        try:
            self.state.consume_token(token.token_id, at)
        except (KeyError, ValueError):
            raise ExecutionIntegrityError("token_consumed", "execution authority is not usable") from None
        token.status = TokenStatus.CONSUMED
        token.consumed_at = at

    def _fail(self, code: str, message: str) -> None:
        raise ExecutionIntegrityError(code, message)

    def _validate_binding(
        self,
        admission: Admission,
        decision: DecisionFixture,
        token: ExecutionToken,
        current_proposal: Proposal,
        approval: ApprovalFixture | None,
        now: datetime,
    ) -> None:
        current_digest = proposal_digest(admission.tenant_id, current_proposal)
        if current_digest != admission.proposal_digest:
            self._fail("proposal_drift", "proposal changed after admission")

        persisted_token = self.state.get_token(token.token_id)
        if persisted_token is None:
            self._fail("execution_token_missing", "execution authority is not present in authoritative state")
        if persisted_token != token:
            self._fail("execution_token_identity_mismatch", "supplied token does not match authoritative state")

        expected_ttl = self.state.get_token_ttl(token.token_id)
        if expected_ttl is None:
            self._fail("execution_token_missing", "execution authority lifetime is not present in authoritative state")
        if token.expires_at != token.issued_at + expected_ttl:
            self._fail("execution_token_lifetime_invalid", "execution authority lifetime does not match issuance configuration")
        if now < token.issued_at:
            self._fail("execution_token_not_yet_valid", "execution authority was issued in the future")
        if now >= token.expires_at:
            self._fail("token_expired", "execution authority is outside its validity window")

        if decision.tenant_id != admission.tenant_id or token.tenant_id != admission.tenant_id:
            self._fail("tenant_scope_mismatch", "tenant scope does not match admission")
        if decision.request_id != admission.request_id or token.request_id != admission.request_id:
            self._fail("request_scope_mismatch", "request scope does not match admission")
        if token.decision_id != decision.decision_id:
            self._fail("decision_scope_mismatch", "token is not bound to this decision")
        if decision.proposal_digest != admission.proposal_digest or token.proposal_digest != admission.proposal_digest:
            self._fail("proposal_digest_mismatch", "decision or token is not bound to this proposal")
        if token.action_type != admission.proposal.action_type:
            self._fail("action_scope_mismatch", "token action type does not match proposal")
        if token.policy_version != decision.policy_version:
            self._fail("policy_scope_mismatch", "token policy version does not match decision")
        if token.status != TokenStatus.ISSUED or token.consumed_at is not None:
            self._fail("token_consumed", "execution authority has already been consumed")

        if token.authority_type == AuthorityType.POLICY:
            if decision.outcome != DecisionOutcome.ALLOW or token.authority_id != decision.policy_version or token.authority_role is not None or approval is not None:
                self._fail("policy_authority_invalid", "policy authority binding is invalid")
            return
        if token.authority_type == AuthorityType.HUMAN:
            if decision.outcome != DecisionOutcome.REQUIRES_APPROVAL or approval is None or not approval.approved:
                self._fail("human_authority_missing", "a bound approval is required")
            if approval.approval_id != token.approval_id or approval.tenant_id != admission.tenant_id or approval.request_id != admission.request_id or approval.decision_id != decision.decision_id or approval.proposal_digest != admission.proposal_digest or approval.policy_version != decision.policy_version or approval.required_approver_role != decision.required_approver_role or approval.actor_id != token.authority_id or approval.actor_role != token.authority_role or approval.actor_role != decision.required_approver_role:
                self._fail("human_authority_mismatch", "human authority binding does not match approval")
            return
        self._fail("authority_type_invalid", "unknown authority type")
