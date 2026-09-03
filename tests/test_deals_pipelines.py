"""
Tests for deal and pipeline endpoints.
All Supabase calls are mocked — no real DB required.

NOTE: We patch the database functions at the IMPORT SITE (e.g. crm_routes.select)
because routes use `from services.database import select, ...` which creates a
local binding at import time. Patching services.database.select after import
would NOT redirect calls inside routes modules.
"""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


# ── Health ─────────────────────────────────────────────────────────


def test_health_endpoint_public():
    """Health endpoint should not require auth."""
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
        data = r.json()
        assert data["status"] == "ok"
        assert data["evolution_api"] == "ok"
        assert "uptime_seconds" in data


# ── Pipelines list ─────────────────────────────────────────────────


def test_list_pipelines_unauthorized():
    """Without token, /crm/pipelines must return 401."""
    r = client.get("/crm/pipelines")
    assert r.status_code == 401


def test_list_pipelines_with_auth(auth_headers, mock_user):
    """Master should see all pipelines with stages."""
    with patch("routes.routes_pipelines.get_current_user", AsyncMock(return_value=mock_user)), \
         patch("routes.routes_pipelines.apply_org_filter", AsyncMock(return_value={})), \
         patch("routes.routes_pipelines.select", AsyncMock(side_effect=[
             [{"id": "p1", "name": "Vendas"}],
             [{"id": "s1", "name": "Lead", "pipeline_id": "p1"}],
         ])):
        r = client.get("/crm/pipelines", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "pipelines" in data
        assert data["total"] == 1
        assert data["pipelines"][0]["stages"][0]["name"] == "Lead"


# ── Deals CRUD (crm_routes.py) ─────────────────────────────────────


def test_create_deal(auth_headers, mock_user):
    with patch("crm_routes.get_current_user", AsyncMock(return_value=mock_user)), \
         patch("crm_routes.select", AsyncMock(return_value=[{"id": "p1", "name": "Vendas", "organization_id": "org1"}])), \
         patch("crm_routes.insert", AsyncMock(return_value=[{"id": "deal-1", "title": "Novo deal", "stage": "lead"}])):

        r = client.post(
            "/crm/pipelines/deals",
            json={
                "title": "Novo deal",
                "pipeline_id": "p1",
                "phone": "5541999999999",
                "value": 1500.0,
                "stage": "lead",
            },
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "created"
        assert data["deal"]["title"] == "Novo deal"


def test_create_deal_pipeline_not_found(auth_headers, mock_user):
    with patch("crm_routes.get_current_user", AsyncMock(return_value=mock_user)), \
         patch("crm_routes.select", AsyncMock(return_value=[])):
        r = client.post(
            "/crm/pipelines/deals",
            json={"title": "X", "pipeline_id": "missing", "value": 0},
            headers=auth_headers,
        )
        assert r.status_code == 404


def test_update_deal(auth_headers, mock_user):
    with patch("crm_routes.get_current_user", AsyncMock(return_value=mock_user)), \
         patch("crm_routes.select") as mock_select, \
         patch("crm_routes.update", AsyncMock(return_value=[{"id": "d1", "stage": "qualified"}])):
        mock_select.side_effect = [
            [{"id": "d1", "stage": "lead"}],
            [{"id": "s1", "stage_id": "s1"}],
        ]
        r = client.put(
            "/crm/pipelines/deals/d1",
            json={"stage": "qualified"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "updated"


def test_delete_deal(auth_headers, mock_user):
    with patch("crm_routes.get_current_user", AsyncMock(return_value=mock_user)), \
         patch("crm_routes.select", AsyncMock(return_value=[{"id": "d1"}])), \
         patch("crm_routes.delete", AsyncMock(return_value=True)):
        r = client.delete("/crm/pipelines/deals/d1", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "deleted"


# ── Win / Lose ─────────────────────────────────────────────────────


def test_win_deal_master(auth_headers, mock_user):
    with patch("crm_routes.get_current_user", AsyncMock(return_value=mock_user)), \
         patch("crm_routes.is_unrestricted", return_value=True), \
         patch("crm_routes.select", AsyncMock(return_value=[{"id": "d1", "organization_id": "org1"}])), \
         patch("crm_routes.update", AsyncMock(return_value=[{"id": "d1", "stage": "closed_won"}])):
        r = client.put("/crm/pipelines/deals/d1/win", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "success"


def test_lose_deal_agent_forbidden(auth_headers, mock_agent_user):
    """Agent (restricted) cannot mark a deal in a foreign org as lost."""
    with patch("crm_routes.get_current_user", AsyncMock(return_value=mock_agent_user)), \
         patch("crm_routes.is_unrestricted", return_value=False), \
         patch("crm_routes.get_user_org_ids", AsyncMock(return_value={"my-org"})), \
         patch("crm_routes.select", AsyncMock(return_value=[{"id": "d1", "organization_id": "other-org"}])), \
         patch("crm_routes.update", AsyncMock(return_value=[])):
        r = client.put("/crm/pipelines/deals/d1/lose", headers=auth_headers)
        assert r.status_code == 403