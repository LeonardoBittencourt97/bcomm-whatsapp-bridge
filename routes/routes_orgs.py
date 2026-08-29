"""Organizations CRM Routes"""
from fastapi import APIRouter, Query, HTTPException, Request
from typing import Optional
from datetime import datetime
import logging

from services.database import select, insert, update, delete, ensure_supabase
from routes.deps import get_current_user

router = APIRouter(prefix="/crm")
logger = logging.getLogger(__name__)


# GET /crm/organizations - List organizations
@router.get("/organizations")
async def list_organizations(
    request: Request,
    search: Optional[str] = Query(None, description="Search by name, CNPJ, or email"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """List all organizations with optional search"""
    try:
        await _get_current_user(request)
        ensure_supabase()
        
        filters = {}
        if search:
            filters["name"] = search
            
        result = await select(
            table="organizations",
            filters=filters if filters else None,
            limit=limit,
            offset=offset,
        )
        
        return {
            "status": "success",
            "data": result,
            "count": len(result) if result else 0
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing organizations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# GET /crm/organizations/{id} - Get single organization
@router.get("/organizations/{organization_id}")
async def get_organization(request: Request, organization_id: str):
    """Get an organization by ID"""
    try:
        await _get_current_user(request)
        ensure_supabase()
        
        result = await select(
            table="organizations",
            filters={"id": organization_id},
        )
        
        if not result or len(result) == 0:
            raise HTTPException(status_code=404, detail="Organization not found")
            
        return {
            "status": "success",
            "data": result[0]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting organization: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# POST /crm/organizations - Create organization
@router.post("/organizations")
async def create_organization(request: Request, data: dict):
    """Create a new organization"""
    try:
        await _get_current_user(request)
        ensure_supabase()
        
        # Add timestamps
        data["created_at"] = datetime.utcnow().isoformat()
        data["updated_at"] = datetime.utcnow().isoformat()
        
        result = insert(
            table="organizations",
            data=data,
        )
        
        return {
            "status": "success",
            "data": result,
            "message": "Organization created successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating organization: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# PUT /crm/organizations/{id} - Update organization
@router.put("/organizations/{organization_id}")
async def update_organization(request: Request, organization_id: str, data: dict):
    """Update an existing organization"""
    try:
        await _get_current_user(request)
        ensure_supabase()
        
        # Add updated timestamp
        data["updated_at"] = datetime.utcnow().isoformat()
        
        # Remove id from data if present
        data.pop("id", None)
        
        result = update(
            table="organizations",
            filters={"id": organization_id},
            data=data,
        )
        
        return {
            "status": "success",
            "data": result,
            "message": "Organization updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating organization: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# DELETE /crm/organizations/{id} - Delete organization
@router.delete("/organizations/{organization_id}")
async def delete_organization(request: Request, organization_id: str):
    """Delete an organization"""
    try:
        await _get_current_user(request)
        ensure_supabase()
        
        result = delete(
            table="organizations",
            filters={"id": organization_id},
        )
        
        return {
            "status": "success",
            "message": "Organization deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting organization: {e}")
        raise HTTPException(status_code=500, detail=str(e))
