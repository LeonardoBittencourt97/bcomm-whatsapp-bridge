"""
Test fixtures for the test suite.
"""
import os
import sys

import jwt
import time
import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# Set JWT secret so the auth middleware can verify our test tokens.
os.environ["JWT_SECRET"] = "test-jwt-secret-32-chars-min-len-xyz"
os.environ["SUPABASE_JWT_SECRET"] = "test-jwt-secret-32-chars-min-len-xyz"


# Generate a real signed token to bypass the auth middleware.
TEST_TOKEN = jwt.encode(
    {
        "sub": "sup-1",
        "exp": int(time.time()) + 3600,
        "aud": "authenticated",
    },
    os.environ["JWT_SECRET"],
    algorithm="HS256",
)


def _noop():
    """No-op replacement for ensure_supabase."""
    return None


# Patch ensure_supabase at import time so every reference points to noop.
# This works because the routes call `ensure_supabase()` by module-attribute
# lookup, so re-binding the module attribute redirects all callsites.
def _apply_patches():
    import services.database as db
    import routes.deps as deps
    import routes.routes_pipelines as rp
    import routes.routes_auth as ra
    import routes.routes_orgs as ro
    import routes.routes_contacts as rc
    import routes.routes_users as ru
    import routes.routes_deals as rd
    import routes.routes_notes as rn
    import routes.routes_tags as rt
    import routes.routes_activities as ract
    import routes.routes_whatsapp as rw
    import routes.routes_agents as rag
    import routes.routes_search as rs
    import crm_routes as cr

    db._supabase_client = None
    db.ensure_supabase = _noop

    for mod in (deps, rp, ra, ro, rc, ru, rd, rn, rt, ract, rw, rag, rs):
        mod.ensure_supabase = _noop
    ra._ensure_supabase = _noop
    ru._ensure_supabase = _noop
    rag._ensure_supabase = _noop
    cr._ensure_supabase = _noop


_apply_patches()


@pytest.fixture(autouse=True)
def _reapply_patches():
    """Re-apply patches before each test (in case previous tests overrode them)."""
    _apply_patches()
    yield
    import services.database as db
    db._supabase_client = None


@pytest.fixture
def auth_headers():
    """Cookie-based auth headers that pass the auth middleware."""
    return {"Cookie": f"bcomm_crm_token={TEST_TOKEN}"}


@pytest.fixture
def mock_user():
    """Default master user dict."""
    return {
        "id": "user-1",
        "email": "master@bcomm.com",
        "role": "master",
        "is_active": True,
        "supabase_user_id": "sup-1",
    }


@pytest.fixture
def mock_agent_user():
    """Default agent user (restricted)."""
    return {
        "id": "user-2",
        "email": "agent@bcomm.com",
        "role": "agent",
        "is_active": True,
        "supabase_user_id": "sup-2",
    }