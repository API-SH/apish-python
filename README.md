# api.sh for Python

Official Python client for [api.sh](https://api.sh?utm_source=github&utm_medium=readme): public web data from around 1,000 websites as clean JSON: search engines, social media, e-commerce, real estate, jobs, travel, news and sports (Google, Amazon, TikTok, Zillow, LinkedIn and more). Every endpoint is a typed method.

```sh
pip install apish-sdk
```

```python
from apish import Apish

apish = Apish()  # reads APISH_API_KEY; or Apish("ash_live_…")  (https://app.api.sh/keys?utm_source=github&utm_medium=readme)

profile = apish.tiktok.profile(username="nasa")
print(profile["followers"], profile.meta.credits_used, profile.meta.request_id)

results = apish.amazon.search(q="headphones", options={"raw": False})
```

Python 3.9+, sync (`Apish`) and asyncio (`AsyncApish`).

## Calls

- `apish.<platform>.<endpoint>(**params, options=...)`: one method per endpoint, with keyword-only typed parameters and the price in its docstring.
- `apish.call(route, params, options)`: any route, e.g. `apish.call("/reddit/v1/subreddit", {"subreddit": "python"})`.
- Options: `raw` (False leaves out raw source blocks), `fields`, `fresh`, `output` ("csv" / "ndjson" returns text), `timeout`, `max_retries`.
- Results are dicts with `.meta` (`request_id`, `credits_used`, `credits_remaining`, `status`, `seconds`).
- Retries 502/503/504 and network errors with backoff (failed calls are never charged).

## Live catalog: counts, prices and new platforms

The typed methods cover every endpoint that existed when this version was published. The client also reads the
live catalog (free, no credits, cached for an hour), so newer platforms and endpoints work without an upgrade:

```python
cat = apish.catalog()                      # cat["platform_count"], cat["endpoint_count"]: today's numbers
prices = apish.prices()                    # route -> credits per call, live
apish.new_site.search(q="shoes")           # a platform added after this release
apish.hacker_news.some_new_endpoint(id="1")  # an endpoint added after this release
```

```python
for page in apish.paginate("/reddit/v1/subreddit", {"subreddit": "python"}, max_pages=5):
    print(len(page["posts"]))

from apish import ApishError
try:
    apish.zillow.property(url=url)
except ApishError as e:
    print(e.status, e.message, e.insufficient_credits, e.spend_limit, e.request_id)
```

## Async

```python
import asyncio
from apish import AsyncApish

async def main():
    async with AsyncApish() as apish:
        print((await apish.reddit.subreddit(subreddit="python"))["posts"][0]["title"])

asyncio.run(main())
```

## Account (free)

```python
apish.account.get()            # balance, plan, spend, limits
apish.account.usage(days=30)
apish.account.logs(status="error")
apish.account.result(request_id)   # a past response again, free, 30 days
```

## AI agents

```python
from apish.tools import openai_tools, anthropic_tools, run_tool
tools = openai_tools()             # apish_search + apish_call (or openai_tools(["/tiktok/v1/profile"]))
text = run_tool(apish, name, arguments)   # when the model calls a tool

# LangChain:  pip install "apish-sdk[langchain]"
from apish.langchain import apish_tools
tools = apish_tools(apish)
```

For Claude Desktop, Cursor and other MCP clients, use the [MCP server](https://api.sh/mcp?utm_source=github&utm_medium=readme).

Docs: https://api.sh/docs/sdks

## Source and contributions

This repository mirrors the package published on PyPI. The typed endpoint methods (`apish/_endpoints.py`) are generated from the live API.SH catalog, so new platforms appear here with each release. Bug reports, questions and pull requests for the hand-written parts are welcome: open an [issue](../../issues).

## License

MIT
