from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import RLock

from .models import ExecutionReceipt, ExecutionToken, TokenStatus


@dataclass
class ExecutionReservation:
    idempotency_key: str
    proposal_digest: str
    receipt: ExecutionReceipt | None = None


@dataclass(frozen=True)
class ReservationResult:
    status: str
    receipt: ExecutionReceipt | None = None


class CommitGateState:
    """Synchronized in-process authority, reservation, and receipt state."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._tokens: dict[str, ExecutionToken] = {}
        self._token_ttls: dict[str, timedelta] = {}
        self._reservations: dict[str, ExecutionReservation] = {}

    def save_token(self, token: ExecutionToken, ttl: timedelta) -> ExecutionToken:
        if ttl <= timedelta(0):
            raise ValueError("authority TTL must be positive")
        with self._lock:
            self._tokens[token.token_id] = deepcopy(token)
            self._token_ttls[token.token_id] = ttl
            return deepcopy(self._tokens[token.token_id])

    def get_token(self, token_id: str) -> ExecutionToken | None:
        with self._lock:
            token = self._tokens.get(token_id)
            return deepcopy(token) if token is not None else None

    def get_token_ttl(self, token_id: str) -> timedelta | None:
        with self._lock:
            return self._token_ttls.get(token_id)

    def consume_token(self, token_id: str, consumed_at: datetime) -> ExecutionToken:
        with self._lock:
            token = self._tokens.get(token_id)
            if token is None:
                raise KeyError("execution token not found")
            if token.status != TokenStatus.ISSUED or token.consumed_at is not None:
                raise ValueError("execution token is not issued")
            token.status = TokenStatus.CONSUMED
            token.consumed_at = consumed_at
            self._tokens[token_id] = token
            return deepcopy(token)

    def reserve_execution(self, idempotency_key: str, proposal_digest: str) -> ReservationResult:
        """Atomically check/create an in-process reservation for one consequence."""
        with self._lock:
            reservation = self._reservations.get(idempotency_key)
            if reservation is None:
                self._reservations[idempotency_key] = ExecutionReservation(
                    idempotency_key=idempotency_key,
                    proposal_digest=proposal_digest,
                )
                return ReservationResult(status="reserved")
            if reservation.proposal_digest != proposal_digest:
                return ReservationResult(status="conflict")
            if reservation.receipt is None:
                return ReservationResult(status="incomplete")
            return ReservationResult(status="duplicate", receipt=deepcopy(reservation.receipt))

    def save_receipt(self, idempotency_key: str, receipt: ExecutionReceipt) -> ExecutionReceipt:
        with self._lock:
            reservation = self._reservations.get(idempotency_key)
            if reservation is None:
                raise KeyError("execution reservation not found")
            if reservation.proposal_digest != receipt.proposal_digest:
                raise ValueError("receipt digest does not match reservation")
            reservation.receipt = deepcopy(receipt)
            self._reservations[idempotency_key] = reservation
            return deepcopy(receipt)
