from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from .models import Admission, Proposal, new_id


def _reject_non_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("proposal contains a non-finite number")
    if isinstance(value, dict):
        for child in value.values():
            _reject_non_finite(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _reject_non_finite(child)


def canonical_proposal_payload(tenant_id: str, proposal: Proposal) -> dict[str, Any]:
    payload = {"tenant_id": tenant_id, **proposal.as_payload()}
    _reject_non_finite(payload)
    return payload


def canonical_json(payload: dict[str, Any]) -> bytes:
    _reject_non_finite(payload)
    return json.dumps(payload, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def proposal_digest(tenant_id: str, proposal: Proposal) -> str:
    return hashlib.sha256(canonical_json(canonical_proposal_payload(tenant_id, proposal))).hexdigest()


def admit(tenant_id: str, proposal: Proposal, *, request_id: str | None = None) -> Admission:
    return Admission(tenant_id=tenant_id, request_id=request_id or new_id("req"), proposal=proposal, proposal_digest=proposal_digest(tenant_id, proposal))


def execution_idempotency_key(admission: Admission) -> str:
    return ":".join((admission.tenant_id, admission.request_id, admission.proposal.action_type, admission.proposal_digest))
