from __future__ import annotations

from typing import Any, Dict, Optional


class ApishError(Exception):
    """An error answered by api.sh. Failed calls are never charged.

    status: 400 bad input, 401 bad key, 402 out of credits or a spend limit, 404 not found,
    502 the source site failed (retry), 503 endpoint paused.
    """

    def __init__(self, status: int, message: str, body: Optional[Dict[str, Any]] = None, request_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.body = body or {}
        self.request_id = request_id

    @property
    def insufficient_credits(self) -> bool:
        return self.status == 402 and not self.body.get("spend_limit")

    @property
    def spend_limit(self) -> Optional[str]:
        """"daily" or "monthly" when a spend limit you set was reached."""
        return self.body.get("spend_limit") if self.status == 402 else None

    @property
    def retryable(self) -> bool:
        return self.status in (502, 503, 504)

    def __repr__(self) -> str:
        return f"ApishError(status={self.status}, message={self.message!r}, request_id={self.request_id!r})"
