"""api.sh tools for LangChain (pip install "apish-sdk[langchain]").

    from apish import Apish
    from apish.langchain import apish_tools
    tools = apish_tools(Apish())                 # search + call
    agent = create_react_agent(llm, tools)       # or any LangChain / LangGraph agent
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .tools import run_tool, endpoint_tools

try:
    from langchain_core.tools import StructuredTool
    from pydantic import Field, create_model
except ImportError as e:  # pragma: no cover
    raise ImportError('apish.langchain needs langchain-core: pip install "apish-sdk[langchain]"') from e


def apish_tools(client: Any, routes: Optional[Iterable[str]] = None) -> List[Any]:
    """LangChain tools: apish_search + apish_call, or one tool per route when `routes` is given."""
    if routes:
        out = []
        types = {"integer": int, "number": float, "boolean": bool}
        for d in endpoint_tools(routes):
            name, props, req = d["name"], d["parameters"]["properties"], set(d["parameters"]["required"])
            fields = {k: ((types.get(v["type"], str)) if k in req else Optional[types.get(v["type"], str)], Field(... if k in req else None, description=v["description"])) for k, v in props.items()}
            schema = create_model(f"{name}_args", **fields)  # type: ignore[call-overload]
            out.append(StructuredTool.from_function(func=lambda _n=name, **kw: run_tool(client, _n, {k: v for k, v in kw.items() if v is not None}), name=name, description=d["description"], args_schema=schema))
        return out

    def search(query: str, limit: int = 10) -> str:
        return run_tool(client, "apish_search", {"query": query, "limit": limit})

    def call(route: str, params: Optional[Dict[str, Any]] = None) -> str:
        return run_tool(client, "apish_call", {"route": route, "params": params or {}})

    return [
        StructuredTool.from_function(func=search, name="apish_search", description="Search the api.sh catalog of public-web data endpoints (around 1,000 websites: search engines, social media, e-commerce, real estate, jobs, travel, news and sports). Returns routes, parameters and credit price."),
        StructuredTool.from_function(func=call, name="apish_call", description="Run an api.sh endpoint (route from apish_search) with its query parameters and return the JSON. Costs the endpoint's credits on success."),
    ]
