"""Deals CRM Routes"""
from fastapi import APIRouter, Query, HTTPException, Request
from typing import Optional
from datetime import datetime
import logging

from services.database import select, insert, update, delete, ensure_supabase
from routes.deps import get_current_user, apply_org_filter, is_unrestricted, get_user_org_ids

router = APIRouter(prefix="/crm")
logger = logging.getLogger(__name__)


# GET /crm/deals - List deals with filters
@router.get("/deals")
async def list_deals(
    request: Request,
    stage_id: Optional[str] = Query(None, description="Filter by stage ID"),
    pipeline_id: Optional[str] = Query(None, description="Filter by pipeline ID"),
    status: Optional[str] = Query(None, description="Filter by status (open, won, lost)"),
    owner_id: Optional[str] = Query(None, description="Filter by owner ID"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """List all deals with optional filters"""
    user = await get_current_user(request)
    try:
        ensure_supabase()
        
        filters = {}
        if stage_id:
            filters["stage_id"] = stage_id
        if pipeline_id:
            filters["pipeline_id"] = pipeline_id
        if status:
            filters["status"] = status
        if owner_id:
            filters["owner_id"] = owner_id
        filters = await apply_org_filter(user, filters, request)
            
        result = await select(
            table="deals",
            filters=filters if filters else None,
            limit=limit,
            offset=offset,
            
        )
        
        return {
            "status": "success",
            "data": result,
            "count": len(result) if result else 0
        }
    except Exception as e:
        logger.error(f"Error listing deals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# GET /crm/deals/{id} - Get single deal
@router.get("/deals/{deal_id}")
async def get_deal(request: Request, deal_id: str):
    """Get a deal by ID"""
    user = await get_current_user(request)
    try:
        ensure_supabase()
        
        result = await select(
            table="deals",
            filters={"id": deal_id},
            
        )
        
        if not result or len(result) == 0:
            raise HTTPException(status_code=404, detail="Deal not found")

        if not is_unrestricted(user):
            deal_org = result[0].get("organization_id")
            if deal_org:
                org_ids = await get_user_org_ids(user["id"])
                if deal_org not in org_ids:
                    raise HTTPException(status_code=403, detail="Sem acesso a esta organização")
            
        return {
            "status": "success",
            "data": result[0]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting deal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# POST /crm/deals - Create deal
@router.post("/deals")
async def create_deal(request: Request, data: dict):
    """Create a new deal"""
    user = await get_current_user(request)
    try:
        ensure_supabase()
        
        if not is_unrestricted(user):
            org_ids = await get_user_org_ids(user["id"])
            if org_ids:
                data["organization_id"] = data.get("organization_id") or list(org_ids)[0]

        # Add timestamps and default status
        data["created_at"] = datetime.utcnow().isoformat()
        data["updated_at"] = datetime.utcnow().isoformat()
        if "status" not in data:
            data["status"] = "open"
        
        result = await insert(
            table="deals",
            data=data,
            
        )
        
        return {
            "status": "success",
            "data": result,
            "message": "Deal created successfully"
        }
    except Exception as e:
        logger.error(f"Error creating deal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# PUT /crm/deals/{id} - Update deal
@router.put("/deals/{deal_id}")
async def update_deal(request: Request, deal_id: str, data: dict):
    """Update an existing deal"""
    user = await get_current_user(request)
    try:
        ensure_supabase()

        if not is_unrestricted(user):
            existing = await select(table="deals", filters={"id": deal_id})
            if existing:
                deal_org = existing[0].get("organization_id")
                if deal_org:
                    org_ids = await get_user_org_ids(user["id"])
                    if deal_org not in org_ids:
                        raise HTTPException(status_code=403, detail="Sem acesso a esta organização")
        
        # Add updated timestamp
        data["updated_at"] = datetime.utcnow().isoformat()
        
        # Remove id from data if present
        data.pop("id", None)
        
        result = await update(
            table="deals",
            filters={"id": deal_id},
            data=data,
            
        )
        
        return {
            "status": "success",
            "data": result,
            "message": "Deal updated successfully"
        }
    except Exception as e:
        logger.error(f"Error updating deal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# PUT /crm/deals/{id}/stage - Update deal stage
@router.put("/deals/{deal_id}/stage")
async def update_deal_stage(request: Request, deal_id: str, data: dict):
    """Update the stage of a deal"""
    user = await get_current_user(request)
    try:
        ensure_supabase()
        
        existing = await select(table="deals", filters={"id": deal_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Deal not found")

        if not is_unrestricted(user):
            deal_org = existing[0].get("organization_id")
            if deal_org:
                org_ids = await get_user_org_ids(user["id"])
                if deal_org not in org_ids:
                    raise HTTPException(status_code=403, detail="Sem acesso a esta organização")

        stage = data.get("stage") or data.get("stage_id")
        if not stage:
            raise HTTPException(status_code=400, detail="stage is required")

        result = await update(
            table="deals",
            filters={"id": deal_id},
            data={
                "stage": stage,
                "updated_at": datetime.utcnow().isoformat()
            },

        )

        return {
            "status": "success",
            "data": result,
            "message": "Deal stage updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating deal stage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# PUT /crm/deals/{id}/win - Mark deal as won
@router.put("/deals/{deal_id}/win")
async def win_deal(request: Request, deal_id: str):
    """Mark a deal as won"""
    user = await get_current_user(request)
    try:
        ensure_supabase()

        existing = await select(table="deals", filters={"id": deal_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Deal not found")

        if not is_unrestricted(user):
            deal_org = existing[0].get("organization_id")
            if deal_org:
                org_ids = await get_user_org_ids(user["id"])
                if deal_org not in org_ids:
                    raise HTTPException(status_code=403, detail="Sem acesso a esta organização")

        result = await update(
            table="deals",
            filters={"id": deal_id},
            data={
                "status": "won",
                "stage": "closed_won",
                "probability": 100,
                "actual_close_date": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            },

        )

        return {
            "status": "success",
            "data": result,
            "message": "Deal marked as won"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error winning deal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# PUT /crm/deals/{id}/lose - Mark deal as lost
@router.put("/deals/{deal_id}/lose")
async def lose_deal(request: Request, deal_id: str, data: dict):
    """Mark a deal as lost"""
    user = await get_current_user(request)
    try:
        ensure_supabase()

        existing = await select(table="deals", filters={"id": deal_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Deal not found")

        if not is_unrestricted(user):
            deal_org = existing[0].get("organization_id")
            if deal_org:
                org_ids = await get_user_org_ids(user["id"])
                if deal_org not in org_ids:
                    raise HTTPException(status_code=403, detail="Sem acesso a esta organização")

        lost_reason = data.get("lost_reason", "")
        
        result = await update(
            table="deals",
            filters={"id": deal_id},
            data={
                "status": "lost",
                "stage": "closed_lost",
                "lost_reason": lost_reason,
                "actual_close_date": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            },

        )
        
        return {
            "status": "success",
            "data": result,
            "message": "Deal marked as lost"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error losing deal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# DELETE /crm/deals/{id} - Delete deal
@router.delete("/deals/{deal_id}")
async def delete_deal(request: Request, deal_id: str):
    """Delete a deal"""
    user = await get_current_user(request)
    try:
        ensure_supabase()

        if not is_unrestricted(user):
            existing = await select(table="deals", filters={"id": deal_id})
            if existing:
                deal_org = existing[0].get("organization_id")
                if deal_org:
                    org_ids = await get_user_org_ids(user["id"])
                    if deal_org not in org_ids:
                        raise HTTPException(status_code=403, detail="Sem acesso a esta organização")
        
        result = await delete(
            table="deals",
            filters={"id": deal_id},
            
        )
        
        return {
            "status": "success",
            "message": "Deal deleted successfully"
        }
    except Exception as e:
        logger.error(f"Error deleting deal: {e}")
        raise HTTPException(status_code=500, detail=str(e))
