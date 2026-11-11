from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TypedDict, Union


class CallOptions(TypedDict, total=False):
    """Options for one call, on top of the endpoint's own parameters."""

    raw: bool
    """False leaves out the bulky `raw` source blocks (often 10-30x smaller)."""
    fields: Union[List[str], str]
    """Only these fields, e.g. ["posts.id", "posts.title"]. Call metadata is always included."""
    fresh: bool
    """Skip the 24-hour cache and fetch live."""
    output: str
    """"csv" or "ndjson" returns the response's records as text instead of JSON."""
    records: str
    """With output csv/ndjson: which top-level list becomes the rows ("." = the whole object as one row)."""
    timeout: float
    """Seconds (default: the client's, 120)."""
    max_retries: int
    """Retries on 502/503/504 and network errors (default: the client's, 2). Failed calls are never charged."""


@dataclass(frozen=True)
class CallMeta:
    """Facts about the call, from the response headers."""

    request_id: Optional[str]
    credits_used: int
    credits_remaining: Optional[int]
    status: int
    seconds: float


class Result(Dict[str, Any]):
    """A JSON response: a dict of its fields, plus `.meta` (request id, credits)."""

    meta: CallMeta

    def __init__(self, data: Dict[str, Any], meta: CallMeta) -> None:
        super().__init__(data)
        self.meta = meta


class TextResult(str):
    """A CSV / NDJSON response: the text, plus `.meta`."""

    meta: CallMeta

    def __new__(cls, text: str, meta: CallMeta) -> "TextResult":
        obj = super().__new__(cls, text)
        obj.meta = meta
        return obj
