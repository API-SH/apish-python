"""Official Python client for api.sh: public web data from around 1,000 websites as clean JSON.

    from apish import Apish
    apish = Apish()                       # reads APISH_API_KEY
    print(apish.reddit.subreddit(subreddit="python")["posts"][0]["title"])

Docs: https://api.sh/docs/sdks
"""
from ._client import DEFAULT_BASE_URL, Apish, AsyncApish, __version__
from ._types import CallMeta, CallOptions, Result, TextResult
from .errors import ApishError

__all__ = ["Apish", "AsyncApish", "ApishError", "CallMeta", "CallOptions", "Result", "TextResult", "DEFAULT_BASE_URL", "__version__"]
