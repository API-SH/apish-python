import json

import httpx

from apish import Apish
from apish.tools import anthropic_tools, endpoint_tools, openai_tools, run_tool, search


def test_search_finds_platform_routes():
    r = search("tiktok comments", 5)
    assert r and all("/tiktok" in x["route"] for x in r[:2])


def test_tool_formats():
    o = openai_tools()
    assert o[0]["type"] == "function" and o[1]["function"]["name"] == "apish_call"
    a = anthropic_tools(["/tiktok/v1/profile"])
    assert a[0]["name"] == "apish_tiktok_profile" and "username" in a[0]["input_schema"]["required"]
    assert endpoint_tools(["/reddit/v1/subreddit"])[0]["x-route"] == "/reddit/v1/subreddit"


def test_run_tool_call_and_errors():
    seen = []
    c = Apish("k", http_client=httpx.Client(transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200, json={"ok": 1}))))
    assert json.loads(run_tool(c, "apish_call", '{"route": "/reddit/v1/subreddit", "params": {"subreddit": "python"}}')) == {"ok": 1}
    assert seen[0].url.params["raw"] == "0"
    assert json.loads(run_tool(c, "apish_tiktok_profile", {"username": "nasa"})) == {"ok": 1}
    assert seen[1].url.path == "/tiktok/v1/profile"
    assert "unknown tool" in run_tool(c, "nope", {})
