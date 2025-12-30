"""Shim module to support legacy imports in tests.

This proxies to ``core.cache`` so patch targets like ``cache.get_redis`` work.
"""
from core.redis_client import get_redis  # noqa: F401
from core.cache import *  # noqa: F401,F403
