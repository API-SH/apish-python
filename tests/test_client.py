import json

import httpx
import pytest

from apish import Apish, ApishError, AsyncApish
from apish._endpoints import PAGINATION


def client(handler, **kw):
    return Apish("ash_test", http_client=httpx.Client(transport=httpx.MockTransport(handler)), **kw)


def ok(body, headers=None, ctype="application/json"):
    return httpx.Response(200, content=body if isinstance(body, str) else json.dumps(body), headers={"content-type": ctype, **(headers or {})})


def test_typed_method_and_meta():
    seen = []

    def h(req):
        seen.append(req)
        return ok({"username": "nasa"}, {"x-request-id": "r1", "x-credits-used": "2", "x-credits-remaining": "98"})

    r = client(h).tiktok.profile(username="nasa", options={"raw": False, "fields": ["username"]})
    assert r["username"] == "nasa" and r.meta.request_id == "r1" and r.meta.credits_used == 2 and r.meta.credits_remaining == 98
    u = seen[0].url
    assert u.path == "/tiktok/v1/profile" and u.params["username"] == "nasa" and u.params["raw"] == "0" and u.params["fields"] == "username"
    assert seen[0].headers["x-api-key"] == "ash_test"


def test_retry_then_ok_and_no_retry_on_400(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    replies = [httpx.Response(502, json={"success": False, "error": "upstream"}), ok({"x": 1})]
    assert client(lambda r: replies.pop(0)).call("/reddit/v1/subreddit", {"subreddit": "x"})["x"] == 1
    n = []
    with pytest.raises(ApishError) as e:
        client(lambda r: n.append(1) or httpx.Response(400, json={"success": False, "error": "missing"})).call("/x")
    assert e.value.status == 400 and str(e.value) == "missing" and len(n) == 1


def test_402_kinds():
    with pytest.raises(ApishError) as e:
        client(lambda r: httpx.Response(402, json={"error": "limit", "spend_limit": "daily"})).call("/x")
    assert e.value.spend_limit == "daily" and not e.value.insufficient_credits


def test_csv_text_result():
    r = client(lambda req: ok("a,b\n1,2\n", {"x-request-id": "r2"}, "text/csv")).amazon.search(q="x", options={"output": "csv"})
    assert r == "a,b\n1,2\n" and r.meta.request_id == "r2"


def test_reserved_param_names_are_suffixed():
    import inspect
    from apish import _endpoints as ep
    bad = [name for cls in vars(ep).values() if inspect.isclass(cls) for name, fn in vars(cls).items() if callable(fn) for p in inspect.signature(fn).parameters if p in ("type", "from", "id", "format")]
    assert not bad


def test_paginate():
    route = next(r for r, (frm, to) in PAGINATION.items() if to == "page")
    pages = [ok({"items": [1], "next_page": 2}), ok({"items": [2], "next_page": None})]
    seen = []
    got = [p["items"][0] for p in client(lambda r: seen.append(r) or pages.pop(0)).paginate(route, {})]
    assert got == [1, 2] and seen[1].url.params["page"] == "2"


def test_account_paths():
    seen = []
    c = client(lambda r: seen.append(r) or ok({"success": True}))
    c.account.usage(7)
    c.account.result("abc-1")
    assert seen[0].url.path == "/v1/account/usage" and seen[0].url.params["days"] == "7" and seen[1].url.path == "/v1/results/abc-1"


def test_async():
    import asyncio

    async def run():
        a = AsyncApish("k", http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: ok({"title": "t"}))))
        r = await a.reddit.subreddit(subreddit="python")
        await a.aclose()
        return r["title"]

    assert asyncio.run(run()) == "t"


CAT = {"version": "v", "platform_count": 2, "endpoint_count": 3, "platforms": [
    {"slug": "hacker-news", "name": "Hacker News", "category": "news", "endpoints": [{"route": "/hackernews/v1/top", "credits": 1}, {"route": "/hackernews/v1/brand-new", "credits": 4}]},
    {"slug": "new-site", "name": "New Site", "category": "x", "endpoints": [{"route": "/newsite/v1/search", "credits": 2}]},
]}


def test_live_catalog_prices_and_newer_endpoints():
    seen = []

    def h(req):
        seen.append(req.url.path)
        return ok(CAT) if req.url.path == "/catalog" else ok({"ok": 1})

    a = client(h)
    assert a.catalog()["endpoint_count"] == 3 and a.prices()["/hackernews/v1/brand-new"] == 4
    a.hacker_news.brand_new(id="1")
    assert a.new_site.search(q="x")["ok"] == 1
    assert seen == ["/catalog", "/hackernews/v1/brand-new", "/newsite/v1/search"]
    with pytest.raises(AttributeError):
        a.new_site.nope()
    with pytest.raises(AttributeError):
        a._private_thing


def test_async_newer_endpoint():
    import asyncio

    async def run():
        async def h(req):
            return ok(CAT) if req.url.path == "/catalog" else ok({"ok": 1})
        a = AsyncApish("k", http_client=httpx.AsyncClient(transport=httpx.MockTransport(h)))
        r = await a.new_site.search(q="x")
        assert r["ok"] == 1 and (await a.prices())["/newsite/v1/search"] == 2
    asyncio.run(run())
