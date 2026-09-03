"""
Tests for auth and security boundaries.
Covers: public endpoints, JWT requirement, login validation, role-based access.
"""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


# ── Health ─────────────────────────────────────────────────────────


def test_health_requires_no_auth():
    """Health endpoint must be reachable without any token."""
    with patch("main.evolution_client") as evo, \
         patch("main.llm_client") as llm, \
         patch("main.stt_client") as stt, \
         patch("main.hermes_client") as hermes:
        evo.health_check = AsyncMock(return_value=True)
        llm.health_check = AsyncMock(return_value=True)
        stt.health_check = AsyncMock(return_value=True)
        hermes.is_available = AsyncMock(return_value=True)

        r = client.get("/health")
        assert r.status_code == 200


# ── /crm/* auth requirement ────────────────────────────────────────


def test_crm_endpoint_without_token_returns_401():
    """Any /crm/* endpoint must require authentication."""
    r = client.get("/crm/pipelines")
    assert r.status_code == 401


def test_crm_endpoint_with_invalid_token_returns_401():
    """Invalid JWT must be rejected by the auth middleware."""
    headers = {"Cookie": "bcomm_crm_token=invalid.jwt.token"}
    r = client.get("/crm/pipelines", headers=headers)
    assert r.status_code == 401


def test_crm_endpoint_with_empty_token_returns_401():
    """Empty Bearer token must be rejected."""
    headers = {"Authorization": "Bearer "}
    r = client.get("/crm/pipelines", headers=headers)
    assert r.status_code == 401


# ── Login validation ────────────────────────────────────────────────


@patch("routes.routes_auth.httpx.AsyncClient")
def test_login_with_wrong_password_returns_401(mock_async_client_cls):
    """Wrong password must return 401 with an error detail."""
    fake_response = AsyncMock()
    fake_response.status_code = 401
    fake_response.headers = {"content-type": "application/json"}
    fake_response.json = lambda: {"error_description": "Invalid login credentials"}

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__ = AsyncMock(return_value=None)
    cm.post = AsyncMock(return_value=fake_response)
    mock_async_client_cls.return_value = cm

    r = client.post(
        "/crm/auth/login",
        json={"email": "user@example.com", "password": "badpassword"},
    )
    assert r.status_code == 401
    body = r.json()
    assert "detail" in body


@patch("routes.routes_auth.httpx.AsyncClient")
def test_login_with_invalid_email_returns_422(mock_async_client_cls):
    """Invalid email format must be rejected by Pydantic validation."""
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__ = AsyncMock(return_value=None)
    mock_async_client_cls.return_value = cm

    r = client.post(
        "/crm/auth/login",
        json={"email": "not-an-email", "password": "validpassword"},
    )
    # 422 = Unprocessable Entity (pydantic validation error)
    assert r.status_code == 422


# ── Role-based access control ──────────────────────────────────────


def test_create_organization_as_non_admin_returns_403(auth_headers, mock_agent_user):
    """Agent must not be able to create organizations (master/admin_geral only)."""
    with patch("routes.routes_orgs.get_current_user", AsyncMock(return_value=mock_agent_user)):
        r = client.post(
            "/crm/organizations",
            json={"name": "Test Org", "slug": "test-org"},
            headers=auth_headers,
        )
        assert r.status_code == 403


def test_create_organization_as_master_returns_201(auth_headers, mock_user):
    """Master user can create organizations."""
    with patch("routes.routes_orgs.get_current_user", AsyncMock(return_value=mock_user)), \
         patch("routes.routes_orgs.insert", AsyncMock(return_value=[{"id": "org-1", "name": "Test Org"}])):
        r = client.post(
            "/crm/organizations",
            json={"name": "Test Org", "slug": "test-org"},
            headers=auth_headers,
        )
        # 201 Created or 200 — both acceptable for successful creation
        assert r.status_code in (200, 201)


def test_system_info_endpoint_as_agent_returns_403(auth_headers, mock_agent_user):
    """System info endpoint must be restricted to master/admin_geral."""
    with patch("main.get_current_user", AsyncMock(return_value=mock_agent_user)):
        r = client.get("/admin/system-info", headers=auth_headers)
        assert r.status_code == 403


def test_admin_logs_endpoint_as_agent_returns_403(auth_headers, mock_agent_user):
    """Admin logs endpoint must be restricted to master/admin_geral."""
    with patch("main.get_current_user", AsyncMock(return_value=mock_agent_user)):
        r = client.get("/admin/logs", headers=auth_headers)
        assert r.status_code == 403


# ── Win/Lose role check ──────────────────────────────────────


def test_win_deal_as_agent_in_foreign_org_returns_403(auth_headers, mock_agent_user):
    """Agent from one org cannot mark a deal in another org as won."""
    with patch("crm_routes.get_current_user", AsyncMock(return_value=mock_agent_user)), \
         patch("crm_routes.is_unrestricted", return_value=False), \
         patch("crm_routes.get_user_org_ids", AsyncMock(return_value={"agent-org"})), \
         patch("crm_routes.select", AsyncMock(return_value=[{"id": "d1", "organization_id": "other-org"}])):
        r = client.put("/crm/pipelines/deals/d1/win", headers=auth_headers)
        assert r.status_code == 403


def test_win_deal_as_agent_in_own_org_succeeds(auth_headers, mock_agent_user):
    """Agent can mark a deal in their own org as won."""
    with patch("crm_routes.get_current_user", AsyncMock(return_value=mock_agent_user)), \
         patch("crm_routes.is_unrestricted", return_value=False), \
         patch("crm_routes.get_user_org_ids", AsyncMock(return_value={"agent-org"})), \
         patch("crm_routes.select", AsyncMock(return_value=[{"id": "d1", "organization_id": "agent-org"}])), \
         patch("crm_routes.update", AsyncMock(return_value=[{"id": "d1", "stage": "closed_won"}])):
        r = client.put("/crm/pipelines/deals/d1/win", headers=auth_headers)
        assert r.status_code == 200