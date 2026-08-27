from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


class DecisionOutcome(StrEnum):
    ALLOW = "allow"
    REQUIRES_APPROVAL = "requires_approval"


class AuthorityType(StrEnum):
    POLICY = "policy"
    HUMAN = "human"


class TokenStatus(StrEnum):
    ISSUED = "issued"
    CONSUMED = "consumed"


class ExecutionStatus(StrEnum):
    EXECUTED = "executed"
    FAILED = "failed"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


@dataclass(frozen=True)
class Proposal:
    action_type: str
    payload: dict[str, Any]
    evidence: tuple[dict[str, Any], ...] = ()

    def as_payload(self) -> dict[str, Any]:
        return {"action_type": self.action_type, "payload": self.payload, "evidence": list(self.evidence)}


@dataclass(frozen=True)
class Admission:
    tenant_id: str
    request_id: str
    proposal: Proposal
    proposal_digest: str


@dataclass(frozen=True)
class DecisionFixture:
    tenant_id: str
    request_id: str
    decision_id: str
    proposal_digest: str
    policy_version: str
    outcome: DecisionOutcome
    required_approver_role: str | None = None


@dataclass(frozen=True)
class ApprovalFixture:
    tenant_id: str
    request_id: str
    decision_id: str
    approval_id: str
    proposal_digest: str
    policy_version: str
    actor_id: str
    actor_role: str
    required_approver_role: str
    approved: bool = True


@dataclass
class ExecutionToken:
    tenant_id: str
    request_id: str
    decision_id: str
    token_id: str
    proposal_digest: str
    action_type: str
    policy_version: str
    authority_type: AuthorityType
    authority_id: str
    authority_role: str | None
    issued_at: datetime
    expires_at: datetime
    approval_id: str | None = None
    status: TokenStatus = TokenStatus.ISSUED
    consumed_at: datetime | None = None


@dataclass(frozen=True)
class ExecutionReceipt:
    tenant_id: str
    request_id: str
    execution_id: str
    proposal_digest: str
    decision_id: str
    policy_version: str
    authority_type: AuthorityType
    authority_id: str
    authority_role: str | None
    token_id: str
    idempotency_key: str
    adapter: str
    status: ExecutionStatus
    result: dict[str, Any] = field(default_factory=dict)
