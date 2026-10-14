"""The service-role Supabase client, shared by the routers.

It bypasses RLS, so every query made with it must already be scoped to the
caller — see app/auth.py.
"""

import os
from functools import lru_cache

from supabase import create_client


@lru_cache(maxsize=1)
def client():
    """Made once. Practice endpoints are chatty."""
    url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    return create_client(url, key) if (url and key) else None
