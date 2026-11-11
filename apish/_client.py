from __future__ import annotations

import os
import re
import random
import time
import asyncio
from typing import Any, AsyncIterator, Dict, Iterator, Optional, Union
from urllib.parse import quote

import httpx

from ._endpoints import CREDITS, PAGINATION, AsyncPlatforms, Platforms
from ._types import CallMeta, CallOptions, Result, TextResult
from .errors import ApishError

__version__ = "0.3.1"
DEFAULT_BASE_URL = "https://api.api.sh"


def _query(params: Dict[str, Any], options: Optional[CallOptions]) -> Dict[str, str]:
    q: Dict[str, str] = {}
    for k, v in params.items():
        if v is None or v == "":
            continue
        q[k] = ("true" if v else "false") if isinstance(v, bool) else str(v)
    o = options or {}
    if "raw" in o:
        q["raw"] = "1" if o["raw"] else "0"
    if o.get("fields"):
        f = o["fields"]
        q["fields"] = f if isinstance(f, str) else ",".join(f)
    if o.get("fresh"):
        q["fresh"] = "1"
    if o.get("output") and o["output"] != "json":
        q["output"] = o["output"]
    if o.get("records"):
        q["records"] = o["records"]
    return q


def _meta(res: httpx.Response, started: float) -> CallMeta:
    rem = res.headers.get("x-credits-remaining")
    return CallMeta(
        request_id=res.headers.get("x-request-id"),
        credits_used=int(res.headers.get("x-credits-used") or 0),
        credits_remaining=int(rem) if rem is not None else None,
        status=res.status_code,
        seconds=round(time.monotonic() - started, 3),
    )


def _result(res: httpx.Response, started: float) -> Union[Result, TextResult]:
    meta = _meta(res, started)
    if "json" not in res.headers.get("content-type", ""):
        return TextResult(res.text, meta)
    data = res.json()
    return Result(data if isinstance(data, dict) else {"items": data}, meta)


def _error(res: httpx.Response) -> ApishError:
    try:
        body = res.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    return ApishError(res.status_code, str(body.get("error") or body.get("message") or f"api.sh returned {res.status_code}"), body, res.headers.get("x-request-id"))


def _wait(res: Optional[httpx.Response], attempt: int) -> float:
    if res is not None:
        try:
            after = float(res.headers.get("retry-after", ""))
            if after > 0:
                return min(after, 30.0)
        except ValueError:
            pass
    return min(2 ** attempt, 10) + random.random() / 4


# ---------- live catalog and endpoints newer than this SDK version ----------
# Method names exactly as the generated endpoint code names them, so dynamic calls match the typed ones.
_PY_RESERVED = {"and", "as", "assert", "async", "await", "break", "class", "continue", "def", "del", "elif", "else", "except", "False", "finally", "for", "from", "global", "if", "import", "in", "is", "lambda", "None", "nonlocal", "not", "or", "pass", "raise", "return", "True", "try", "while", "with", "yield", "type", "id", "format", "filter", "input", "max", "min", "sum", "len", "list", "dict", "str", "int", "object", "range", "map", "next", "self"}


def _words(s: str) -> list:
    return [w for w in re.split(r"[^A-Za-z0-9]+|(?<=[a-z0-9])(?=[A-Z])", s) if w]


def _lead(w: list) -> list:
    return ["site", *w] if w and w[0][:1].isdigit() else w


def _camel(s: str) -> str:
    return "".join(w.lower() if i == 0 else w[0].upper() + w[1:].lower() for i, w in enumerate(_lead(_words(s))))


def _snake(s: str) -> str:
    return "_".join(w.lower() for w in _lead(_words(s)))


def _py(name: str) -> str:
    return f"{name}_" if name in _PY_RESERVED else name


def _route_for(catalog: Dict[str, Any], platform: str, method: str) -> Optional[str]:
    """The route behind apish.<platform>.<method>() in a live catalog."""
    for p in catalog.get("platforms", []):
        if _snake(_camel(p["slug"])) != platform:
            continue
        parts = []
        for e in p["endpoints"]:
            segs = [x for x in e["route"].split("/") if x]
            tail = "-".join(x for x in segs[1:] if x != "v1") or segs[0]
            parts.append((e["route"], segs[0], tail))
        tally: Dict[str, int] = {}
        for _, _, tail in parts:
            tally[_camel(tail)] = tally.get(_camel(tail), 0) + 1
        for route, first, tail in parts:
            m = _camel(f"{first}-{tail}") if tally[_camel(tail)] > 1 else _camel(tail)
            if _py(_snake(m)) == method:
                return route
    return None


class _DynamicPlatform:
    """A platform added after this SDK version: its methods are looked up in the live catalog."""

    def __init__(self, client: Any, name: str) -> None:
        self._client = client
        self._ns = name

    def __getattr__(self, method: str) -> Any:
        if method.startswith("_"):
            raise AttributeError(method)
        return self._client._endpoint(self._ns, method)


def _key(api_key: Optional[str]) -> str:
    key = api_key or os.environ.get("APISH_API_KEY", "")
    if not key:
        raise ValueError("api.sh: pass api_key=... or set APISH_API_KEY (create a key at https://app.api.sh/keys)")
    return key


class Apish(Platforms):
    """The api.sh client.

        from apish import Apish
        apish = Apish()                      # reads APISH_API_KEY
        profile = apish.tiktok.profile(username="nasa")
        print(profile["followers"], profile.meta.credits_used)

    Every platform is an attribute (apish.amazon, apish.google_maps, ...); every endpoint a method with typed,
    keyword-only parameters. `apish.call(route, params)` runs any route; `apish.account` covers your balance,
    usage, logs and past responses (free).
    """

    def __init__(self, api_key: Optional[str] = None, *, base_url: str = DEFAULT_BASE_URL, timeout: float = 120.0, max_retries: int = 2, http_client: Optional[httpx.Client] = None) -> None:
        self._key = _key(api_key)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._http = http_client or httpx.Client(timeout=timeout, headers={"user-agent": f"apish-python/{__version__}"})
        super().__init__(self.call)
        self.account = _Account(self.call)

    def call(self, route: str, params: Optional[Dict[str, Any]] = None, options: Optional[CallOptions] = None) -> Union[Result, TextResult]:
        """Runs any endpoint: apish.call("/reddit/v1/subreddit", {"subreddit": "python"})."""
        o = options or {}
        retries = o.get("max_retries", self.max_retries)
        started = time.monotonic()
        attempt = 0
        while True:
            try:
                res = self._http.get(self.base_url + route, params=_query(params or {}, o), headers={"x-api-key": self._key, "accept": "application/json"}, timeout=o.get("timeout", self.timeout))
            except httpx.TransportError:
                if attempt >= retries:
                    raise
                time.sleep(_wait(None, attempt))
                attempt += 1
                continue
            if res.is_success:
                return _result(res, started)
            err = _error(res)
            if not err.retryable or attempt >= retries:
                raise err
            time.sleep(_wait(res, attempt))
            attempt += 1

    def paginate(self, route: str, params: Optional[Dict[str, Any]] = None, options: Optional[CallOptions] = None, *, max_pages: Optional[int] = None) -> Iterator[Union[Result, TextResult]]:
        """Every page of a paginated endpoint: for page in apish.paginate("/reddit/v1/subreddit", {"subreddit": "python"}, max_pages=5)."""
        rule = PAGINATION.get(route)
        p = dict(params or {})
        n = 0
        while max_pages is None or n < max_pages:
            page = self.call(route, p, options)
            yield page
            n += 1
            nxt = page.get(rule[0]) if rule and isinstance(page, dict) else None
            if nxt in (None, "", False):
                return
            p[rule[1]] = nxt  # type: ignore[index]

    @staticmethod
    def credits(route: str) -> Optional[int]:
        """Credits per successful call for a route, as of this SDK version (live prices: apish.prices())."""
        return CREDITS.get(route)

    def catalog(self, *, refresh: bool = False) -> Dict[str, Any]:
        """The live catalog (free, no credits): platform_count, endpoint_count and every platform with its
        endpoints and today's price. Cached for an hour."""
        cached = getattr(self, "_live", None)
        if refresh or not cached or time.monotonic() - cached[0] > 3600:
            res = self._http.get(self.base_url + "/catalog", headers={"accept": "application/json"})
            if not res.is_success:
                raise _error(res)
            cached = (time.monotonic(), res.json())
            self._live = cached
        return cached[1]

    def prices(self) -> Dict[str, int]:
        """route -> credits per successful call, live."""
        return {e["route"]: e["credits"] for p in self.catalog()["platforms"] for e in p["endpoints"]}

    def resolve(self, platform: str, method: str) -> Optional[str]:
        """The route behind apish.<platform>.<method>() for platforms and endpoints newer than this SDK version."""
        return _route_for(self.catalog(), platform, method)

    def _endpoint(self, platform: str, method: str) -> Any:
        def run(*, options: Optional[CallOptions] = None, **params: Any) -> Union[Result, TextResult]:
            route = self.resolve(platform, method)
            if not route:
                raise AttributeError(f"api.sh: no endpoint {platform}.{method} (see https://api.sh/catalog)")
            return self.call(route, params, options)
        return run

    def __getattr__(self, name: str) -> Any:
        # a platform added after this SDK version: apish.newsite.search(q=...) finds its route in the live catalog
        if name.startswith("_"):
            raise AttributeError(name)
        return _DynamicPlatform(self, name)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "Apish":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class AsyncApish(AsyncPlatforms):
    """The api.sh client for asyncio: `await apish.tiktok.profile(username="nasa")`."""

    def __init__(self, api_key: Optional[str] = None, *, base_url: str = DEFAULT_BASE_URL, timeout: float = 120.0, max_retries: int = 2, http_client: Optional[httpx.AsyncClient] = None) -> None:
        self._key = _key(api_key)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._http = http_client or httpx.AsyncClient(timeout=timeout, headers={"user-agent": f"apish-python/{__version__}"})
        super().__init__(self.call)
        self.account = _AsyncAccount(self.call)

    async def call(self, route: str, params: Optional[Dict[str, Any]] = None, options: Optional[CallOptions] = None) -> Union[Result, TextResult]:
        o = options or {}
        retries = o.get("max_retries", self.max_retries)
        started = time.monotonic()
        attempt = 0
        while True:
            try:
                res = await self._http.get(self.base_url + route, params=_query(params or {}, o), headers={"x-api-key": self._key, "accept": "application/json"}, timeout=o.get("timeout", self.timeout))
            except httpx.TransportError:
                if attempt >= retries:
                    raise
                await asyncio.sleep(_wait(None, attempt))
                attempt += 1
                continue
            if res.is_success:
                return _result(res, started)
            err = _error(res)
            if not err.retryable or attempt >= retries:
                raise err
            await asyncio.sleep(_wait(res, attempt))
            attempt += 1

    async def paginate(self, route: str, params: Optional[Dict[str, Any]] = None, options: Optional[CallOptions] = None, *, max_pages: Optional[int] = None) -> AsyncIterator[Union[Result, TextResult]]:
        rule = PAGINATION.get(route)
        p = dict(params or {})
        n = 0
        while max_pages is None or n < max_pages:
            page = await self.call(route, p, options)
            yield page
            n += 1
            nxt = page.get(rule[0]) if rule and isinstance(page, dict) else None
            if nxt in (None, "", False):
                return
            p[rule[1]] = nxt  # type: ignore[index]

    @staticmethod
    def credits(route: str) -> Optional[int]:
        """Credits per successful call for a route, as of this SDK version (live prices: await apish.prices())."""
        return CREDITS.get(route)

    async def catalog(self, *, refresh: bool = False) -> Dict[str, Any]:
        """The live catalog (free, no credits); cached for an hour. See Apish.catalog."""
        cached = getattr(self, "_live", None)
        if refresh or not cached or time.monotonic() - cached[0] > 3600:
            res = await self._http.get(self.base_url + "/catalog", headers={"accept": "application/json"})
            if not res.is_success:
                raise _error(res)
            cached = (time.monotonic(), res.json())
            self._live = cached
        return cached[1]

    async def prices(self) -> Dict[str, int]:
        """route -> credits per successful call, live."""
        return {e["route"]: e["credits"] for p in (await self.catalog())["platforms"] for e in p["endpoints"]}

    async def resolve(self, platform: str, method: str) -> Optional[str]:
        """The route behind apish.<platform>.<method>() for platforms and endpoints newer than this SDK version."""
        return _route_for(await self.catalog(), platform, method)

    def _endpoint(self, platform: str, method: str) -> Any:
        async def run(*, options: Optional[CallOptions] = None, **params: Any) -> Union[Result, TextResult]:
            route = await self.resolve(platform, method)
            if not route:
                raise AttributeError(f"api.sh: no endpoint {platform}.{method} (see https://api.sh/catalog)")
            return await self.call(route, params, options)
        return run

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return _DynamicPlatform(self, name)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "AsyncApish":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()


class _Account:
    """Your balance, usage, logs and past responses. Free (no credits)."""

    def __init__(self, call: Any) -> None:
        self._call = call

    def get(self) -> Result:
        """Credits by bucket, plan, spend today / this month (UTC) and spend limits."""
        return self._call("/v1/account", {})

    def usage(self, days: int = 30) -> Result:
        """Calls, errors and credits per UTC day (1-90 days) and the top endpoints."""
        return self._call("/v1/account/usage", {"days": days})

    def logs(self, *, limit: int = 50, status: Optional[str] = None, route: Optional[str] = None, key: Optional[str] = None, since: Optional[str] = None, before: Optional[str] = None) -> Result:
        """Calls of the last 30 days, newest first; next page with before=result["next"]."""
        return self._call("/v1/account/logs", {"limit": limit, "status": status, "route": route, "key": key, "since": since, "before": before})

    def result(self, request_id: str, *, output: Optional[str] = None) -> Union[Result, TextResult]:
        """The response of an earlier call (its x-request-id) again, free, for 30 days."""
        return self._call(f"/v1/results/{quote(request_id)}", {}, {"output": output} if output else None)


class _AsyncAccount:
    """Your balance, usage, logs and past responses. Free (no credits)."""

    def __init__(self, call: Any) -> None:
        self._call = call

    async def get(self) -> Result:
        return await self._call("/v1/account", {})

    async def usage(self, days: int = 30) -> Result:
        return await self._call("/v1/account/usage", {"days": days})

    async def logs(self, *, limit: int = 50, status: Optional[str] = None, route: Optional[str] = None, key: Optional[str] = None, since: Optional[str] = None, before: Optional[str] = None) -> Result:
        return await self._call("/v1/account/logs", {"limit": limit, "status": status, "route": route, "key": key, "since": since, "before": before})

    async def result(self, request_id: str, *, output: Optional[str] = None) -> Union[Result, TextResult]:
        return await self._call(f"/v1/results/{quote(request_id)}", {}, {"output": output} if output else None)
