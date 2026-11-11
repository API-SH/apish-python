"""api.sh as tools for AI agents (OpenAI / Anthropic function calling, or any framework).

Two small, generic tools keep the prompt short however many endpoints exist:
  apish_search(query)          finds endpoints (route, what it returns, parameters, price)
  apish_call(route, params)    runs one and returns its JSON (spends its credits)

    from apish import Apish
    from apish.tools import openai_tools, anthropic_tools, run_tool
    apish = Apish()
    tools = openai_tools()                          # pass to the chat completions / responses API
    result = run_tool(apish, name, arguments)       # when the model calls one

Or one tool per endpoint for a fixed set: endpoint_tools(["/tiktok/v1/profile", "/amazon/v1/search"]).
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional

from ._endpoints import ENDPOINTS

MAX_CHARS = 60_000

_SEARCH = {
    "name": "apish_search",
    "description": "Search the api.sh catalog of public-web data endpoints (around 1,000 websites: search engines, social media, e-commerce, real estate, jobs, travel, news and sports) by keywords. Returns routes, what they return, their parameters and credit price.",
    "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "Keywords, e.g. 'tiktok comments' or 'zillow property'"}, "limit": {"type": "integer", "description": "Max results (default 10)"}}, "required": ["query"]},
}
_CALL = {
    "name": "apish_call",
    "description": "Run an api.sh endpoint found with apish_search and return its JSON. Costs the endpoint's credits on success; failed calls are free. Bulky raw source blocks are left out.",
    "parameters": {"type": "object", "properties": {"route": {"type": "string", "description": "The route, e.g. /reddit/v1/subreddit"}, "params": {"type": "object", "description": "Query parameters, e.g. {\"subreddit\": \"python\"}"}}, "required": ["route"]},
}


def search(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Endpoints matching the keywords, best first."""
    words = [w for w in re.split(r"\W+", query.lower()) if w]
    scored = []
    for e in ENDPOINTS:
        hay = f"{e['platform']} {e['route']} {e['summary']}".lower()
        score = sum((3 if w in e["platform"].lower() or w in e["route"] else 1) for w in words if w in hay)
        if score:
            scored.append((score, e))
    scored.sort(key=lambda x: -x[0])
    return [{"route": e["route"], "platform": e["platform"], "summary": e["summary"], "credits": e["credits"], "params": e["params"]} for _, e in scored[: max(1, min(50, limit))]]


def _schema(e: Dict[str, Any]) -> Dict[str, Any]:
    props = {}
    for p in e["params"]:
        t = {"integer": "integer", "number": "number", "boolean": "boolean"}.get(p["type"], "string")
        props[p["name"]] = {"type": t, "description": p.get("description") or p["name"], **({"enum": p["enum"]} if p.get("enum") else {})}
    return {"type": "object", "properties": props, "required": [p["name"] for p in e["params"] if p["required"]]}


def _tool_name(route: str) -> str:
    return "apish_" + re.sub(r"[^a-z0-9]+", "_", route.replace("/v1/", "/").lower()).strip("_")[:56]


def endpoint_tools(routes: Iterable[str]) -> List[Dict[str, Any]]:
    """One generic tool definition (name, description, JSON-schema parameters) per route."""
    by = {e["route"]: e for e in ENDPOINTS}
    out = []
    for r in routes:
        e = by.get(r)
        if not e:
            raise KeyError(f"unknown route {r}")
        out.append({"name": _tool_name(r), "description": f"{e['platform']}: {e['summary']} ({e['credits']} credits per call)", "parameters": _schema(e), "x-route": r})
    return out


def openai_tools(routes: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    """Tools in OpenAI's function-calling format. Default: apish_search + apish_call."""
    defs = endpoint_tools(routes) if routes else [_SEARCH, _CALL]
    return [{"type": "function", "function": {k: v for k, v in d.items() if k != "x-route"}} for d in defs]


def anthropic_tools(routes: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    """Tools in Anthropic's Messages API format. Default: apish_search + apish_call."""
    defs = endpoint_tools(routes) if routes else [_SEARCH, _CALL]
    return [{"name": d["name"], "description": d["description"], "input_schema": d["parameters"]} for d in defs]


def run_tool(client: Any, name: str, arguments: Any) -> str:
    """Runs a tool call from the model (sync client) and returns text for the tool result."""
    args = json.loads(arguments) if isinstance(arguments, str) else dict(arguments or {})
    if name == "apish_search":
        return json.dumps(search(args.get("query", ""), int(args.get("limit") or 10)))
    if name == "apish_call":
        route, params = args.get("route", ""), args.get("params") or {}
    else:
        match = next((e["route"] for e in ENDPOINTS if _tool_name(e["route"]) == name), None)
        if not match:
            return json.dumps({"error": f"unknown tool {name}"})
        route, params = match, args
    try:
        res = client.call(route, params, {"raw": False})
    except Exception as err:  # the model sees the error and can adjust
        return json.dumps({"error": str(err)})
    text = json.dumps(res) if isinstance(res, dict) else str(res)
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + "… (truncated: ask for fewer results or use the fields option)"
